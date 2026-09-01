from typing import List, Optional, Literal
from pydantic import BaseModel, Field


Signal = Literal[
    "BULLISH",
    "BEARISH",
    "NEUTRAL",
    "CONFLICT",
    "UNAVAILABLE",
]

AgentStatus = Literal[
    "OK",
    "UNAVAILABLE",
    "FAILED",
]


class MarketSnapshot(BaseModel):
    ticker: str
    current_price: float
    price_change_percent: float
    volume: float
    average_volume: float
    rsi: float
    momentum: float
    volatility: float
    sentiment_score: float = 0.0


class Evidence(BaseModel):
    source_name: str
    source_type: str
    source_date: Optional[str] = None
    page: Optional[int] = None
    section: Optional[str] = None
    text: str
    relevance_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0
    )


class AgentOutput(BaseModel):
    agent_name: str
    ticker: str
    status: AgentStatus
    signal: Signal
    confidence: float = Field(
        ge=0.0,
        le=1.0
    )
    reasoning: str
    citations: List[Evidence] = Field(default_factory=list)

    @classmethod
    def unavailable(
        cls,
        name: str,
        ticker: str,
        reason: str
    ):
        return cls(
            agent_name=name,
            ticker=ticker,
            status="UNAVAILABLE",
            signal="UNAVAILABLE",
            confidence=0.0,
            reasoning=reason,
            citations=[]
        )


class UserProfile(BaseModel):
    user_id: str
    name: str

    risk_profile: Literal[
        "CONSERVATIVE",
        "BALANCED",
        "AGGRESSIVE"
    ]

    investment_horizon: str

    portfolio_value: float

    max_holding_pct: float = Field(
        ge=0.0,
        le=100.0
    )


class Metrics(BaseModel):
    total_latency_ms: float
    avg_confidence: float
    concentration_score: float
    agents_ok: int
    agents_failed: int


class SynthesisOutput(BaseModel):
    investigation_id: str
    ticker: str
    recommendation: str
    confidence: float = Field(
        ge=0.0,
        le=1.0
    )
    summary: str

    agent_outputs: List[AgentOutput] = Field(
        default_factory=list
    )

    citations: List[Evidence] = Field(
        default_factory=list
    )

    metrics: Optional[Metrics] = None