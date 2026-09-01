import sys
from pathlib import Path

# Allow the test to import files from the project root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import asyncio

from models import MarketSnapshot, AgentOutput
from safety import run_agent_safely


# --------------------------------------------------
# Shared test snapshot
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
# Test 1: Working agent
# --------------------------------------------------

async def working_agent(
    ticker: str,
    snapshot: MarketSnapshot
) -> AgentOutput:

    return AgentOutput(
        agent_name="test",
        ticker=ticker,
        status="OK",
        signal="BULLISH",
        confidence=0.80,
        reasoning="Test agent worked successfully.",
        citations=[]
    )


# --------------------------------------------------
# Test 2: Broken agent
# --------------------------------------------------

async def broken_agent(
    ticker: str,
    snapshot: MarketSnapshot
) -> AgentOutput:

    raise RuntimeError("Intentional test failure")


# --------------------------------------------------
# Test 3: Slow agent
# --------------------------------------------------

async def slow_agent(
    ticker: str,
    snapshot: MarketSnapshot
) -> AgentOutput:

    await asyncio.sleep(10)

    return AgentOutput(
        agent_name="slow",
        ticker=ticker,
        status="OK",
        signal="NEUTRAL",
        confidence=0.50,
        reasoning="This agent should not finish before timeout.",
        citations=[]
    )


# --------------------------------------------------
# Run all tests
# --------------------------------------------------

async def main():

    # ----------------------------------------------
    # Working agent test
    # ----------------------------------------------

    print("Testing working agent...")

    result = await run_agent_safely(
        working_agent,
        "test_working",
        "RELIANCE",
        snapshot
    )

    print(result.model_dump())

    assert result.status == "OK"

    print("PASS: Working agent returned OK\n")


    # ----------------------------------------------
    # Broken agent test
    # ----------------------------------------------

    print("Testing broken agent...")

    result = await run_agent_safely(
        broken_agent,
        "test_broken",
        "RELIANCE",
        snapshot
    )

    print(result.model_dump())

    assert result.status == "UNAVAILABLE"
    assert result.signal == "UNAVAILABLE"

    print("PASS: Broken agent became UNAVAILABLE\n")


    # ----------------------------------------------
    # Timeout test
    # ----------------------------------------------

    print("Testing slow agent...")
    print("Waiting for safety timeout...")

    result = await run_agent_safely(
        slow_agent,
        "test_slow",
        "RELIANCE",
        snapshot
    )

    print(result.model_dump())

    assert result.status == "UNAVAILABLE"
    assert result.signal == "UNAVAILABLE"
    assert "timed out" in result.reasoning

    print("PASS: Slow agent timed out safely\n")


    # ----------------------------------------------
    # Final result
    # ----------------------------------------------

    print("========================================")
    print("ALL SAFETY TESTS PASSED")
    print("========================================")


# --------------------------------------------------
# Entry point
# --------------------------------------------------

if __name__ == "__main__":
    asyncio.run(main())