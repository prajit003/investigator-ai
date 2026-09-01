"""
market_detective — the price and volume dimensions.

DETERMINISTIC MATH, NO LLM. Two reasons: it returns in under a millisecond, and
when a judge asks where the confidence number came from we can point at the
exact rule and the exact numbers that produced it.

PS-01 requires three INDEPENDENT dimensions. Price and volume are computed
separately here — `price_signal()` and `volume_signal()` share no terms — and
the orchestrator reports them as distinct signals. `run()` combines them into
this agent's single verdict for the synthesis layer.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from contracts import AgentOutput, MarketData, Signal

# Thresholds, named so `reasons` can quote them back with real numbers.
MOMENTUM_STRONG = 0.10
RSI_OVERBOUGHT = 70.0
RSI_OVERSOLD = 30.0
VOLUME_ANOMALY = 1.5
VOLUME_EXTREME = 2.5


def _label(score: float) -> str:
    return "BULLISH" if score >= 0.25 else "BEARISH" if score <= -0.25 else "NEUTRAL"


def price_signal(m: MarketData) -> Signal:
    """DIMENSION 1 — trend and mean reversion. Uses momentum, RSI, session move.
    Deliberately ignores volume so this stays independent of dimension 2."""
    score, reasons = 0.0, []

    if m.momentum is None:
        # ARCHITECTURE.md §15.2: a missing indicator is missing, not neutral.
        # Drop the term and say so, rather than scoring it as 0.00 silently.
        reasons.append("Momentum unavailable (insufficient price history) — "
                       "term dropped, not scored as neutral")
    elif m.momentum >= MOMENTUM_STRONG:
        score += 0.50
        reasons.append(f"Momentum {m.momentum:+.2f} >= {MOMENTUM_STRONG:.2f} "
                       f"(strong uptrend, +0.50)")
    elif m.momentum <= -MOMENTUM_STRONG:
        score -= 0.50
        reasons.append(f"Momentum {m.momentum:+.2f} <= -{MOMENTUM_STRONG:.2f} "
                       f"(strong downtrend, -0.50)")
    else:
        reasons.append(f"Momentum {m.momentum:+.2f} within +/-{MOMENTUM_STRONG:.2f} "
                       f"(no trend signal, 0.00)")

    if m.price_change_percent >= 1.0:
        score += 0.20
        reasons.append(f"Session move {m.price_change_percent:+.2f}% (+0.20)")
    elif m.price_change_percent <= -1.0:
        score -= 0.20
        reasons.append(f"Session move {m.price_change_percent:+.2f}% (-0.20)")

    if m.rsi is None:
        reasons.append("RSI unavailable (needs 15 daily closes) — term dropped, "
                       "not scored as neutral")
    elif m.rsi >= RSI_OVERBOUGHT:
        score -= 0.20
        reasons.append(f"RSI {m.rsi:.1f} >= {RSI_OVERBOUGHT:.0f} (overbought, "
                       f"caution against chasing, -0.20)")
    elif m.rsi <= RSI_OVERSOLD:
        score += 0.20
        reasons.append(f"RSI {m.rsi:.1f} <= {RSI_OVERSOLD:.0f} (oversold, "
                       f"bounce potential, +0.20)")

    label = _label(score)
    conf = round(min(abs(score), 1.0), 2)
    reasons.append(f"Price score {score:+.2f} -> {label} at confidence {conf:.2f}")
    return Signal(signal=label, confidence=conf, reasons=reasons)


def volume_signal(m: MarketData) -> Signal:
    """DIMENSION 2 — participation. Uses only the volume ratio and the SIGN of
    the session move; it never reads momentum or RSI. Volume is confirmation,
    so an anomaly on a rising price is bullish and on a falling price bearish;
    without an anomaly there is no signal at all."""
    if m.volume <= 0:
        # The feed reported no traded quantity, or the quote layer zeroed a
        # figure it could not believe. Either way we do not know participation,
        # and "no anomaly" would be a claim we cannot support.
        return Signal(signal="UNAVAILABLE", confidence=0.0,
                      reasons=[f"No traded volume reported for {m.symbol}; the "
                               f"participation dimension is missing, not neutral."])

    ratio = m.volume / m.average_volume if m.average_volume else 0.0
    direction = 1 if m.price_change_percent > 0 else -1 if m.price_change_percent < 0 else 0
    reasons = [f"Volume {m.volume:,} vs 30-day average {m.average_volume:,} = {ratio:.1f}x"]

    if ratio < VOLUME_ANOMALY or direction == 0:
        reasons.append(f"Below the {VOLUME_ANOMALY:.1f}x anomaly threshold — "
                       f"the move is not volume-confirmed (NEUTRAL)")
        return Signal(signal="NEUTRAL", confidence=0.0, reasons=reasons)

    magnitude = 0.75 if ratio >= VOLUME_EXTREME else 0.50
    score = magnitude * direction
    label = _label(score)
    reasons.append(f"{ratio:.1f}x >= {VOLUME_ANOMALY:.1f}x on a "
                   f"{'rising' if direction > 0 else 'falling'} price confirms the move "
                   f"({score:+.2f}) -> {label} at confidence {magnitude:.2f}")
    return Signal(signal=label, confidence=magnitude, reasons=reasons)


async def run(symbol: str, market_data: MarketData | None = None) -> AgentOutput:
    if market_data is None:
        return AgentOutput(
            agent_name="market_detective", symbol=symbol, signal="UNAVAILABLE",
            confidence=0.0, status="DEGRADED",
            reasons=[f"No market data for {symbol}; price and volume dimensions "
                     f"are missing, not neutral."])

    price, volume = price_signal(market_data), volume_signal(market_data)

    # Combine the two independent dimensions into this agent's single verdict.
    # A dimension can be UNAVAILABLE — no volume was reported, or there is not
    # enough history for the price terms. Average over the dimensions that
    # ACTUALLY REPORTED rather than dividing by two regardless, which would
    # halve a real signal because the other half is missing.
    weights = {"BULLISH": 1, "BEARISH": -1, "NEUTRAL": 0}
    live = [sig for sig in (price, volume) if sig.signal in weights]

    if not live:
        return AgentOutput(
            agent_name="market_detective", symbol=symbol, signal="UNAVAILABLE",
            confidence=0.0, status="DEGRADED",
            reasons=([f"PRICE: {r}" for r in price.reasons]
                     + [f"VOLUME: {r}" for r in volume.reasons]
                     + ["Neither the price nor the volume dimension reported; "
                        "the market view is missing, not neutral."]))

    combined = sum(weights[s.signal] * s.confidence for s in live) / len(live)
    label = _label(combined)
    conf = round(min(abs(combined) * 1.6, 1.0), 2)   # scale: agreement earns conviction

    status = "COMPLETE" if len(live) == 2 else "DEGRADED"
    reasons = ([f"PRICE: {r}" for r in price.reasons]
               + [f"VOLUME: {r}" for r in volume.reasons]
               + [f"Combined price {price.signal}@{price.confidence:.2f} with volume "
                  f"{volume.signal}@{volume.confidence:.2f} over {len(live)} reporting "
                  f"dimension(s) -> {label} at confidence {conf:.2f}"])

    return AgentOutput(agent_name="market_detective", symbol=symbol, signal=label,
                       confidence=conf, reasons=reasons, status=status)
