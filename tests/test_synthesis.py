"""
tests/test_synthesis.py — Person 5's tests.

(Filename kept as originally scaffolded; content targets the actual
risk/ module per docs/ARCHITECTURE.md, not a BUY/HOLD synthesis layer
-- see docs/RISK_MODULE.md for why.)

Core requirement: SAME portfolio + SAME symbol + DIFFERENT risk_profile
=> DIFFERENT personalization output.
"""

import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from risk.profiles import build_personalization
from risk.portfolio import compute_stock_exposure, compute_concentration_score
from risk.simulation import run_scenario

PROFILES_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "profiles.json"
)


def load_profiles():
    with open(PROFILES_PATH, "r") as f:
        return json.load(f)


def test_personalization_differs_by_profile_same_portfolio():
    """
    Core personalization test: give the SAME portfolio and SAME symbol
    to a CONSERVATIVE and an AGGRESSIVE user_profile, and require
    different personalization output.
    """
    shared_portfolio = {
        "portfolio_value": 100000,
        "holdings": [
            {"symbol": "RELIANCE", "quantity": 1, "average_price": 30000, "current_value": 30000},
        ],
    }

    conservative_profile = {
        "risk_profile": "CONSERVATIVE",
        "risk_score": 20,
        "investment_horizon": "LONG_TERM",
    }
    aggressive_profile = {
        "risk_profile": "AGGRESSIVE",
        "risk_score": 85,
        "investment_horizon": "SHORT_TERM",
    }

    result_conservative = build_personalization(
        conservative_profile, shared_portfolio, "RELIANCE"
    )
    result_aggressive = build_personalization(
        aggressive_profile, shared_portfolio, "RELIANCE"
    )

    # Same stock_exposure number (0.30) ...
    assert result_conservative["stock_exposure"] == result_aggressive["stock_exposure"]

    # ... but a materially different explanation, because 30% breaches
    # the conservative ceiling (20%) and not the aggressive one (40%).
    assert result_conservative["personalized_reason"] != result_aggressive["personalized_reason"]
    assert "above the 20% single-stock ceiling" in result_conservative["personalized_reason"]
    assert "within the 40% single-stock ceiling" in result_aggressive["personalized_reason"]


def test_profiles_json_loads_and_produces_different_personalization():
    """
    Same idea, using the real data/profiles.json fixtures (u1
    conservative/concentrated, u2 aggressive/diversified).
    """
    profiles = load_profiles()
    u1, u2 = profiles["u1"], profiles["u2"]

    result_u1 = build_personalization(u1, u1["portfolio"], "RELIANCE")
    result_u2 = build_personalization(u2, u2["portfolio"], "RELIANCE")

    assert result_u1["risk_profile"] == "CONSERVATIVE"
    assert result_u2["risk_profile"] == "AGGRESSIVE"
    assert result_u1["personalized_reason"] != result_u2["personalized_reason"]

    # u1 is concentrated (~30% in RELIANCE) -> should breach conservative ceiling.
    assert result_u1["stock_exposure"] > 0.20
    assert "above the 20% single-stock ceiling" in result_u1["personalized_reason"]

    # u2 is diversified (~12% in RELIANCE) -> should be within aggressive ceiling.
    assert result_u2["stock_exposure"] < 0.20
    assert "within the 40% single-stock ceiling" in result_u2["personalized_reason"]


def test_stock_exposure_and_concentration_score():
    portfolio = {
        "portfolio_value": 100000,
        "holdings": [
            {"symbol": "AAA", "quantity": 1, "average_price": 50000, "current_value": 50000},
            {"symbol": "BBB", "quantity": 1, "average_price": 50000, "current_value": 50000},
        ],
    }
    assert compute_stock_exposure(portfolio, "AAA") == 0.5
    assert compute_stock_exposure(portfolio, "ZZZ") == 0.0
    # HHI for two 50/50 holdings: 0.5^2 + 0.5^2 = 0.5 -> concentration_score 50
    assert compute_concentration_score(portfolio) == 50


def test_personalization_never_crashes_on_bad_input():
    result = build_personalization({}, {}, "RELIANCE")
    assert result["risk_profile"] == "BALANCED"
    assert result["stock_exposure"] == 0.0
    assert "personalized_reason" in result

    result = build_personalization(None, None, None)
    assert "personalized_reason" in result


def test_scenario_simulation():
    portfolio = {
        "portfolio_value": 500000,
        "holdings": [
            {"symbol": "RELIANCE", "quantity": 42, "average_price": 2600, "current_value": 119700},
        ],
    }
    result = run_scenario(portfolio, "RELIANCE", "BEAR_CASE")
    assert result["scenario"] == "BEAR_CASE"
    assert result["scenario_change_percent"] == -10
    assert result["stock_impact"] == -11970.0
    assert result["portfolio_impact"] == -11970.0
    assert result["portfolio_impact_percent"] == round(-11970.0 / 500000 * 100, 2)


def test_scenario_never_crashes_on_bad_input():
    result = run_scenario({}, "RELIANCE", "CRASH")
    assert result["stock_impact"] == 0.0
    assert result["portfolio_impact_percent"] == 0.0


if __name__ == "__main__":
    tests = [
        test_personalization_differs_by_profile_same_portfolio,
        test_profiles_json_loads_and_produces_different_personalization,
        test_stock_exposure_and_concentration_score,
        test_personalization_never_crashes_on_bad_input,
        test_scenario_simulation,
        test_scenario_never_crashes_on_bad_input,
    ]
    for t in tests:
        t()
        print(f"PASS: {t.__name__}")
    print(f"\n{len(tests)} tests passed.")
