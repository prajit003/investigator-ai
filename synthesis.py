from pydantic import BaseModel
from typing import List, Optional
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

def synthesize(agents: List[AgentOutput], profile: UserProfile) -> SynthesisOutput:
    # STEP 1: return fixtures/synthesis_example.json parsed into a SynthesisOutput.
    with open("fixtures/synthesis_example.json", "r") as f:
        data = json.load(f)
        return SynthesisOutput(**data)

if __name__ == '__main__':
    print("Run successful")
