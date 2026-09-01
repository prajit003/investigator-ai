"""
The orchestration layer. Runs every agent CONCURRENTLY and never lets one
failure reach the user as an error.

Contract: every agent module exposes
    async def run(symbol: str, market_data: MarketData) -> AgentOutput
Agents that do not need market_data accept and ignore it.
"""
import asyncio
import importlib
import json
import os
import pathlib
import time
import uuid
from typing import List

import store
from contracts import (
    AgentOutput, InvestigationResult, JudgeOutput, Personalization,
    Portfolio, Signal, Signals, UserProfile,
)
from safety import compute_data_quality, compute_metrics, run_agent_safely

LOGS = pathlib.Path(__file__).resolve().parent / "logs"
LOGS.mkdir(exist_ok=True)

# agent_name -> module path. Names come from docs/ARCHITECTURE.md §5.
AGENTS = {
    "market_detective": "agents.market_agent",
    "news_detective":   "agents.news_agent",
    "filing_detective": "agents.filing_agent",
}


async def _missing(agent_name: str, symbol: str, why: str) -> AgentOutput:
    return AgentOutput.failed(agent_name, symbol, why)


def _killed(agent_name: str) -> bool:
    """KILL_AGENT=news_detective forces a real failure, for the degraded demo."""
    kill = {a.strip().lower() for a in os.getenv("KILL_AGENT", "").split(",") if a.strip()}
    return agent_name.lower() in kill


async def run_agents(symbol: str, market_data) -> List[AgentOutput]:
    tasks = []
    for agent_name, module_path in AGENTS.items():
        if _killed(agent_name):
            # Kill BEFORE dispatch, so we exercise the real failure path and pay
            # none of the cost — not by overwriting a result we already computed.
            tasks.append(_missing(agent_name, symbol, f"killed by KILL_AGENT={agent_name}"))
            continue
        try:
            mod = importlib.import_module(module_path)
            fn = getattr(mod, "run")
        except ModuleNotFoundError:
            tasks.append(_missing(agent_name, symbol, "agent not implemented yet"))
            continue
        except AttributeError:
            tasks.append(_missing(agent_name, symbol, f"{module_path}.run() not found"))
            continue
        tasks.append(run_agent_safely(fn, agent_name, symbol, market_data))

    # return_exceptions=True is belt-and-braces: run_agent_safely already cannot
    # raise, but a bug in it must still not take down the request.
    results = await asyncio.gather(*tasks, return_exceptions=True)
    out = []
    for (agent_name, _), r in zip(AGENTS.items(), results):
        out.append(r if isinstance(r, AgentOutput)
                   else AgentOutput.failed(agent_name, symbol, f"orchestrator error: {r}"))
    return out


def _signals_from(agents: List[AgentOutput]) -> Signals:
    """Project agent outputs onto the three dimensions PS-01 requires."""
    by = {a.agent_name: a for a in agents}

    def sig(name: str) -> Signal:
        a = by.get(name)
        if a is None or a.status == "FAILED":
            return Signal(signal="UNAVAILABLE", confidence=0.0,
                          reasons=[a.reasons[0] if a and a.reasons else "agent unavailable"])
        return Signal(signal=a.signal, confidence=a.confidence, reasons=list(a.reasons))

    m = sig("market_detective")
    # price and volume are both produced by the market agent; it reports them
    # separately in `reasons`, and P4 may later split it into two modules.
    return Signals(price_signal=m, volume_signal=m, sentiment_signal=sig("news_detective"))


def _synthesize(agents: List[AgentOutput], user: UserProfile,
                portfolio: Portfolio) -> tuple[JudgeOutput, Personalization]:
    try:
        from synthesis import judge
        return judge(agents, user, portfolio)
    except ModuleNotFoundError:
        pass
    except Exception as e:
        return (JudgeOutput(verdict="INSUFFICIENT_DATA",
                            summary=f"Synthesis failed: {type(e).__name__}: {e}"),
                Personalization(risk_profile=user.risk_profile, risk_score=user.risk_score,
                                investment_horizon=user.investment_horizon))
    # Fallback so the pipeline is demoable before P5 lands.
    live = [a for a in agents if a.status != "FAILED"]
    bull = sum(1 for a in live if a.signal == "BULLISH")
    bear = sum(1 for a in live if a.signal == "BEARISH")
    return (JudgeOutput(
                verdict="INSUFFICIENT_DATA",
                confidence=0.0,
                summary="Synthesis layer not implemented; showing raw agent findings.",
                key_reasons=[r for a in live for r in a.reasons][:5],
                selected_evidence=[e for a in live for e in a.evidence][:3],
                agent_agreement=max(bull, bear),
                agent_conflict=bull > 0 and bear > 0),
            Personalization(risk_profile=user.risk_profile, risk_score=user.risk_score,
                            investment_horizon=user.investment_horizon,
                            stock_exposure=portfolio.stock_exposure))


async def investigate(symbol: str, user_id: str) -> InvestigationResult:
    """The whole pipeline. Raises only if the SYMBOL or USER is unknown."""
    symbol = symbol.upper()
    t0 = time.perf_counter()

    market_data = store.snapshot(symbol)
    user, portfolio = store.profiles().get(user_id, (None, None))
    if user is None:
        raise KeyError(f"unknown user_id {user_id!r}")

    ta = time.perf_counter()
    agents = await run_agents(symbol, market_data)
    agent_ms = (time.perf_counter() - ta) * 1000

    judge_output, personalization = _synthesize(agents, user, portfolio)
    evidence = [e for a in agents for e in a.evidence]

    result = InvestigationResult(
        investigation_id=f"CASE-{uuid.uuid4().hex[:6].upper()}",
        symbol=symbol,
        company_name=market_data.company_name if market_data else "",
        market_data=market_data,
        signals=_signals_from(agents),
        agent_outputs=agents,
        evidence=evidence,
        judge_output=judge_output,
        personalization=personalization,
        portfolio=portfolio,
        metrics=compute_metrics(agents, portfolio, (time.perf_counter() - t0) * 1000, agent_ms),
        data_quality=compute_data_quality(
            agents, symbol,
            extra_warnings=[] if market_data else [f"No market data for {symbol}."]),
    )
    _log(result, user_id)
    return result


def _log(result: InvestigationResult, user_id: str) -> None:
    entry = {
        "investigation_id": result.investigation_id,
        "symbol": result.symbol,
        "user_id": user_id,
        "verdict": result.judge_output.verdict,
        "overall_quality": result.data_quality.overall_quality,
        "metrics": result.metrics.model_dump(),
    }
    with (LOGS / "sessions.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
