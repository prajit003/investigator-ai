"""
Technical indicators, computed from accumulated daily closes.

WHY WE ACCUMULATE OUR OWN HISTORY: none of the keyless providers that answer us
will hand over daily candles. Moneycontrol's chart endpoint returns 403, NSE
returns 403, Yahoo returns 429, and stooq wants a JavaScript proof-of-work. So
the system records one close per symbol per session and grows its own series.

The consequence is deliberate and is the honest one: on day one there is no RSI,
and every function here returns None rather than a plausible-looking number.
None means MISSING (docs/ARCHITECTURE.md §15.2) — the price agent drops the term
and says so. A seeded default of 50.0 would let an indicator we do not have cast
a vote, which is the exact failure this codebase rejects everywhere else.

If TWELVEDATA_API_KEY is set, seed_history() backfills real candles in one call
and every indicator below becomes available immediately.
"""
import math
import os
from typing import Optional

from feeds import cache, clock, http

RSI_PERIOD = 14
MOMENTUM_LOOKBACK = 20          # ~1 trading month
VOLATILITY_LOOKBACK = 20
TRADING_DAYS = 252

TD_SERIES = "https://api.twelvedata.com/time_series"


def rsi(symbol: str, period: int = RSI_PERIOD) -> Optional[float]:
    """
    Wilder's RSI. Needs period+1 closes to produce even one value; returns None
    below that rather than a partial-window figure dressed up as a real one.
    """
    closes = cache.closes(symbol, limit=period * 6)
    if len(closes) < period + 1:
        return None

    deltas = [b - a for a, b in zip(closes, closes[1:])]
    gains = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    # Wilder smoothing over whatever history exists beyond the first window.
    for g, l in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l) / period

    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 2)


def momentum(symbol: str, lookback: int = MOMENTUM_LOOKBACK) -> Optional[float]:
    """
    Fractional return over the lookback window, matching the scale the price
    agent's MOMENTUM_STRONG=0.10 threshold was written against (0.18 = +18%).
    """
    closes = cache.closes(symbol, limit=lookback + 1)
    if len(closes) < lookback + 1 or not closes[0]:
        return None
    return round((closes[-1] - closes[0]) / closes[0], 4)


def volatility(symbol: str, lookback: int = VOLATILITY_LOOKBACK) -> Optional[float]:
    """Annualised standard deviation of daily log returns."""
    closes = cache.closes(symbol, limit=lookback + 1)
    if len(closes) < lookback + 1:
        return None
    rets = [math.log(b / a) for a, b in zip(closes, closes[1:]) if a > 0 and b > 0]
    if len(rets) < 2:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return round(math.sqrt(var) * math.sqrt(TRADING_DAYS), 4)


def coverage(symbol: str) -> dict:
    """What the history can currently support. Used in reasons and warnings."""
    n = cache.close_count(symbol)
    return {"closes": n,
            "rsi": n >= RSI_PERIOD + 1,
            "momentum": n >= MOMENTUM_LOOKBACK + 1,
            "volatility": n >= VOLATILITY_LOOKBACK + 1}


async def seed_history(symbol: str, days: int = 90) -> int:
    """
    Backfill daily closes from a licensed provider, when one is configured.
    Returns the number of closes written (0 if there is no key or it failed).

    This is the difference between "indicators appear in three weeks" and
    "indicators work now", and it is the reason the keyed adapter exists.
    """
    key = os.getenv("TWELVEDATA_API_KEY", "").strip()
    if not key:
        return 0
    try:
        payload = await http.fetch_json(TD_SERIES, params={
            "symbol": symbol, "exchange": "NSE", "interval": "1day",
            "outputsize": str(days), "apikey": key, "order": "ASC"})
    except Exception:
        return 0
    values = payload.get("values") if isinstance(payload, dict) else None
    if not values:
        return 0

    written = 0
    for row in values:
        try:
            cache.record_close(symbol, str(row["datetime"])[:10],
                               float(row["close"]), int(float(row.get("volume") or 0)))
            written += 1
        except (KeyError, TypeError, ValueError):
            continue
    return written


if __name__ == "__main__":
    import sys
    sym = (sys.argv[1] if len(sys.argv) > 1 else "RELIANCE").upper()
    print(f"{sym}  {clock.describe()}")
    print(f"  coverage   {coverage(sym)}")
    print(f"  rsi        {rsi(sym)}")
    print(f"  momentum   {momentum(sym)}")
    print(f"  volatility {volatility(sym)}")
