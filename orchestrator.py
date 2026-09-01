import asyncio
import json
import os
import time
from pathlib import Path
from typing import List
from uuid import uuid4

from models import (
    AgentOutput,
    MarketSnapshot,
    UserProfile,
    SynthesisOutput,
    Metrics,
)
from safety import run_agent_safely


LOGS_DIR = Path(__file__).parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)


async def orchestrate(
    ticker: str,
    user_id: str,
    snapshot: MarketSnapshot,
    profile: UserProfile,
) -> SynthesisOutput:
    """
    Orchestrate all four agents concurrently, synthesize results, compute metrics, and log.
    
    STEP 2: Run all four agents concurrently with safety wrappers.
    STEP 3: Compute metrics and log.
    STEP 4: Handle degraded data (KILL_AGENT env var).
    """
    
    start_time = time.time()
    
    # STEP 2: Load and run agents concurrently
    agents_outputs = await _run_all_agents(ticker, snapshot)
    
    # STEP 4: Handle KILL_AGENT env var for degraded-data demo
    kill_agent = os.getenv("KILL_AGENT", "").lower()
    if kill_agent:
        # Find the agent to kill and replace with unavailable
        for i, output in enumerate(agents_outputs):
            if output.agent_name.lower() == kill_agent:
                agents_outputs[i] = AgentOutput.unavailable(
                    kill_agent,
                    ticker,
                    f"Killed by KILL_AGENT={kill_agent}"
                )
                break
    
    # Synthesize results (P5 owns this)
    synthesis_result = await _synthesize(
        agents_outputs,
        profile
    )
    
    # STEP 3: Compute metrics
    end_time = time.time()
    total_latency_ms = (end_time - start_time) * 1000
    
    metrics = _compute_metrics(
        agents_outputs,
        profile,
        total_latency_ms
    )
    
    # Add metrics to synthesis result
    synthesis_result.metrics = metrics
    
    # Log to sessions.jsonl
    _log_session(
        ticker,
        user_id,
        synthesis_result,
        agents_outputs
    )
    
    return synthesis_result


async def _run_all_agents(
    ticker: str,
    snapshot: MarketSnapshot,
) -> List[AgentOutput]:
    """
    STEP 2: Run all four agents concurrently.
    Each agent is wrapped in safety.run_agent_safely.
    If an agent module doesn't exist, return AgentOutput.unavailable.
    """
    
    agent_modules = [
        "technical",
        "volume",
        "sentiment",
        "fundamental",
    ]
    
    agent_coroutines = []
    
    for agent_name in agent_modules:
        try:
            # Dynamically import agent module
            module = __import__(
                f"agents.{agent_name}",
                fromlist=[agent_name]
            )
            # Call the agent's run function
            coroutine = run_agent_safely(
                module.run,
                agent_name,
                ticker,
                snapshot
            )
        except ImportError:
            # Agent module not implemented yet
            coroutine = _unavailable_agent(agent_name, ticker, "not implemented yet")
        except AttributeError:
            # Agent module exists but doesn't have run() function
            coroutine = _unavailable_agent(agent_name, ticker, "run() not found")
        
        agent_coroutines.append(coroutine)
    
    # Run all agents concurrently
    results = await asyncio.gather(*agent_coroutines)
    return results


async def _unavailable_agent(
    agent_name: str,
    ticker: str,
    reason: str
) -> AgentOutput:
    """Return an unavailable agent output (for async compatibility)"""
    return AgentOutput.unavailable(agent_name, ticker, reason)


async def _synthesize(
    agents: List[AgentOutput],
    profile: UserProfile
) -> SynthesisOutput:
    """
    STEP 2: Call synthesis.synthesize() to combine results.
    P5 owns the synthesis module.
    """
    try:
        from synthesis import synthesize
        return synthesize(agents, profile)
    except ImportError:
        # Synthesis not implemented yet; return a default result
        return SynthesisOutput(
            investigation_id=str(uuid4()),
            ticker=agents[0].ticker if agents else "UNKNOWN",
            recommendation="PENDING",
            confidence=0.0,
            summary="Synthesis not implemented",
            agent_outputs=agents,
            citations=[],
            metrics=None,
        )
    except Exception as e:
        # Synthesis failed; return a default result
        return SynthesisOutput(
            investigation_id=str(uuid4()),
            ticker=agents[0].ticker if agents else "UNKNOWN",
            recommendation="ERROR",
            confidence=0.0,
            summary=f"Synthesis failed: {type(e).__name__}: {e}",
            agent_outputs=agents,
            citations=[],
            metrics=None,
        )


def _compute_metrics(
    agents_outputs: List[AgentOutput],
    profile: UserProfile,
    total_latency_ms: float,
) -> Metrics:
    """
    STEP 3: Compute metrics.
    - total_latency_ms: wall clock time of the gather
    - avg_confidence: average confidence of OK agents only
    - concentration_score: max holding pct from the profile
    - agents_ok: count of agents with status=="OK"
    - agents_failed: count of agents with status=="FAILED" or "UNAVAILABLE"
    """
    
    ok_agents = [a for a in agents_outputs if a.status == "OK"]
    failed_agents = [a for a in agents_outputs if a.status in ("FAILED", "UNAVAILABLE")]
    
    avg_confidence = (
        sum(a.confidence for a in ok_agents) / len(ok_agents)
        if ok_agents else 0.0
    )
    
    concentration_score = profile.max_holding_pct
    
    return Metrics(
        total_latency_ms=total_latency_ms,
        avg_confidence=avg_confidence,
        concentration_score=concentration_score,
        agents_ok=len(ok_agents),
        agents_failed=len(failed_agents),
    )


def _log_session(
    ticker: str,
    user_id: str,
    synthesis_result: SynthesisOutput,
    agents_outputs: List[AgentOutput],
) -> None:
    """
    STEP 3: Log every request as one JSON line to logs/sessions.jsonl.
    """
    
    log_entry = {
        "ticker": ticker,
        "user_id": user_id,
        "recommendation": synthesis_result.recommendation,
        "metrics": synthesis_result.metrics.model_dump() if synthesis_result.metrics else None,
        "investigation_id": synthesis_result.investigation_id,
    }
    
    log_file = LOGS_DIR / "sessions.jsonl"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry) + "\n")
