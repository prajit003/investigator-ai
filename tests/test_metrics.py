import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from models import AgentOutput, UserProfile
from orchestrator import calculate_metrics


def main():

    agents = [
        AgentOutput(
            agent_name="technical",
            ticker="RELIANCE",
            status="OK",
            signal="BULLISH",
            confidence=0.80,
            reasoning="Technical signal.",
            citations=[]
        ),

        AgentOutput(
            agent_name="volume",
            ticker="RELIANCE",
            status="OK",
            signal="BEARISH",
            confidence=0.60,
            reasoning="Volume signal.",
            citations=[]
        ),

        AgentOutput.unavailable(
            "sentiment",
            "RELIANCE",
            "not implemented yet"
        ),

        AgentOutput.unavailable(
            "fundamental",
            "RELIANCE",
            "not implemented yet"
        ),
    ]

    profile = UserProfile(
        user_id="u1",
        name="Alex",
        risk_profile="CONSERVATIVE",
        investment_horizon="LONG_TERM",
        portfolio_value=500000,
        max_holding_pct=24
    )

    metrics = calculate_metrics(
        agents,
        150.0,
        profile
    )

    print("===== METRICS TEST =====")
    print(metrics.model_dump())

    assert metrics.total_latency_ms == 150.0
    assert metrics.avg_confidence == 0.70
    assert metrics.concentration_score == 24
    assert metrics.agents_ok == 2
    assert metrics.agents_failed == 2

    print()
    print("ALL METRICS TESTS PASSED")


if __name__ == "__main__":
    main()