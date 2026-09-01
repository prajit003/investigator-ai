"""
risk/profiles.py — Person 5's risk-profile rules.

Produces the `personalization` object (docs/ARCHITECTURE.md, section 10):

    {
        "risk_profile": "CONSERVATIVE",
        "risk_score": 25,
        "investment_horizon": "LONG_TERM",
        "stock_exposure": 0.24,
        "personalized_reason": "High concentration increases your downside risk."
    }

IMPORTANT — this module does NOT decide BUY/SELL/HOLD. Per
ARCHITECTURE.md: "Do not use BUY/SELL as the primary verdict."
That verdict (STRONG_POSITIVE / POSITIVE / CAUTION / NEGATIVE /
INSUFFICIENT_DATA) is produced by the Judge Agent (agents/judge_agent.py).

This module only decides how a user's risk profile should color the
*interpretation* of whatever the Judge already said, via
`personalized_reason` — using deterministic Python rules (not an LLM),
so the same portfolio + market data reliably produces different
personalization text for different risk profiles.

Allowed risk_profile values (ARCHITECTURE.md section 1):
    "CONSERVATIVE", "BALANCED", "AGGRESSIVE"
"""

from typing import Any, Dict

from risk.portfolio import compute_stock_exposure, compute_concentration_score

# Deterministic per-tier thresholds. Tuned so the SAME portfolio/exposure
# can trigger a warning for a CONSERVATIVE user while staying comfortable
# for an AGGRESSIVE one -- this is what makes personalization observable.
RISK_PROFILE_RULES: Dict[str, Dict[str, float]] = {
    "CONSERVATIVE": {
        "single_stock_exposure_ceiling": 0.20,   # 20%
        "concentration_score_ceiling": 20,
    },
    "BALANCED": {
        "single_stock_exposure_ceiling": 0.30,   # 30%
        "concentration_score_ceiling": 30,
    },
    "AGGRESSIVE": {
        "single_stock_exposure_ceiling": 0.40,   # 40%
        "concentration_score_ceiling": 45,
    },
}

DEFAULT_RISK_PROFILE = "BALANCED"


def _normalize_risk_profile(risk_profile: Any) -> str:
    value = str(risk_profile or "").upper().strip()
    return value if value in RISK_PROFILE_RULES else DEFAULT_RISK_PROFILE


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def build_personalized_reason(
    risk_profile: str,
    symbol: str,
    stock_exposure: float,
    concentration_score: int,
) -> str:
    """
    Deterministic, numbers-explicit explanation of how this user's
    risk profile relates to their current exposure. Never vague.
    """
    rules = RISK_PROFILE_RULES[risk_profile]
    exposure_ceiling = rules["single_stock_exposure_ceiling"]
    concentration_ceiling = rules["concentration_score_ceiling"]

    exposure_pct = round(stock_exposure * 100, 1)
    exposure_ceiling_pct = round(exposure_ceiling * 100)

    reasons = []

    if stock_exposure > exposure_ceiling:
        reasons.append(
            f"Your {symbol} position is {exposure_pct}% of your portfolio, "
            f"above the {exposure_ceiling_pct}% single-stock ceiling for "
            f"{'an' if risk_profile[:1].upper() in 'AEIOU' else 'a'} "
            f"{risk_profile.title()} investor. This concentration increases "
            f"your downside risk if {symbol} underperforms."
        )
    else:
        reasons.append(
            f"Your {symbol} position is {exposure_pct}% of your portfolio, "
            f"within the {exposure_ceiling_pct}% single-stock ceiling for "
            f"{'an' if risk_profile[:1].upper() in 'AEIOU' else 'a'} "
            f"{risk_profile.title()} investor."
        )

    if concentration_score > concentration_ceiling:
        reasons.append(
            f"Overall portfolio concentration is {concentration_score}/100, "
            f"above the {concentration_ceiling}/100 ceiling for this profile, "
            f"meaning the portfolio as a whole is less diversified than "
            f"recommended."
        )

    return " ".join(reasons)


def build_personalization(
    user_profile: Dict[str, Any],
    portfolio: Dict[str, Any],
    symbol: str,
) -> Dict[str, Any]:
    """
    Main entry point. Builds the `personalization` object.

    Must never crash: falls back to safe defaults for any missing or
    malformed field, since this feeds the frontend directly.
    """
    try:
        risk_profile = _normalize_risk_profile(user_profile.get("risk_profile"))
        risk_score = _safe_int(user_profile.get("risk_score"), default=50)
        investment_horizon = str(
            user_profile.get("investment_horizon") or "MEDIUM_TERM"
        ).upper()

        stock_exposure = compute_stock_exposure(portfolio, symbol)
        concentration_score = compute_concentration_score(portfolio)

        personalized_reason = build_personalized_reason(
            risk_profile, symbol, stock_exposure, concentration_score
        )

        return {
            "risk_profile": risk_profile,
            "risk_score": risk_score,
            "investment_horizon": investment_horizon,
            "stock_exposure": stock_exposure,
            "personalized_reason": personalized_reason,
        }
    except Exception:
        # Deterministic, never-crash fallback.
        return {
            "risk_profile": DEFAULT_RISK_PROFILE,
            "risk_score": 50,
            "investment_horizon": "MEDIUM_TERM",
            "stock_exposure": 0.0,
            "personalized_reason": (
                "Personalization unavailable due to incomplete portfolio "
                "or profile data; showing default risk settings."
            ),
        }
