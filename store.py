"""Loads the on-disk fixtures once and validates them. Import this, never open() a path."""
import json, pathlib
from functools import lru_cache
from typing import Optional
from contracts import MarketData, Portfolio, UserProfile

BASE = pathlib.Path(__file__).resolve().parent


def _read(rel: str):
    p = BASE / rel
    if not p.exists():
        return []
    return json.loads(p.read_text() or "[]")


@lru_cache(maxsize=1)
def market() -> dict[str, MarketData]:
    return {m["symbol"].upper(): MarketData.model_validate(m)
            for m in _read("data/market/market.json")}


@lru_cache(maxsize=1)
def profiles() -> dict[str, tuple[UserProfile, Portfolio]]:
    out = {}
    for row in _read("data/profiles.json"):
        u = UserProfile.model_validate(row["user"])
        out[u.user_id] = (u, Portfolio.model_validate(row["portfolio"]))
    return out


def symbols() -> list[str]:
    """The symbol list the UI offers. Only symbols we have BOTH price and filings for."""
    from rag.ingest import available_symbols
    return sorted(set(market()) & set(available_symbols()))


def snapshot(symbol: str) -> Optional[MarketData]:
    return market().get(symbol.upper())
