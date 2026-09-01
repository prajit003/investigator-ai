import asyncio
import importlib
import os
import time
from typing import Any

from models import (
    AgentOutput,
    MarketSnapshot,
    UserProfile,
    Metrics,
)

from safety import run_agent_safely


# --------------------------------------------------
# Agent configuration
# --------------------------------------------------

AGENT_MODULES = {
    "technical": "agents.technical",
    "volume": "agents.volume",
    "sentiment": "agents.sentiment",
    "fundamental": "agents.fundamental",
}


# --------------------------------------------------
# Load an agent module
# --------------------------------------------------

def load_agent_module(agent_name: str):
    """
    Dynamically load an agent module.

    If the module does not exist yet, return None.
    This allows the backend to run while teammates
    are still implementing their agents.
    """

    module_name = AGENT_MODULES[agent_name]

    try:
        return importlib.import_module(module_name)

    except ImportError:
        return None


# --------------------------------------------------
# Run one agent safely
# --------------------------------------------------

async def run_one_agent(
    agent_name: str,
    ticker: str,
    snapshot: MarketSnapshot,
) -> AgentOutput:

    # --------------------------------------------------
    # KILL_AGENT demo
    # --------------------------------------------------

    kill_agent = os.getenv("KILL_AGENT", "").lower()

    if kill_agent == agent_name:
        async def killed_agent(
            ticker: str,
            snapshot: MarketSnapshot
        ):
            raise RuntimeError(
                f"{agent_name} intentionally killed "
                "for degraded-data testing"
            )

        return await run_agent_safely(
            killed_agent,
            agent_name,
            ticker,
            snapshot
        )

    # --------------------------------------------------
    # Load the actual agent
    # --------------------------------------------------

    module = load_agent_module(agent_name)

    if module is None:
        return AgentOutput.unavailable(
            agent_name,
            ticker,
            "not implemented yet"
        )

    # --------------------------------------------------
    # Verify run() exists
    # --------------------------------------------------

    if not hasattr(module, "run"):
        return AgentOutput.unavailable(
            agent_name,
            ticker,
            "agent run() function not implemented"
        )

    # --------------------------------------------------
    # Run through safety wrapper
    # --------------------------------------------------

    return await run_agent_safely(
        module.run,
        agent_name,
        ticker,
        snapshot
    )


# --------------------------------------------------
# Run all four agents concurrently
# --------------------------------------------------

async def run_all_agents(
    ticker: str,
    snapshot: MarketSnapshot,
) -> tuple[list[AgentOutput], float]:

    start_time = time.perf_counter()

    # IMPORTANT:
    # asyncio.gather() runs all four agent tasks
    # concurrently rather than one after another.

    agent_outputs = await asyncio.gather(
        run_one_agent(
            "technical",
            ticker,
            snapshot
        ),

        run_one_agent(
            "volume",
            ticker,
            snapshot
        ),

        run_one_agent(
            "sentiment",
            ticker,
            snapshot
        ),

        run_one_agent(
            "fundamental",
            ticker,
            snapshot
        ),
    )

    end_time = time.perf_counter()

    # Wall-clock time for the complete gather.
    total_latency_ms = (
        end_time - start_time
    ) * 1000

    return agent_outputs, total_latency_ms


# --------------------------------------------------
# Calculate metrics
# --------------------------------------------------

def calculate_metrics(
    agent_outputs: list[AgentOutput],
    total_latency_ms: float,
    profile: UserProfile,
) -> Metrics:

    successful_agents = [
        agent
        for agent in agent_outputs
        if agent.status == "OK"
    ]

    failed_agents = [
        agent
        for agent in agent_outputs
        if agent.status != "OK"
    ]

    # Average confidence ONLY from successful agents.
    if successful_agents:
        avg_confidence = (
            sum(
                agent.confidence
                for agent in successful_agents
            )
            / len(successful_agents)
        )
    else:
        avg_confidence = 0.0

    # Highest holding percentage in the profile.
    concentration_score = profile.max_holding_pct

    return Metrics(
        total_latency_ms=round(
            total_latency_ms,
            2
        ),

        avg_confidence=round(
            avg_confidence,
            4
        ),

        concentration_score=concentration_score,

        agents_ok=len(successful_agents),

        agents_failed=len(failed_agents),
    )


# --------------------------------------------------
# Full orchestration pipeline
# --------------------------------------------------

async def orchestrate(
    ticker: str,
    snapshot: MarketSnapshot,
    profile: UserProfile,
) -> tuple[list[AgentOutput], Metrics]:

    agent_outputs, total_latency_ms = (
        await run_all_agents(
            ticker,
            snapshot
        )
    )

    metrics = calculate_metrics(
        agent_outputs,
        total_latency_ms,
        profile
    )

    return agent_outputs, metrics