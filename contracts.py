"""
INVESTIGATOR — the single source of truth for every data shape in this project.

This file IMPLEMENTS `docs/ARCHITECTURE.md`. It invents no new names: every field
below appears in that document, and every allowed value matches it exactly.
If you want a field that is not here, change ARCHITECTURE.md first, tell the
team, then change this file. Never the other way round.

Everything is a pydantic model with defaults, so a partially-built object is
still valid and a missing agent degrades instead of raising.
"""
from typing import List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    """
    Base for every contract object.

    `extra="forbid"` is the point: a field name that drifts from
    docs/ARCHITECTURE.md raises immediately instead of being silently dropped.
    Naming drift is the failure mode this project cannot afford, so it is a
    hard error, not a convention. `python3 validate.py` lists the banned
    spellings and their replacements.
    """
    model_config = ConfigDict(extra="forbid")

# ---- allowed values (docs/ARCHITECTURE.md) ----
RiskProfile = Literal["CONSERVATIVE", "BALANCED", "AGGRESSIVE"]
Horizon     = Literal["SHORT_TERM", "MEDIUM_TERM", "LONG_TERM"]
SignalValue = Literal["BULLISH", "BEARISH", "NEUTRAL", "CONFLICT", "UNAVAILABLE"]
AgentStatus = Literal["COMPLETE", "DEGRADED", "FAILED"]
AgentName   = Literal["market_detective", "news_detective", "filing_detective",
                      "behavioral_detective", "bull_agent", "bear_agent", "judge_agent"]
Verdict     = Literal["STRONG_POSITIVE", "POSITIVE", "CAUTION", "NEGATIVE",
                      "INSUFFICIENT_DATA"]
Availability = Literal["AVAILABLE", "UNAVAILABLE"]
Quality      = Literal["GOOD", "DEGRADED", "POOR"]
SourceType   = Literal["FILING", "TRANSCRIPT", "NEWS", "SHAREHOLDER_LETTER"]


# ---- 1. user ----
class UserProfile(Strict):
    user_id: str
    user_name: str = ""
    risk_profile: RiskProfile = "BALANCED"
    risk_score: int = 50
    investment_horizon: Horizon = "LONG_TERM"


# ---- 3. market data ----
class MarketData(Strict):
    symbol: str
    company_name: str = ""
    current_price: float = 0.0
    price_change: float = 0.0
    price_change_percent: float = 0.0
    volume: int = 0
    average_volume: int = 1
    rsi: float = 50.0
    momentum: float = 0.0
    volatility: float = 0.0


# ---- 4. the three core signals ----
class Signal(Strict):
    signal: SignalValue = "NEUTRAL"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reasons: List[str] = []


class Signals(Strict):
    price_signal: Signal = Signal()
    volume_signal: Signal = Signal()
    sentiment_signal: Signal = Signal()


# ---- 6. RAG ----
class Evidence(Strict):
    """Built by rag.build_evidence. `text` is copied verbatim from the corpus."""
    source_name: str
    source_type: SourceType = "FILING"
    source_date: str = ""
    page: int = 0
    section: str = ""
    text: str = ""
    relevance_score: float = 0.0


# ---- 5. agent output ----
class AgentOutput(Strict):
    agent_name: AgentName
    symbol: str = ""
    signal: SignalValue = "NEUTRAL"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reasons: List[str] = []
    evidence: List[Evidence] = []
    status: AgentStatus = "COMPLETE"
    latency_ms: int = 0

    @classmethod
    def failed(cls, agent_name: str, symbol: str, why: str) -> "AgentOutput":
        """Built by the orchestrator when an agent dies. Never raises."""
        return cls(agent_name=agent_name, symbol=symbol, signal="UNAVAILABLE",
                   confidence=0.0, reasons=[f"Agent unavailable: {why}"],
                   evidence=[], status="FAILED", latency_ms=0)


# ---- 7. bull / bear (CUT for the demo; kept so the shape exists) ----
class Case(Strict):
    argument: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reasons: List[str] = []
    evidence: List[Evidence] = []


# ---- 8. judge ----
class JudgeOutput(Strict):
    verdict: Verdict = "INSUFFICIENT_DATA"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    summary: str = ""
    key_reasons: List[str] = []
    key_risks: List[str] = []
    selected_evidence: List[Evidence] = []
    agent_agreement: int = 0
    agent_conflict: bool = False


# ---- 9. portfolio ----
class Holding(Strict):
    symbol: str
    quantity: float = 0.0
    average_price: float = 0.0
    current_value: float = 0.0


class Portfolio(Strict):
    portfolio_value: float = 0.0
    holdings: List[Holding] = []
    sector_exposure: dict = {}
    stock_exposure: float = 0.0
    concentration_score: float = 0.0   # ACTUAL largest holding as % of portfolio


# ---- 10. personalization ----
class Personalization(Strict):
    risk_profile: RiskProfile = "BALANCED"
    risk_score: int = 50
    investment_horizon: Horizon = "LONG_TERM"
    stock_exposure: float = 0.0
    personalized_reason: str = ""


# ---- 11. what-if (CUT for the demo) ----
class Scenario(Strict):
    scenario: str = ""
    scenario_change_percent: float = 0.0
    stock_impact: float = 0.0
    portfolio_impact: float = 0.0
    portfolio_impact_percent: float = 0.0


# ---- 13. metrics ----
class Metrics(Strict):
    total_latency_ms: int = 0
    agent_latency_ms: int = 0
    signal_confidence: float = 0.0
    evidence_coverage: float = 0.0
    concentration_score: float = 0.0
    # Additive: needed to report degradation. Not in ARCHITECTURE.md's example,
    # agreed as an addition rather than a rename.
    agents_complete: int = 0
    agents_failed: int = 0


# ---- 14. data quality ----
class DataQuality(Strict):
    market_data: Availability = "AVAILABLE"
    news_data: Availability = "AVAILABLE"
    filing_data: Availability = "AVAILABLE"
    overall_quality: Quality = "GOOD"
    warnings: List[str] = []


# ---- 12. THE MASTER OBJECT — this is what the frontend renders ----
class InvestigationResult(Strict):
    investigation_id: str = ""
    symbol: str = ""
    company_name: str = ""
    market_data: Optional[MarketData] = None
    signals: Signals = Signals()
    agent_outputs: List[AgentOutput] = []
    retrieved_chunks: List[dict] = []
    evidence: List[Evidence] = []
    bull_case: Optional[Case] = None
    bear_case: Optional[Case] = None
    judge_output: JudgeOutput = JudgeOutput()
    personalization: Personalization = Personalization()
    portfolio: Optional[Portfolio] = None
    scenario: Optional[Scenario] = None
    metrics: Metrics = Metrics()
    data_quality: DataQuality = DataQuality()
