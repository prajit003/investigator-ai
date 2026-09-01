import asyncio
import inspect
from typing import Callable, Any

from models import AgentOutput, MarketSnapshot


# Maximum time an agent is allowed to run.
AGENT_TIMEOUT_SECONDS = 8


async def run_agent_safely(
    agent_function: Callable,
    agent_name: str,
    ticker: str,
    snapshot: MarketSnapshot,
) -> AgentOutput:
    """
    Safely execute an untrusted agent.

    Handles:
    - Agent exceptions
    - Agent timeouts
    - Invalid AgentOutput responses
    - Async and synchronous agent functions

    A failed agent is converted into an UNAVAILABLE AgentOutput
    instead of crashing the backend.
    """

    try:
        # Call the agent.
        result = agent_function(ticker, snapshot)

        # If the agent is asynchronous, wait for it with a timeout.
        if inspect.isawaitable(result):
            result = await asyncio.wait_for(
                result,
                timeout=AGENT_TIMEOUT_SECONDS
            )

        # Validate the returned result.
        if isinstance(result, AgentOutput):
            return result

        return AgentOutput.model_validate(result)

    except asyncio.TimeoutError:
        return AgentOutput.unavailable(
            agent_name,
            ticker,
            f"{agent_name} timed out"
        )

    except Exception as exc:
        return AgentOutput.unavailable(
            agent_name,
            ticker,
            f"{agent_name} failed: "
            f"{type(exc).__name__}: {exc}"
        )