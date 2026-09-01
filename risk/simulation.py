"""
risk/simulation.py — Person 5's what-if simulator.

Produces the `scenario` object (docs/ARCHITECTURE.md, section 11):

    {
        "scenario": "BEAR_CASE",
        "scenario_change_percent": -10,
        "stock_impact": -12000,
        "portfolio_impact": -12000,
        "portfolio_impact_percent": -2.4
    }

Scope, deliberately simple for a hackathon: a single-stock price
shock applied to that stock's current holding value. Other holdings
are assumed unaffected (no cross-asset correlation modeling).
"""

from typing import Any, Dict

from risk.portfolio import _safe_holdings, _safe_portfolio_value  # noqa: F401 (reuse safe helpers)

PRESET_SCENARIOS: Dict[str, float] = {
    "BULL_CASE": 15,
    "BASE_CASE": 0,
    "BEAR_CASE": -10,
    "CRASH": -25,
}


def _holding_value_for_symbol(portfolio: Dict[str, Any], symbol: str) -> float:
    total = 0.0
    for h in _safe_holdings(portfolio):
        if str(h.get("symbol", "")).upper() == str(symbol or "").upper():
            try:
                total += float(h.get("current_value", 0) or 0)
            except (TypeError, ValueError):
                continue
    return total


def run_scenario(
    portfolio: Dict[str, Any],
    symbol: str,
    scenario: str,
    scenario_change_percent: float = None,
) -> Dict[str, Any]:
    """
    Applies a price-change scenario to `symbol`'s current holding and
    measures the resulting dollar/percent impact on the whole portfolio.

    If `scenario_change_percent` is omitted, falls back to the preset
    for `scenario` (see PRESET_SCENARIOS), defaulting to 0 if unknown.

    Never crashes: any missing/malformed input degrades to a
    zero-impact result rather than raising.
    """
    try:
        change_pct = (
            float(scenario_change_percent)
            if scenario_change_percent is not None
            else float(PRESET_SCENARIOS.get(str(scenario or "").upper(), 0))
        )

        portfolio_value = _safe_portfolio_value(portfolio)
        held_value = _holding_value_for_symbol(portfolio, symbol)

        stock_impact = round(held_value * (change_pct / 100.0), 2)
        # Other holdings assumed unaffected in this simple model.
        portfolio_impact = stock_impact
        portfolio_impact_percent = (
            round((portfolio_impact / portfolio_value) * 100, 2)
            if portfolio_value > 0
            else 0.0
        )

        return {
            "scenario": str(scenario or "CUSTOM").upper(),
            "scenario_change_percent": change_pct,
            "stock_impact": stock_impact,
            "portfolio_impact": portfolio_impact,
            "portfolio_impact_percent": portfolio_impact_percent,
        }
    except Exception:
        return {
            "scenario": str(scenario or "CUSTOM").upper(),
            "scenario_change_percent": 0,
            "stock_impact": 0.0,
            "portfolio_impact": 0.0,
            "portfolio_impact_percent": 0.0,
        }
