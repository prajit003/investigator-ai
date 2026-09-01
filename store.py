"""
The data router. Import this, never open() a path.

It used to be a fixture loader; it is now a router with the fixture loader still
inside it as the bottom rung. Callers ask for a snapshot and get whatever the
current DATA_MODE can honestly provide — live, cached, or hand-written — and a
list of warnings naming every step down that ladder.
"""
import json
import pathlib
from functools import lru_cache
from typing import Optional

import feeds
from contracts import MarketData, Portfolio, UserProfile

BASE = pathlib.Path(__file__).resolve().parent


def _read(rel: str):
    p = BASE / rel
    if not p.exists():
        return []
    return json.loads(p.read_text() or "[]")


@lru_cache(maxsize=1)
def market() -> dict[str, MarketData]:
    """The hand-written fixture set. Not the live feed — see snapshot()."""
    return {m["symbol"].upper(): MarketData.model_validate(m)
            for m in _read("data/market/market.json")}


def _derive(pf: dict) -> dict:
    """Fill portfolio figures that can be computed from the holdings.

    concentration_score is DERIVED, never trusted from the file: a stale
    hand-written number silently breaks the conservative downgrade rule.
    """
    pf = dict(pf)
    holdings = pf.get("holdings") or []
    total = pf.get("portfolio_value") or sum(h.get("current_value", 0) for h in holdings)
    pf["portfolio_value"] = total
    if holdings and total:
        top = max(h.get("current_value", 0) for h in holdings)
        pf["concentration_score"] = round(top / total * 100, 2)
        pf.setdefault("stock_exposure", round(top / total, 4))
    return pf


@lru_cache(maxsize=1)
def profiles() -> dict[str, tuple[UserProfile, Portfolio]]:
    """
    Accepts BOTH on-disk shapes, so a teammate reshaping this file cannot
    take the pipeline down again:

      A) [{"user": {...}, "portfolio": {...}}, ...]
      B) {"u1": {...user fields..., "portfolio": {...}}, ...}
    """
    raw = _read("data/profiles.json")
    if isinstance(raw, dict):
        # Skip "_comment" and friends: a data file is allowed to explain itself,
        # and an underscore key is documentation, not a user.
        rows = [v for k, v in raw.items() if not str(k).startswith("_")]
    else:
        rows = list(raw)

    out = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        if "user" in row:                       # shape A
            user_fields, pf = dict(row["user"]), row.get("portfolio") or {}
        else:                                   # shape B — portfolio nested in the user
            user_fields = dict(row)
            pf = user_fields.pop("portfolio", {}) or {}
        u = UserProfile.model_validate(user_fields)
        out[u.user_id] = (u, Portfolio.model_validate(_derive(pf)))
    return out


def symbols() -> list[str]:
    """
    The symbol list the UI offers.

    Fixture mode keeps the original rule — only symbols we have BOTH a price and
    filings for, so the UI never offers one that returns empty evidence. With a
    live feed both are fetchable on demand, so the watchlist is the universe.
    """
    from rag.ingest import available_symbols

    if feeds.offline():
        return sorted(set(market()) & set(available_symbols()))

    from feeds.symbols import watchlist
    live = watchlist()
    return live or sorted(set(market()) & set(available_symbols()))


def fixture_snapshot(symbol: str) -> Optional[MarketData]:
    """The hand-written snapshot only. feeds.quotes calls this as its last rung."""
    return market().get(symbol.upper())


async def snapshot_with_warnings(symbol: str) -> tuple[Optional[MarketData], list[str]]:
    """
    The live path. Returns (market_data, warnings); never raises.

    In fixtures mode this resolves to exactly the old behaviour, which is what
    keeps validate.py and CI deterministic and offline.
    """
    from feeds.quotes import quote_with_warnings
    return await quote_with_warnings(symbol)


async def snapshot(symbol: str) -> Optional[MarketData]:
    md, _ = await snapshot_with_warnings(symbol)
    return md
