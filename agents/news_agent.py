"""
news_detective — the sentiment dimension.

Lexicon scoring over headlines. No LLM: it is deterministic, needs no API key,
and cannot stall the 12-second agent budget. This is also the agent we
deliberately kill for the degraded-data demo (KILL_AGENT=news_detective),
so it stays simple on purpose.
"""
import json
import pathlib
import re
import sys
from functools import lru_cache

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from contracts import AgentOutput, MarketData

NEWS_PATH = pathlib.Path(__file__).resolve().parent.parent / "data" / "news" / "news.json"

POSITIVE = {
    "high": 2, "record": 2, "wins": 2, "win": 2, "raise": 2, "raises": 2, "beat": 2,
    "beats": 2, "strong": 2, "growth": 1, "expand": 1, "expands": 1, "expansion": 1,
    "improves": 1, "recovery": 1, "rises": 1, "up": 1, "gain": 2, "gains": 2,
    "upgrade": 2, "outperform": 2, "dividend": 1, "profit": 2, "surge": 2,
}
NEGATIVE = {
    "slide": 2, "slides": 2, "fall": 2, "falls": 2, "decline": 2, "declines": 2,
    "cut": 2, "cuts": 2, "weakness": 2, "weak": 2, "pressure": 2, "loss": 2,
    "losses": 2, "notice": 1, "demand": 1, "probe": 2, "delayed": 2, "delay": 2,
    "downgrade": 2, "concern": 1, "concerns": 1, "shrinks": 2, "weighing": 1,
    "weighs": 1, "intensifies": 1, "competition": 1, "persists": 1,
}
_WORD = re.compile(r"[a-z]+")


@lru_cache(maxsize=1)
def _news() -> dict[str, list[str]]:
    if not NEWS_PATH.exists():
        return {}
    return {r["symbol"].upper(): r.get("headlines", [])
            for r in json.loads(NEWS_PATH.read_text() or "[]")}


def _score_headline(h: str) -> int:
    words = _WORD.findall(h.lower())
    return sum(POSITIVE.get(w, 0) for w in words) - sum(NEGATIVE.get(w, 0) for w in words)


async def run(symbol: str, market_data: MarketData | None = None) -> AgentOutput:
    headlines = _news().get(symbol.upper(), [])

    # DEGRADED, not neutral: no coverage is missing information, and saying
    # "neutral" would let an absent signal vote in the synthesis.
    if not headlines:
        return AgentOutput(
            agent_name="news_detective", symbol=symbol, signal="UNAVAILABLE",
            confidence=0.0, status="DEGRADED",
            reasons=[f"No news coverage found for {symbol}; the sentiment "
                     f"dimension is missing, not neutral."])

    scores = [(_score_headline(h), h) for h in headlines]
    pos = [h for s, h in scores if s > 0]
    neg = [h for s, h in scores if s < 0]
    total = sum(s for s, _ in scores)

    signal = "BULLISH" if total >= 2 else "BEARISH" if total <= -2 else "NEUTRAL"
    # Confidence scales with net score per headline, capped — a lexicon over
    # five headlines does not justify high conviction.
    confidence = round(min(abs(total) / (2.0 * len(headlines)), 0.75), 2)

    reasons = [
        f"{len(headlines)} headline(s): {len(pos)} positive, {len(neg)} negative, "
        f"net lexicon score {total:+d} -> {signal} at confidence {confidence:.2f}"
    ]
    strongest = max(scores, key=lambda p: abs(p[0]))
    if strongest[0]:
        reasons.append(f"Strongest signal ({strongest[0]:+d}): \"{strongest[1]}\"")

    return AgentOutput(
        agent_name="news_detective", symbol=symbol, signal=signal,
        confidence=confidence, reasons=reasons, status="COMPLETE",
    )
