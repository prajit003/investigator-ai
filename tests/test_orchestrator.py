import sys
from pathlib import Path

# Allow imports from the project root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import asyncio

from models import MarketSnapshot
from orchestrator import run_all_agents


# --------------------------------------------------
# Test market snapshot
# --------------------------------------------------

snapshot = MarketSnapshot(
    ticker="RELIANCE",
    current_price=2850.0,
    price_change_percent=-3.8,
    volume=3200000,
    average_volume=1000000,
    rsi=31.0,
    momentum=-0.18,
    volatility=0.27,
    sentiment_score=-0.41
)


# --------------------------------------------------
# Test
# --------------------------------------------------

async def main():

    print("=" * 50)
    print("TESTING AGENT ORCHESTRATOR")
    print("=" * 50)

    agent_outputs, total_latency_ms = (
        await run_all_agents(
            "RELIANCE",
            snapshot
        )
    )

    print()
    print("Total latency:")
    print(f"{total_latency_ms:.2f} ms")

    print()
    print("Agent results:")
    print("-" * 50)

    for agent in agent_outputs:

        print(
            f"{agent.agent_name:15}"
            f" | status={agent.status:12}"
            f" | signal={agent.signal:12}"
            f" | confidence={agent.confidence}"
        )

    print("-" * 50)

    assert len(agent_outputs) == 4

    expected_agents = {
        "technical",
        "volume",
        "sentiment",
        "fundamental",
    }

    actual_agents = {
        agent.agent_name
        for agent in agent_outputs
    }

    assert actual_agents == expected_agents

    print()
    print("PASS: All four agents returned results.")
    print("PASS: Orchestrator completed successfully.")


# --------------------------------------------------
# Entry point
# --------------------------------------------------

if __name__ == "__main__":
    asyncio.run(main())