"""
market_detective — the price and volume dimensions.

DETERMINISTIC MATH, NO LLM. Two reasons: it returns in under a millisecond, and
when a judge asks where the confidence number came from we can point at the
exact rule and the exact numbers that produced it.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from contracts import AgentOutput, MarketData

# Thresholds. Named so `reasons` can quote them back with real numbers.
MOMENTUM_STRONG = 0.10
RSI_OVERBOUGHT = 70.0
RSI_OVERSOLD = 30.0
VOLUME_ANOMALY = 1.5


async def run(symbol: str, market_data: MarketData | None = None) -> AgentOutput:
    if market_data is None:
        return AgentOutput(
            agent_name="market_detective", symbol=symbol, signal="UNAVAILABLE",
            confidence=0.0, status="DEGRADED",
            reasons=[f"No market data for {symbol}; price and volume dimensions "
                     f"are missing, not neutral."])

    m = market_data
    score = 0.0
    reasons: list[str] = []

    # --- price dimension ---
    if m.momentum >= MOMENTUM_STRONG:
        score += 0.40
        reasons.append(f"Momentum {m.momentum:+.2f} >= {MOMENTUM_STRONG:.2f} "
                       f"(strong uptrend, +0.40)")
    elif m.momentum <= -MOMENTUM_STRONG:
        score -= 0.40
        reasons.append(f"Momentum {m.momentum:+.2f} <= -{MOMENTUM_STRONG:.2f} "
                       f"(strong downtrend, -0.40)")
    else:
        reasons.append(f"Momentum {m.momentum:+.2f} is within +/-{MOMENTUM_STRONG:.2f} "
                       f"(no trend signal, 0.00)")

    if m.price_change_percent >= 1.0:
        score += 0.15
        reasons.append(f"Price {m.price_change_percent:+.2f}% on the session (+0.15)")
    elif m.price_change_percent <= -1.0:
        score -= 0.15
        reasons.append(f"Price {m.price_change_percent:+.2f}% on the session (-0.15)")

    # --- RSI: a mean-reversion caution, applied AGAINST the prevailing trend ---
    if m.rsi >= RSI_OVERBOUGHT:
        score -= 0.15
        reasons.append(f"RSI {m.rsi:.1f} >= {RSI_OVERBOUGHT:.0f} (overbought, "
                       f"caution against chasing, -0.15)")
    elif m.rsi <= RSI_OVERSOLD:
        score += 0.15
        reasons.append(f"RSI {m.rsi:.1f} <= {RSI_OVERSOLD:.0f} (oversold, "
                       f"bounce potential, +0.15)")

    # --- volume dimension: confirmation, not direction ---
    ratio = m.volume / m.average_volume if m.average_volume else 0.0
    if ratio >= VOLUME_ANOMALY:
        confirm = 0.25 if score >= 0 else -0.25
        score += confirm
        reasons.append(f"Volume {ratio:.1f}x the 30-day average "
                       f"(>= {VOLUME_ANOMALY:.1f}x confirms the move, {confirm:+.2f})")
    else:
        reasons.append(f"Volume {ratio:.1f}x average — move is not volume-confirmed (0.00)")

    signal = "BULLISH" if score >= 0.25 else "BEARISH" if score <= -0.25 else "NEUTRAL"
    confidence = round(min(abs(score), 1.0), 2)
    reasons.append(f"Net score {score:+.2f} -> {signal} at confidence {confidence:.2f}")

    return AgentOutput(
        agent_name="market_detective", symbol=symbol, signal=signal,
        confidence=confidence, reasons=reasons, status="COMPLETE",
    )
