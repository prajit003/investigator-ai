"""
THE ANTI-INTEGRATION-BUG LAYER. Owned by P2 (backend). Nobody else edits this.

Every agent is treated as UNTRUSTED CODE. An agent may crash, hang, return None,
return the wrong shape, or cite a source it never retrieved. None of that is
allowed to break the pipeline or put an uncited claim in front of a user.
"""
import asyncio
import time
from typing import Callable, List, Sequence

from contracts import (
    AgentOutput, DataQuality, Evidence, Metrics, Portfolio, UserProfile,
)

AGENT_TIMEOUT_S = 12


async def run_agent_safely(fn: Callable, agent_name: str, symbol: str, *args) -> AgentOutput:
    """
    Wrap ANY agent callable. Guarantees, in order:
      - never raises
      - never hangs past AGENT_TIMEOUT_S
      - always returns a schema-valid AgentOutput

    This single function is why one broken agent cannot take down the demo.
    Accepts a coroutine function or a plain sync function.
    """
    t0 = time.perf_counter()
    try:
        result = fn(symbol, *args)
        raw = await asyncio.wait_for(result, timeout=AGENT_TIMEOUT_S) \
            if asyncio.iscoroutine(result) else result
    except asyncio.TimeoutError:
        return AgentOutput.failed(agent_name, symbol, f"timed out after {AGENT_TIMEOUT_S}s")
    except Exception as e:
        return AgentOutput.failed(agent_name, symbol, f"{type(e).__name__}: {e}")

    elapsed = int((time.perf_counter() - t0) * 1000)
    try:
        out = raw if isinstance(raw, AgentOutput) else AgentOutput.model_validate(raw)
    except Exception as e:
        # The agent returned the wrong shape. Degrade, do not crash.
        return AgentOutput.failed(agent_name, symbol, f"bad output shape: {e}")

    out.latency_ms = elapsed
    out.agent_name = agent_name
    out.symbol = symbol or out.symbol
    return out


def attach_verified_evidence(out: AgentOutput, cited_chunk_ids, retrieved_chunks) -> AgentOutput:
    """
    THE GROUNDING GUARD, applied centrally so it cannot be skipped under pressure.

    Delegates to rag.retrieve.verify_evidence — the single implementation. An
    agent says WHICH chunk_ids support its claim; only ids that were actually
    retrieved survive, and the evidence text is copied verbatim from the corpus.
    A displayed quote therefore cannot be fabricated by a model.

    Returns the agent output; warnings belong in data_quality.warnings.
    """
    from rag.retrieve import verify_evidence

    evidence, warnings = verify_evidence(cited_chunk_ids, retrieved_chunks)
    out.evidence = [Evidence.model_validate(e) for e in evidence]
    if warnings:
        out.status = "DEGRADED" if out.status == "COMPLETE" else out.status
        out.reasons = list(out.reasons) + warnings
    if not out.evidence:
        # PS-01: never present an uncited claim as if it were sourced.
        out.confidence = min(out.confidence, 0.3)
    return out, warnings


def compute_metrics(agent_outputs: Sequence[AgentOutput], portfolio: Portfolio | None,
                    total_latency_ms: float, agent_latency_ms: float = 0.0) -> Metrics:
    """
    The three-plus session metrics PS-01 requires.

    concentration_score is the ACTUAL largest holding as a percentage of the
    portfolio — not a policy ceiling. A limit is the same number for every user
    and would silently break the conservative downgrade rule.
    """
    done = [a for a in agent_outputs if a.status in ("COMPLETE", "DEGRADED")]
    failed = [a for a in agent_outputs if a.status == "FAILED"]
    with_ev = [a for a in done if a.evidence]

    concentration = 0.0
    if portfolio and portfolio.holdings and portfolio.portfolio_value > 0:
        concentration = round(
            max(h.current_value for h in portfolio.holdings) / portfolio.portfolio_value * 100, 2
        )

    return Metrics(
        total_latency_ms=int(total_latency_ms),
        agent_latency_ms=int(agent_latency_ms or total_latency_ms),
        signal_confidence=round(sum(a.confidence for a in done) / len(done), 4) if done else 0.0,
        evidence_coverage=round(len(with_ev) / len(done), 4) if done else 0.0,
        concentration_score=concentration,
        agents_complete=len(done),
        agents_failed=len(failed),
    )


def compute_data_quality(agent_outputs: Sequence[AgentOutput], symbol: str,
                         extra_warnings: List[str] | None = None) -> DataQuality:
    """Map agent health onto the data_quality block ARCHITECTURE.md §14 defines."""
    from rag.ingest import filing_data_status

    # An agent name may legitimately appear once; treat ANY failure under a name
    # as that source being unavailable, rather than letting a later entry mask it.
    # An agent that ran to completion but found nothing reports
    # signal="UNAVAILABLE". Its source is just as absent as a crashed agent's,
    # so it must not be reported AVAILABLE while warnings say the data is
    # missing — the two blocks are read side by side in the UI.
    failed_names = {a.agent_name for a in agent_outputs
                    if a.status == "FAILED" or a.signal == "UNAVAILABLE"}
    seen_names = {a.agent_name for a in agent_outputs}

    def avail(name: str) -> str:
        return "AVAILABLE" if (name in seen_names and name not in failed_names) else "UNAVAILABLE"

    warnings = list(extra_warnings or [])
    for a in agent_outputs:
        if a.status == "FAILED":
            warnings.append(f"{a.agent_name} unavailable; confidence reduced.")

    # filing_data is unavailable if EITHER the corpus has nothing for this symbol
    # OR the filing agent failed. Reporting AVAILABLE because the corpus exists,
    # while the agent that reads it is dead, would be a lie to the user.
    corpus = filing_data_status(symbol)
    if corpus == "UNAVAILABLE":
        warnings.append(f"No regulatory filings available for {symbol}; "
                        f"fundamental view is missing, not neutral.")
    filing = "UNAVAILABLE" if (corpus == "UNAVAILABLE"
                               or "filing_detective" in failed_names) else "AVAILABLE"

    market, news = avail("market_detective"), avail("news_detective")
    unavailable = [s for s in (market, news, filing) if s == "UNAVAILABLE"]
    overall = "GOOD" if not unavailable else ("POOR" if len(unavailable) > 1 else "DEGRADED")

    return DataQuality(market_data=market, news_data=news, filing_data=filing,
                       overall_quality=overall, warnings=warnings)
