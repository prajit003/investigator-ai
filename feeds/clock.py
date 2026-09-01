"""
NSE session awareness.

Two things depend on it: how long a quote may be cached (a price does not move
after 15:30 IST, so a 60-second TTL out of hours is pure waste and pure load on
someone else's server), and whether the UI should label a figure "live" or
"last close".

IST is UTC+5:30 with no daylight saving, so a fixed offset is correct rather
than merely convenient.
"""
from datetime import datetime, time as _time, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
OPEN = _time(9, 15)
CLOSE = _time(15, 30)


def now_ist() -> datetime:
    return datetime.now(IST)


def is_session_open(at: datetime | None = None) -> bool:
    """True during NSE continuous trading. Weekends are closed; exchange
    holidays are not modelled — a holiday simply looks like a session in which
    nothing traded, and the provider's own timestamp gives it away."""
    at = at or now_ist()
    if at.weekday() >= 5:
        return False
    return OPEN <= at.time() <= CLOSE


def quote_ttl_s(at: datetime | None = None) -> float:
    """60s while the market is open, 15 min when it is not."""
    return 60.0 if is_session_open(at) else 900.0


def session_date(at: datetime | None = None) -> str:
    """The trading date to file a close under, as YYYY-MM-DD."""
    return (at or now_ist()).strftime("%Y-%m-%d")


def describe(at: datetime | None = None) -> str:
    at = at or now_ist()
    return ("market open" if is_session_open(at)
            else f"market closed ({at.strftime('%a %H:%M')} IST)")
