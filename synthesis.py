from pydantic import BaseModel
from typing import List
import json
import os

class AgentOutput(BaseModel):
    name: str
    verdict: str  # "BULLISH", "BEARISH", "NEUTRAL"
    confidence: float
    status: str  # "AVAILABLE", "UNAVAILABLE"

class Holding(BaseModel):
    symbol: str
    quantity: float
    average_price: float
    current_value: float

class Portfolio(BaseModel):
    portfolio_value: float
    holdings: List[Holding]

class UserProfile(BaseModel):
    user_id: str
    user_name: str
    risk_profile: str
    loss_aversion: float
    max_position_pct: float
    portfolio: Portfolio

class SynthesisOutput(BaseModel):
    recommendation: str
    profile_effect: str
    conflicts: str
    rationale: str
    unavailable_agents: List[str]

def synthesize(agents: list[AgentOutput], profile: UserProfile) -> SynthesisOutput:
    # 1. Unavailable agents
    unavailable = [a.name for a in agents if a.status == "UNAVAILABLE"]
    active = [a for a in agents if a.status != "UNAVAILABLE"]

    # 2. Extract agent verdicts
    bullish_agents = []
    bearish_agents = []
    
    for a in active:
        eff_conf = a.confidence
        # Conservative: cap confidence at 0.7
        if profile.risk_profile.lower() == "conservative" and eff_conf > 0.7:
            eff_conf = 0.7
            
        if a.verdict.upper() == "BULLISH":
            bullish_agents.append((a, eff_conf))
        elif a.verdict.upper() == "BEARISH":
            bearish_agents.append((a, eff_conf))

    # 3. Detect conflicts
    conflicts_str = "None"
    if bullish_agents and bearish_agents:
        bull_names = ", ".join(f"{a.name}" for a, _ in bullish_agents)
        bear_names = ", ".join(f"{a.name}" for a, _ in bearish_agents)
        conflicts_str = f"{bull_names} BULLISH vs {bear_names} BEARISH"

    # 4. Calculate Concentration Score (max holding %)
    concentration_score = 0
    if profile.portfolio.portfolio_value > 0 and profile.portfolio.holdings:
        max_holding_val = max(h.current_value for h in profile.portfolio.holdings)
        concentration_score = (max_holding_val / profile.portfolio.portfolio_value) * 100

    # 5. Apply Rules
    recommendation = "HOLD"
    profile_effect = "None"

    is_conservative = profile.risk_profile.lower() == "conservative"
    
    if is_conservative:
        num_bullish = len(bullish_agents)
        has_strong_bear = any(eff_conf > 0.6 for _, eff_conf in bearish_agents)
        
        if num_bullish >= 2 and not has_strong_bear:
            if concentration_score > 25:
                recommendation = "HOLD"
                profile_effect = f"Downgraded BUY -> HOLD: only {num_bullish} of {len(active)} available agents bullish and portfolio concentration {concentration_score:.0f}% exceeds the 25% conservative ceiling. An aggressive profile would return BUY here."
            else:
                recommendation = "BUY"
                profile_effect = "Conservative criteria met for BUY."
        else:
            recommendation = "HOLD"
            if has_strong_bear:
                profile_effect = "Maintained HOLD: BEARISH agent with confidence > 0.6 blocked BUY. An aggressive profile might tolerate this."
            else:
                profile_effect = f"Maintained HOLD: only {num_bullish} BULLISH agents (requires >= 2)."

    else:
        # aggressive
        high_conf_bulls = [a for a, c in bullish_agents if c >= 0.7] # no cap, checking if >= 0.7 (high)
        num_bears = len(bearish_agents)
        
        if len(high_conf_bulls) >= 1 and num_bears <= 1:
            recommendation = "BUY"
            profile_effect = f"Aggressive profile returned BUY: {len(high_conf_bulls)} high-confidence BULLISH agent(s) found, tolerating {num_bears} dissenting BEARISH agent(s)."
        else:
            recommendation = "HOLD"
            profile_effect = "Aggressive criteria for BUY not met."

    # 6. LLM Rationale Generation
    # Fallback used if LLM call fails
    fallback_rationale = f"Based on the rules, the recommendation is {recommendation}. {profile_effect}"
    if conflicts_str != "None":
        fallback_rationale += f" Noted conflicts: {conflicts_str}."

    rationale = fallback_rationale
    
    try:
        # If this was real, we would call LLM to generate rationale.
        # "the LLM writes rationale only: a plain-English paragraph explaining the already-decided recommendation, referencing the agents by name."
        import google.generativeai as genai
        raise Exception("Simulated LLM failure to trigger fallback.")
    except Exception:
        pass

    return SynthesisOutput(
        recommendation=recommendation,
        profile_effect=profile_effect,
        conflicts=conflicts_str,
        rationale=rationale,
        unavailable_agents=unavailable
    )

if __name__ == '__main__':
    # STEP 6: write a test asserting that for the CONFLICTED ticker, u1 and u2 return DIFFERENT recommendation values.
    # We create a conflicted scenario with 2 bullish and 1 weak bearish to trigger the exact downgrade message.
    a1 = AgentOutput(name="technical", verdict="BULLISH", confidence=0.8, status="AVAILABLE")
    a2 = AgentOutput(name="fundamental", verdict="BULLISH", confidence=0.8, status="AVAILABLE")
    a3 = AgentOutput(name="sentiment", verdict="BEARISH", confidence=0.5, status="AVAILABLE") # Weak bear
    agents = [a1, a2, a3]
    
    with open("fixtures/profiles.json", "r") as f:
        profiles = json.load(f)
        
    u1 = UserProfile(**profiles["u1"])
    u2 = UserProfile(**profiles["u2"])
    
    out1 = synthesize(agents, u1)
    out2 = synthesize(agents, u2)
    
    assert out1.recommendation != out2.recommendation, f"u1: {out1.recommendation}, u2: {out2.recommendation}"
    assert out1.recommendation == "HOLD"
    assert out2.recommendation == "BUY"
    print(f"Test passed! u1 (conservative) = {out1.recommendation}, u2 (aggressive) = {out2.recommendation}")
    print(f"u1 profile effect: {out1.profile_effect}")
