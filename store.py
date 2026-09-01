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
    rows = list(raw.values()) if isinstance(raw, dict) else list(raw)

    out = {}
    for row in rows:
        if "user" in row:                       # shape A
            user_fields, pf = dict(row["user"]), row.get("portfolio") or {}
        else:                                   # shape B — portfolio nested in the user
            user_fields = dict(row)
            pf = user_fields.pop("portfolio", {}) or {}
        u = UserProfile.model_validate(user_fields)
        out[u.user_id] = (u, Portfolio.model_validate(_derive(pf)))
    return out


def symbols() -> list[str]:
    """The symbol list the UI offers. Only symbols we have BOTH price and filings for."""
    from rag.ingest import available_symbols
    return sorted(set(market()) & set(available_symbols()))


def snapshot(symbol: str) -> Optional[MarketData]:
    return market().get(symbol.upper())
