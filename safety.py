import asyncio
import inspect
from typing import Callable, Any

from models import AgentOutput, MarketSnapshot


AGENT_TIMEOUT_SECONDS = 8


async def run_agent_safely(
    agent_function: Callable,
    agent_name: str,
    ticker: str,
    snapshot: MarketSnapshot,
) -> AgentOutput:

    try:
        # Run the agent.
        result = agent_function(ticker, snapshot)

        # Support async agents.
        if inspect.isawaitable(result):
            result = await asyncio.wait_for(
                result,
                timeout=AGENT_TIMEOUT_SECONDS
            )

        # Validate the returned object.
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
            f"{agent_name} failed: {type(exc).__name__}: {exc}"
        )