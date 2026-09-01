"""
risk/portfolio.py — portfolio math for Person 5.

Shared variable names (from docs/ARCHITECTURE.md, section 9):

    portfolio
    portfolio_value
    holdings
    sector_exposure
    stock_exposure
    concentration_score

`portfolio` shape (as produced/consumed elsewhere in the app):

    {
        "portfolio_value": 500000,
        "holdings": [
            {"symbol": "RELIANCE", "quantity": 42, "average_price": 2600, "current_value": 119700},
            ...
        ]
    }

This file never crashes. Missing/malformed portfolios degrade to
safe zero-exposure defaults rather than raising, since portfolio
math feeds directly into personalization/UI text.
"""

from typing import Any, Dict, List


def _safe_holdings(portfolio: Dict[str, Any]) -> List[Dict[str, Any]]:
    holdings = portfolio.get("holdings") if isinstance(portfolio, dict) else None
    return holdings if isinstance(holdings, list) else []


def _safe_portfolio_value(portfolio: Dict[str, Any]) -> float:
    try:
        value = float(portfolio.get("portfolio_value", 0) or 0)
    except (TypeError, ValueError):
        value = 0.0
    if value > 0:
        return value

    # Fall back to summing holdings if portfolio_value is missing/zero.
    total = 0.0
    for h in _safe_holdings(portfolio):
        try:
            total += float(h.get("current_value", 0) or 0)
        except (TypeError, ValueError):
            continue
    return total


def compute_stock_exposure(portfolio: Dict[str, Any], symbol: str) -> float:
    """
    Fraction (0.0-1.0) of the portfolio held in `symbol`.
    Matches the `stock_exposure` field in the ARCHITECTURE.md
    `personalization` example (e.g. 0.24).
    """
    portfolio_value = _safe_portfolio_value(portfolio)
    if portfolio_value <= 0:
        return 0.0

    held_value = 0.0
    for h in _safe_holdings(portfolio):
        if str(h.get("symbol", "")).upper() == str(symbol or "").upper():
            try:
                held_value += float(h.get("current_value", 0) or 0)
            except (TypeError, ValueError):
                continue

    exposure = held_value / portfolio_value
    return round(max(0.0, min(exposure, 1.0)), 4)


def compute_concentration_score(portfolio: Dict[str, Any]) -> int:
    """
    Portfolio-wide concentration, 0-100, using a Herfindahl-Hirschman
    Index (sum of squared position weights * 100).

    A single 100%-weight holding scores 100. Many small, even
    positions score close to 0. This is deliberately a *whole
    portfolio* metric, distinct from `stock_exposure`, which is
    scoped to one symbol.
    """
    portfolio_value = _safe_portfolio_value(portfolio)
    if portfolio_value <= 0:
        return 0

    hhi = 0.0
    for h in _safe_holdings(portfolio):
        try:
            weight = float(h.get("current_value", 0) or 0) / portfolio_value
        except (TypeError, ValueError, ZeroDivisionError):
            continue
        hhi += weight * weight

    return round(min(hhi, 1.0) * 100)


def build_portfolio_summary(portfolio: Dict[str, Any]) -> Dict[str, Any]:
    """
    Assembles the `portfolio` master object exactly as shaped in
    ARCHITECTURE.md section 9, filling in the derived fields.
    """
    portfolio_value = _safe_portfolio_value(portfolio)
    holdings = _safe_holdings(portfolio)

    return {
        "portfolio_value": portfolio_value,
        "holdings": holdings,
        "concentration_score": compute_concentration_score(portfolio),
    }


async def mark_to_market(portfolio, quote_fn=None):
    """
    Reprice a Portfolio against live quotes.

    The stored `current_value` per holding was written once by hand. Once prices
    are live, leaving it alone means concentration_score — the number the
    conservative downgrade rule turns on — is computed from history rather than
    from what the position is worth now.

    Takes and returns a contracts.Portfolio. Never raises, and never partially
    reprices: a holding whose quote is missing keeps its stored value and says
    so in the returned warnings, because silently mixing live and stale values
    into one concentration figure would be worse than either alone.
    """
    from contracts import Portfolio
    import store

    if quote_fn is None:
        from feeds.quotes import quote as quote_fn

    if portfolio is None or not portfolio.holdings:
        return portfolio, []

    import asyncio

    async def _quote(sym: str):
        try:
            return await quote_fn(sym)
        except Exception:
            return None

    # Concurrently: a ten-holding portfolio priced one symbol at a time is ten
    # round trips in series before the agents have even started. The feed layer
    # still rate-limits per host, so this overlaps the waiting, not the load.
    quotes = await asyncio.gather(*(_quote(h.symbol) for h in portfolio.holdings))

    warnings: List[str] = []
    priced, stale = [], []
    for h, md in zip(portfolio.holdings, quotes):
        row = h.model_dump()
        if md and md.current_price and h.quantity:
            row["current_value"] = round(md.current_price * h.quantity, 2)
        elif h.symbol:
            stale.append(h.symbol)
        priced.append(row)

    if stale:
        warnings.append(f"Portfolio values for {', '.join(sorted(set(stale)))} are the "
                        f"stored figures, not live: no quote was available. "
                        f"Concentration mixes live and stored values.")

    pf = dict(portfolio.model_dump(), holdings=priced)
    # portfolio_value must be re-derived, not kept: it is the denominator of
    # every exposure figure, and holding it fixed while the numerators move
    # would make concentration drift with the market for no reason.
    pf["portfolio_value"] = round(sum(h["current_value"] for h in priced), 2)
    pf.pop("concentration_score", None)
    pf.pop("stock_exposure", None)
    # Reuse store._derive so concentration is computed in exactly one place.
    return Portfolio.model_validate(store._derive(pf)), warnings
