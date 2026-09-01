"""
The judge / synthesis layer.

Division of labour, per Raj's reconciliation:
  - risk/ (Person 5, canonical) computes exposure, concentration and the
    personalization object -> build_personalization()
  - THIS file decides the verdict. The stub that replaced it pointed at an
    agents/judge_agent.py that was never written, which left the orchestrator
    falling back to INSUFFICIENT_DATA on every request. Verdict rules restored
    here; personalization delegated to risk/.

RULES DECIDE THE VERDICT. Prose only explains it afterwards. If a model were
allowed to pick the verdict, two different risk profiles would occasionally
agree on identical inputs — and the personalization requirement is demonstrated
by toggling the profile in front of a judge, so it must be deterministic.

Thresholds below are P5's, preserved as written; only the types changed.
"""
from typing import List, Tuple

from contracts import (
    AgentOutput, JudgeOutput, Personalization, Portfolio, UserProfile, Verdict,
)

CONSERVATIVE_CONFIDENCE_CAP = 0.7
CONSERVATIVE_MIN_BULLISH = 2
CONSERVATIVE_CONCENTRATION_CEILING = 25.0   # percent of portfolio in one holding
STRONG_BEAR_CONFIDENCE = 0.6
AGGRESSIVE_HIGH_CONFIDENCE = 0.7


def _concentration(portfolio: Portfolio | None) -> float:
    if not portfolio or not portfolio.holdings or portfolio.portfolio_value <= 0:
        return 0.0
    return round(max(h.current_value for h in portfolio.holdings)
                 / portfolio.portfolio_value * 100, 2)


def judge(agents: List[AgentOutput], user: UserProfile,
          portfolio: Portfolio | None = None) -> Tuple[JudgeOutput, Personalization]:
    # "Reporting" means the agent produced an actual view. An agent that ran but
    # found no data returns signal="UNAVAILABLE"; counting it as a reporting
    # agent turns "we know nothing" into CAUTION, which reads as a judgement the
    # evidence does not support. Missing is missing, not neutral.
    def _reporting(a: AgentOutput) -> bool:
        return a.status != "FAILED" and a.signal != "UNAVAILABLE"

    live = [a for a in agents if _reporting(a)]
    unavailable = [a.agent_name for a in agents if not _reporting(a)]
    conservative = user.risk_profile == "CONSERVATIVE"

    # Conservative investors do not get to act on high confidence. Cap first,
    # so every downstream rule sees the capped number.
    def eff(a: AgentOutput) -> float:
        return min(a.confidence, CONSERVATIVE_CONFIDENCE_CAP) if conservative else a.confidence

    bulls = [(a, eff(a)) for a in live if a.signal == "BULLISH"]
    bears = [(a, eff(a)) for a in live if a.signal == "BEARISH"]
    concentration = _concentration(portfolio)

    conflict = bool(bulls and bears)
    conflicts = ([f"{', '.join(a.agent_name for a, _ in bulls)} BULLISH vs "
                  f"{', '.join(a.agent_name for a, _ in bears)} BEARISH"] if conflict else [])

    verdict: Verdict = "CAUTION"
    reason = ""

    if not live:
        verdict = "INSUFFICIENT_DATA"
        reason = ("No agent produced a usable view — every agent either failed or "
                  "found no data for this symbol — so no recommendation can be "
                  "justified. We report that rather than presenting an "
                  "unsupported one.")
    elif conservative:
        strong_bear = any(c > STRONG_BEAR_CONFIDENCE for _, c in bears)
        if len(bulls) >= CONSERVATIVE_MIN_BULLISH and not strong_bear:
            if concentration > CONSERVATIVE_CONCENTRATION_CEILING:
                verdict = "CAUTION"
                reason = (f"Downgraded POSITIVE to CAUTION: {len(bulls)} of {len(live)} "
                          f"available agents are bullish, but your largest holding is "
                          f"{concentration:.0f}% of the portfolio, above the "
                          f"{CONSERVATIVE_CONCENTRATION_CEILING:.0f}% conservative ceiling. "
                          f"An aggressive profile would return POSITIVE here.")
            else:
                verdict = "POSITIVE"
                reason = (f"{len(bulls)} of {len(live)} agents bullish with no strong "
                          f"bearish objection, and concentration {concentration:.0f}% is "
                          f"within the conservative ceiling.")
        elif strong_bear:
            verdict = "NEGATIVE" if len(bears) > len(bulls) else "CAUTION"
            reason = (f"A bearish agent above {STRONG_BEAR_CONFIDENCE:.1f} confidence blocks a "
                      f"positive call for a conservative profile. An aggressive profile "
                      f"would tolerate a single dissenting agent.")
        else:
            verdict = "NEGATIVE" if bears and not bulls else "CAUTION"
            reason = (f"Only {len(bulls)} bullish agent(s); a conservative profile requires "
                      f"at least {CONSERVATIVE_MIN_BULLISH}.")
    else:
        high_conf_bulls = [a for a, c in bulls if c >= AGGRESSIVE_HIGH_CONFIDENCE]
        if high_conf_bulls and len(bears) <= 1:
            verdict = "STRONG_POSITIVE" if len(high_conf_bulls) >= 2 and not bears else "POSITIVE"
            reason = (f"{len(high_conf_bulls)} high-confidence bullish agent(s); an aggressive "
                      f"profile acts on single-agent conviction and tolerates "
                      f"{len(bears)} dissenting agent(s). A conservative profile would "
                      f"require {CONSERVATIVE_MIN_BULLISH} agreeing agents.")
        elif len(bears) > len(bulls):
            verdict = "NEGATIVE"
            reason = f"{len(bears)} bearish agent(s) outweigh {len(bulls)} bullish."
        else:
            verdict = "CAUTION"
            reason = "No agent reached the conviction threshold for an aggressive position."

    if unavailable:
        reason += (f" Confidence reduced: {', '.join(unavailable)} unavailable.")

    scored = [c for _, c in bulls + bears]
    confidence = round(sum(scored) / len(scored), 3) if scored else 0.0
    if unavailable:
        confidence = round(confidence * (len(live) / max(len(agents), 1)), 3)

    judge_output = JudgeOutput(
        verdict=verdict,
        confidence=confidence,
        summary=_summary(verdict, user, live, bulls, bears, conflict),
        # Fall back to every agent's reasons when nothing reported, so an
        # INSUFFICIENT_DATA verdict still tells the user WHY it is empty.
        key_reasons=([r for a in live for r in a.reasons]
                     or [r for a in agents for r in a.reasons])[:5],
        key_risks=[r for a, _ in bears for r in a.reasons][:3],
        selected_evidence=[e for a in live for e in a.evidence][:3],
        agent_agreement=max(len(bulls), len(bears)),
        agent_conflict=conflict,
    )
    # Personalization is Person 5's canonical work and lives in risk/
    # (see docs/RiskModule.md). We delegate to it and then append the
    # verdict-specific reason so both perspectives reach the user.
    from risk.profiles import build_personalization
    p = build_personalization(
        user.model_dump(),
        portfolio.model_dump() if portfolio else {},
        agents[0].symbol if agents else "",
    )
    if reason:
        p["personalized_reason"] = (reason + " " + p.get("personalized_reason", "")).strip()
    personalization = Personalization.model_validate(p)
    return judge_output, personalization


def _summary(verdict, user, live, bulls, bears, conflict) -> str:
    """Deterministic prose. Swap for an LLM paragraph later if time allows —
    but the verdict above must stay rule-decided."""
    parts = [f"{verdict.replace('_', ' ').title()} for a "
             f"{user.risk_profile.lower()} investor: "
             f"{len(bulls)} bullish and {len(bears)} bearish of {len(live)} reporting agents."]
    if conflict:
        parts.append("The agents disagree, and we surface that rather than averaging it away.")
    return " ".join(parts)
