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
