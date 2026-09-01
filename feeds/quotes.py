"""
Live quotes -> contracts.MarketData.

ADAPTER ORDER, and why it is this order:
  1. moneycontrol  keyless, live, and the only verified source that carries a
                   30-day average volume — which the volume dimension needs and
                   cannot be derived from a single quote
  2. twelvedata    only when TWELVEDATA_API_KEY is set. A licensed feed we can
                   actually point at in production
  3. cache         last known good, however old. Explicitly labelled stale
  4. fixture       the hand-written file, only in auto/fixtures mode

Every step down that ladder is reported: the returned MarketData carries
`source`, and quote_with_warnings() hands the caller a sentence to put in
data_quality.warnings. A fallback the user cannot see is a lie about freshness.

rsi/momentum/volatility are NOT set here. No keyless provider gives daily
candles, so they come from feeds.indicators over accumulated history, and stay
None until that history exists.
"""
import os
from typing import Optional

from contracts import MarketData
from feeds import FIXTURES, LIVE, cache, clock, http, mode, symbols

MC_QUOTE = "https://priceapi.moneycontrol.com/pricefeed/nse/equitycash/{scid}"
TD_QUOTE = "https://api.twelvedata.com/quote"


def _f(value, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return default


def _i(value, default: int = 0) -> int:
    return int(_f(value, default))


# ---- adapter 1: moneycontrol (keyless, verified) ----

async def _moneycontrol(symbol: str) -> Optional[dict]:
    ref = await symbols.resolve(symbol)
    if not ref or not ref.get("mc_scid"):
        return None
    payload = await http.fetch_json(MC_QUOTE.format(scid=ref["mc_scid"]))
    data = (payload or {}).get("data") if isinstance(payload, dict) else None
    if not data or not data.get("pricecurrent"):
        return None

    # Guard against the resolver having handed us the wrong company: the feed
    # echoes the NSE id back, so a mismatch is detectable rather than silent.
    # Compared against the id the EXCHANGE lists under, which is not always the
    # symbol people search by — NSE renamed ZOMATO to ETERNAL, and rejecting
    # that echo would silently drop a company from the watchlist.
    echoed = str(data.get("NSEID", "")).upper()
    expected = (ref.get("nse_id") or symbol).upper()
    if echoed and echoed != expected:
        return None

    return {
        "symbol": symbol.upper(),
        "company_name": data.get("SC_FULLNM") or ref.get("company_name", ""),
        "current_price": _f(data.get("pricecurrent")),
        "price_change": _f(data.get("pricechange")),
        "price_change_percent": _f(data.get("pricepercentchange")),
        "volume": _i(data.get("VOL")),
        # DVolAvg30 is the 30-day average traded quantity — exactly the
        # denominator volume_signal() compares against.
        "average_volume": max(_i(data.get("DVolAvg30")) or _i(data.get("VOL")), 1),
        "as_of": str(data.get("lastupd", "")),
        "source": "moneycontrol",
    }


# ---- adapter 2: twelvedata (licensed, keyed) ----

async def _twelvedata(symbol: str) -> Optional[dict]:
    key = os.getenv("TWELVEDATA_API_KEY", "").strip()
    if not key:
        return None
    payload = await http.fetch_json(
        TD_QUOTE, params={"symbol": symbol, "exchange": "NSE", "apikey": key})
    if not isinstance(payload, dict) or payload.get("status") == "error":
        return None
    close = _f(payload.get("close"))
    if not close:
        return None
    return {
        "symbol": symbol.upper(),
        "company_name": payload.get("name", ""),
        "current_price": close,
        "price_change": _f(payload.get("change")),
        "price_change_percent": _f(payload.get("percent_change")),
        "volume": _i(payload.get("volume")),
        "average_volume": max(_i(payload.get("average_volume")) or _i(payload.get("volume")), 1),
        "as_of": str(payload.get("datetime", "")),
        "source": "twelvedata",
    }


# ---- adapter 4: the hand-written fixture ----

def _fixture(symbol: str) -> Optional[dict]:
    import store
    m = store.fixture_snapshot(symbol)
    if m is None:
        return None
    d = m.model_dump()
    d["source"] = "fixture"
    d["as_of"] = d.get("as_of") or "hand-written fixture, not a live quote"
    return d


# ---- the ladder ----

async def quote_with_warnings(symbol: str) -> tuple[Optional[MarketData], list[str]]:
    """
    Returns (market_data, warnings). Never raises: a quote failure is a degraded
    dimension, not an error, and the caller is often mid-request.
    """
    symbol = symbol.upper()
    key = f"quote:{symbol}"
    warnings: list[str] = []

    if mode() != FIXTURES:
        fresh = cache.get(key, clock.quote_ttl_s())
        if fresh:
            return _finish(symbol, fresh, warnings)

        for adapter in (_moneycontrol, _twelvedata):
            try:
                raw = await adapter(symbol)
            except Exception as e:
                warnings.append(f"{adapter.__name__.strip('_')} quote failed for "
                                f"{symbol}: {type(e).__name__}")
                continue
            if raw:
                cache.put(key, raw)
                return _finish(symbol, raw, warnings)

        stale, age = cache.get_stale(key)
        if stale:
            mins = int(age // 60)
            stale = dict(stale, source=f"{stale.get('source', 'cache')} (cached)")
            warnings.append(f"Live quote unavailable for {symbol}; showing the last "
                            f"known price, {mins} minute(s) old.")
            return _finish(symbol, stale, warnings)

    if mode() == LIVE:
        warnings.append(f"No live quote for {symbol} and DATA_MODE=live forbids "
                        f"substituting the fixture.")
        return None, warnings

    raw = _fixture(symbol)
    if raw is None:
        return None, warnings + [f"No market data for {symbol}."]
    if mode() != FIXTURES:
        warnings.append(f"Live quote unavailable for {symbol}; fell back to the "
                        f"hand-written fixture, which is NOT a market price.")
    return _finish(symbol, raw, warnings)


# Observed on 2026-09-01: the NSE quote reported cumulative volume of 11.6M at
# 15:08 and 415k at 15:22 — a counter that went backwards mid-session, with BSE
# independently showing 712k. We cannot tell which reading is right, so we
# refuse to reason from either when the number is not credible. Passing a
# suspect figure through would produce a 0.04x ratio that reads as "nobody is
# trading this", which is a claim about the market rather than about our feed.
VOLUME_PLAUSIBILITY_FLOOR = 0.15


def session_progress() -> float:
    """
    How much of a trading day the reported volume should represent.

    Mid-session it is the fraction elapsed. Outside the session it is 1.0: a
    quote fetched after the close carries that day's completed total, and one
    fetched before the open carries the previous session's — either way a full
    day's worth. Skipping the check outside market hours, which is what this
    did first, meant the guard was off for most of the clock.
    """
    if not clock.is_session_open():
        return 1.0
    now = clock.now_ist()
    elapsed = (now.hour * 60 + now.minute) - (clock.OPEN.hour * 60 + clock.OPEN.minute)
    total = (clock.CLOSE.hour * 60 + clock.CLOSE.minute) - (clock.OPEN.hour * 60 + clock.OPEN.minute)
    return max(min(elapsed / total, 1.0), 0.05)


def _volume_is_credible(raw: dict, progress: float | None = None) -> tuple[bool, str]:
    """Compare reported volume against the 30-day average pro-rated by how much
    of the session has elapsed. Returns (ok, explanation)."""
    vol, avg = raw.get("volume", 0), raw.get("average_volume", 0)
    if vol <= 0 or avg <= 0:
        return False, "the feed reported no traded quantity"

    progress = session_progress() if progress is None else progress
    expected = avg * progress
    if vol < expected * VOLUME_PLAUSIBILITY_FLOOR:
        return False, (f"reported volume {vol:,} is under {VOLUME_PLAUSIBILITY_FLOOR:.0%} "
                       f"of the {expected:,.0f} implied by a {avg:,.0f} 30-day average "
                       f"{progress:.0%} of the way through the session")
    return True, ""


def _finish(symbol: str, raw: dict, warnings: list[str]) -> tuple[MarketData, list[str]]:
    """Attach the derived indicators and record today's close for tomorrow's."""
    from feeds import indicators

    raw = dict(raw)

    if raw.get("source") != "fixture":
        ok, why = _volume_is_credible(raw)
        if not ok:
            warnings.append(f"Volume dimension unavailable for {symbol}: {why}. "
                            f"The price dimension is unaffected.")
            raw["volume"] = 0
    if raw.get("source") not in ("fixture",) and raw.get("current_price"):
        cache.record_close(symbol, clock.session_date(),
                           raw["current_price"], raw.get("volume", 0))

    # A fixture carries its own hand-tuned indicators; a live quote does not,
    # and gets whatever the accumulated history can honestly support.
    if raw.get("source") != "fixture":
        raw["rsi"] = indicators.rsi(symbol)
        raw["momentum"] = indicators.momentum(symbol)
        raw["volatility"] = indicators.volatility(symbol)
        missing = [n for n in ("rsi", "momentum", "volatility") if raw[n] is None]
        if missing:
            warnings.append(
                f"{', '.join(missing)} unavailable for {symbol}: "
                f"{cache.close_count(symbol)} daily close(s) recorded so far. "
                f"Those terms are dropped from the price signal, not scored as neutral.")

    return MarketData.model_validate(raw), warnings


async def quote(symbol: str) -> Optional[MarketData]:
    md, _ = await quote_with_warnings(symbol)
    return md
