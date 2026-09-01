"""
filing_detective — the fundamental dimension, grounded in the filings corpus.

This is the only agent that cites sources, so it carries the grounding
guarantee: the model chooses WHICH chunk_ids support its finding, and
`safety.attach_verified_evidence` copies the quoted text verbatim from the
corpus. The model never writes the quote, so a displayed quote cannot be
fabricated — it can only be a real sentence from a real document.

Runs in two modes:
  - with ANTHROPIC_API_KEY: Claude reads the retrieved chunks and judges
  - without: a deterministic lexicon over the same chunks
Both paths cite real chunk_ids and pass through the same grounding guard, so
the demo never depends on a network call succeeding.
"""
import os
import pathlib
import re
import sys
from typing import List, Literal

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from pydantic import BaseModel, Field

from contracts import AgentOutput, MarketData
from rag.retrieve import retrieve
from safety import attach_verified_evidence

MODEL = "claude-opus-5"
QUERY = "revenue growth, margins, debt, profitability, risks and regulatory disclosures"
TOP_K = 3

# Fundamental language. Used by the offline path, and as the tie-breaker when
# the model is unavailable. Weighted: a contingent liability matters more than
# the word "growth".
NEGATIVE = {
    "down": 2, "decline": 3, "declined": 3, "weaker": 3, "weakness": 2, "pressure": 2,
    "contingent": 3, "liability": 2, "negative": 3, "below": 2, "short": 2,
    "increased": 0, "contest": 1, "assessment": 1, "flagged": 3, "compression": 3,
    "borrowing": 2, "shortfall": 3, "impairment": 3,
}
POSITIVE = {
    "growth": 2, "expanded": 3, "expansion": 2, "ahead": 3, "highest": 3, "improved": 3,
    "favourable": 2, "strong": 2, "record": 3, "consecutive": 2, "reiterated": 1,
    "approved": 1, "visibility": 2, "conversion": 1,
}
_WORD = re.compile(r"[a-z]+")


class _Verdict(BaseModel):
    """
    The model's response shape.

    It may choose a signal, a confidence, prose, and WHICH chunk_ids support
    them. It cannot write the symbol, the status, or the quoted text. What it
    cannot write, it cannot fabricate.
    """
    signal: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    cited_chunk_ids: List[str]


SYSTEM = """You are a fundamental equity analyst covering Indian listed companies.

You may ONLY state claims supported by the numbered source chunks provided.
Every claim must be traceable to a chunk_id, and you must list the ids you
relied on in cited_chunk_ids. If the chunks do not support a conclusion, say so
explicitly and lower your confidence rather than guessing.

Never invent a figure. If you name a number it must appear verbatim in a chunk.
Judge company fundamentals only — ignore price action and momentum, which other
agents cover. Set confidence from how directly the sources support your call."""


def _numbered(chunks) -> str:
    return "\n\n".join(
        f"[{c['chunk_id']}] (source: {c['source_name']}, {c['section']}, p.{c['page']})\n{c['text']}"
        for c in chunks
    )


def _offline_verdict(chunks) -> _Verdict:
    """Deterministic fallback. Scores the retrieved text and cites the chunks
    that actually drove the score — never a chunk it did not read."""
    scored = []
    for c in chunks:
        words = _WORD.findall(c["text"].lower())
        score = sum(POSITIVE.get(w, 0) for w in words) - sum(NEGATIVE.get(w, 0) for w in words)
        scored.append((score, c))

    total = sum(s for s, _ in scored)
    signal = "BULLISH" if total >= 3 else "BEARISH" if total <= -3 else "NEUTRAL"
    # Cite the chunks that moved the verdict in its own direction.
    if signal == "BULLISH":
        cited = [c["chunk_id"] for s, c in scored if s > 0]
    elif signal == "BEARISH":
        cited = [c["chunk_id"] for s, c in scored if s < 0]
    else:
        cited = [c["chunk_id"] for _, c in scored[:1]]

    confidence = round(min(abs(total) / 12.0, 0.75), 2)
    detail = ", ".join(f"{c['section']} ({s:+d})" for s, c in scored)
    return _Verdict(
        signal=signal, confidence=confidence,
        reasoning=(f"Lexicon assessment of {len(chunks)} retrieved filing excerpt(s): "
                   f"{detail}. Net fundamental tone {total:+d} -> {signal}."),
        cited_chunk_ids=cited or [c["chunk_id"] for _, c in scored[:1]],
    )


async def _model_verdict(symbol: str, chunks) -> _Verdict:
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic()
    resp = await client.messages.parse(
        model=MODEL,
        max_tokens=8000,
        system=SYSTEM,
        # Low effort deliberately: the orchestrator kills us at 12s and this is a
        # bounded judgement over ~250 words. Depth buys nothing here.
        output_config={"effort": "low"},
        messages=[{"role": "user", "content":
                   f"Assess the fundamental outlook for {symbol}.\n\n"
                   f"SOURCE CHUNKS:\n\n{_numbered(chunks)}\n\n"
                   f"cited_chunk_ids must contain only ids that appear above."}],
        output_format=_Verdict,
    )
    if resp.parsed_output is None:
        raise ValueError("model returned no parsed output")
    return resp.parsed_output


async def run(symbol: str, market_data: MarketData | None = None) -> AgentOutput:
    chunks = retrieve(QUERY, symbol, k=TOP_K)

    # DEGRADED, not neutral: an absent filing is missing information, and a
    # NEUTRAL vote would let that absence influence the synthesis.
    if not chunks:
        return AgentOutput(
            agent_name="filing_detective", symbol=symbol, signal="UNAVAILABLE",
            confidence=0.0, status="DEGRADED",
            reasons=[f"No regulatory filings or transcripts available for {symbol}; "
                     f"the fundamental view is missing, not neutral."])

    used_model = False
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        try:
            v = await _model_verdict(symbol, chunks)
            used_model = True
        except Exception as e:
            v = _offline_verdict(chunks)
            v.reasoning = f"[model unavailable: {type(e).__name__}] " + v.reasoning
    else:
        v = _offline_verdict(chunks)

    out = AgentOutput(
        agent_name="filing_detective", symbol=symbol, signal=v.signal,
        confidence=v.confidence, status="COMPLETE",
        reasons=[v.reasoning,
                 f"Retrieved {len(chunks)} chunk(s) from the filings corpus; "
                 f"assessed by {'Claude' if used_model else 'deterministic lexicon'}."],
    )
    # The grounding guard: drops any cited id that was not retrieved and copies
    # the surviving quotes verbatim from the corpus.
    out, warnings = attach_verified_evidence(out, v.cited_chunk_ids, chunks)
    if warnings:
        out.reasons.extend(warnings)
    return out
