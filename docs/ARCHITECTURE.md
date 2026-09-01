Yes. This is exactly what you should decide before 5 people start coding.

We will create a single shared architecture + variable naming contract. Everyone follows it exactly. That prevents Person 1 calling something stockData, Person 2 calling it marketInfo, Person 3 calling it symbolData, etc.

The architecture below is based on the hackathon requirements: multi-agent reasoning, 3+ market dimensions, RAG with attribution, personalization, portfolio state, visible reasoning, metrics, and degraded-data handling.

🏗️ INVESTIGATOR — SHARED ARCHITECTURE
                         ┌─────────────────────┐
                         │       USER          │
                         │ risk_profile        │
                         │ portfolio            │
                         └──────────┬──────────┘
                                    │
                                    ▼
                    ┌───────────────────────────┐
                    │      FRONTEND / UI        │
                    │                           │
                    │ selected_symbol           │
                    │ investigation_result      │
                    └─────────────┬─────────────┘
                                  │
                                  ▼
                    ┌───────────────────────────┐
                    │       BACKEND API         │
                    │                           │
                    │ /analyze                  │
                    │ /portfolio                │
                    │ /simulate                 │
                    └─────────────┬─────────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    │                           │
                    ▼                           ▼
            ┌──────────────┐            ┌──────────────┐
            │ MARKET DATA  │            │  RAG SYSTEM  │
            │              │            │              │
            │ market_data  │            │ documents    │
            └──────┬───────┘            │ evidence     │
                   │                    └──────┬───────┘
                   │                           │
                   └────────────┬──────────────┘
                                ▼
                    ┌───────────────────────────┐
                    │    AGENT ORCHESTRATOR     │
                    └─────────────┬─────────────┘
                                  │
          ┌──────────────┬────────┼────────┬──────────────┐
          ▼              ▼        ▼        ▼              ▼
     Market Agent   News Agent  Filing   Behavior     Sentiment
                                Agent     Agent        Agent
          │              │        │        │              │
          └──────────────┴────────┼────────┴──────────────┘
                                  ▼
                         ┌────────────────┐
                         │ BULL AGENT     │
                         │ BEAR AGENT     │
                         └───────┬────────┘
                                 ▼
                         ┌────────────────┐
                         │  JUDGE AGENT   │
                         └───────┬────────┘
                                 │
                     ┌───────────┴───────────┐
                     ▼                       ▼
              ┌──────────────┐       ┌──────────────┐
              │ RISK ENGINE  │       │ WHAT-IF      │
              │              │       │ SIMULATOR    │
              └──────┬───────┘       └──────┬───────┘
                     │                      │
                     └───────────┬──────────┘
                                 ▼
                     ┌──────────────────────┐
                     │ investigation_result │
                     └──────────┬───────────┘
                                ▼
                          FRONTEND RESULT
🔑 MOST IMPORTANT: SHARED VARIABLES

Create a file:

docs/ARCHITECTURE.md

Put this naming contract in it.

Everyone on the team should follow this.

1. USER VARIABLES

Always use:

user_id
user_name
risk_profile
risk_score
investment_horizon
risk_profile

Only these values:

"CONSERVATIVE"
"BALANCED"
"AGGRESSIVE"

Example:

risk_profile = "CONSERVATIVE"
2. STOCK VARIABLES

Always use:

symbol
company_name
current_price
price_change
price_change_percent

Example:

symbol = "RELIANCE"
company_name = "Reliance Industries"
current_price = 2850.00
price_change_percent = -3.8
🚨 Do NOT use
stock_name
ticker_name
stock_symbol
company
price_now

Everyone uses the shared names above.

3. MARKET DATA

The master object is:

market_data

Structure:

{
  "symbol": "RELIANCE",
  "current_price": 2850,
  "price_change_percent": -3.8,
  "volume": 3200000,
  "average_volume": 1000000,
  "rsi": 31,
  "momentum": -0.18,
  "volatility": 0.27
}

So Person 2 gives Person 1:

market_data

and Person 1 knows exactly what it contains.

4. THREE CORE SIGNALS

These are VERY important because the PS requires at least three independent dimensions.

Use:

price_signal
volume_signal
sentiment_signal

Each has:

signal
confidence
reasons

Example:

{
  "signal": "BEARISH",
  "confidence": 0.84,
  "reasons": [
    "Negative momentum",
    "Price below moving average"
  ]
}
5. AGENT OUTPUT

Every agent must return:

agent_output

with exactly:

{
  "agent_name": "market_detective",
  "signal": "BEARISH",
  "confidence": 0.84,
  "reasons": [],
  "evidence": [],
  "status": "COMPLETE"
}
Allowed agent_name
"market_detective"
"news_detective"
"filing_detective"
"behavioral_detective"
"bull_agent"
"bear_agent"
"judge_agent"
Allowed signal
"BULLISH"
"BEARISH"
"NEUTRAL"
"CONFLICT"
"UNAVAILABLE"
Allowed status
"COMPLETE"
"DEGRADED"
"FAILED"
6. RAG VARIABLES

Person 3 should use:

query
documents
retrieved_chunks
evidence

The most important one:

evidence

Every evidence object:

{
  "source_name": "Reliance Q1 Filing",
  "source_type": "FILING",
  "source_date": "2026-08-15",
  "page": 12,
  "section": "Risk Factors",
  "text": "Relevant extracted text...",
  "relevance_score": 0.92
}

This gives the frontend everything it needs to display citations.

The PS explicitly requires visible attribution for retrieved source material.

7. BULL / BEAR VARIABLES

Both must use:

bull_case
bear_case

Structure:

{
  "argument": "Strong long-term fundamentals...",
  "confidence": 0.64,
  "reasons": [],
  "evidence": []
}

So:

bull_case["confidence"]

and:

bear_case["confidence"]
8. JUDGE VARIABLES

The Judge produces:

judge_output

Structure:

{
  "verdict": "CAUTION",
  "confidence": 0.78,
  "summary": "Negative signals outweigh positive evidence.",
  "key_reasons": [],
  "key_risks": [],
  "selected_evidence": [],
  "agent_agreement": 4,
  "agent_conflict": false
}
Allowed verdicts

Use only:

"STRONG_POSITIVE"
"POSITIVE"
"CAUTION"
"NEGATIVE"
"INSUFFICIENT_DATA"

Do not use BUY/SELL as the primary verdict.

We're building an intelligence system, not an automated trading bot.

9. PORTFOLIO VARIABLES

Person 5 uses:

portfolio
portfolio_value
holdings
sector_exposure
stock_exposure
concentration_score

Example:

{
  "portfolio_value": 500000,
  "holdings": [
    {
      "symbol": "RELIANCE",
      "quantity": 42,
      "average_price": 2600,
      "current_value": 119700
    }
  ],
  "stock_exposure": 0.24,
  "concentration_score": 42
}
10. PERSONALIZATION

The master personalization object:

personalization

Structure:

{
  "risk_profile": "CONSERVATIVE",
  "risk_score": 25,
  "investment_horizon": "LONG_TERM",
  "stock_exposure": 0.24,
  "personalized_reason": "High concentration increases your downside risk."
}
11. WHAT-IF VARIABLES

Use:

scenario
scenario_change_percent
stock_impact
portfolio_impact
portfolio_impact_percent

Example:

{
  "scenario": "BEAR_CASE",
  "scenario_change_percent": -10,
  "stock_impact": -12000,
  "portfolio_impact": -12000,
  "portfolio_impact_percent": -2.4
}
🔥 12. FINAL MASTER OBJECT

This is the most important object in the entire project.

Everyone contributes to:

investigation_result

It should ultimately look like:

{
  "investigation_id": "CASE-247",
  "symbol": "RELIANCE",
  "company_name": "Reliance Industries",

  "market_data": {},

  "signals": {
    "price_signal": {},
    "volume_signal": {},
    "sentiment_signal": {}
  },

  "agent_outputs": [],

  "retrieved_chunks": [],

  "evidence": [],

  "bull_case": {},

  "bear_case": {},

  "judge_output": {},

  "personalization": {},

  "portfolio": {},

  "scenario": {},

  "metrics": {},

  "data_quality": {}
}
This is your single source of truth.

The frontend should eventually receive:

investigation_result

and render it.

📊 13. PERFORMANCE METRICS

Use:

metrics

Structure:

{
  "total_latency_ms": 2840,
  "agent_latency_ms": 2100,
  "signal_confidence": 0.81,
  "evidence_coverage": 0.94,
  "concentration_score": 42
}

The PS requires at least three measurable session metrics.

🚨 14. DATA QUALITY

This is important for your degraded-data requirement.

Use:

data_quality

Example:

{
  "market_data": "AVAILABLE",
  "news_data": "AVAILABLE",
  "filing_data": "AVAILABLE",
  "overall_quality": "GOOD",
  "warnings": []
}

If news fails:

{
  "market_data": "AVAILABLE",
  "news_data": "UNAVAILABLE",
  "filing_data": "AVAILABLE",
  "overall_quality": "DEGRADED",
  "warnings": [
    "News data unavailable; confidence reduced."
  ]
}
🧩 FINAL FOLDER ARCHITECTURE

I recommend changing our earlier structure slightly:

investigator-ai/
│
├── frontend/
│
├── backend/
│   ├── main.py
│   ├── routes/
│   └── models/
│
├── agents/
│   ├── market_agent.py
│   ├── news_agent.py
│   ├── filing_agent.py
│   ├── behavioral_agent.py
│   ├── bull_agent.py
│   ├── bear_agent.py
│   ├── judge_agent.py
│   └── orchestrator.py
│
├── rag/
│   ├── ingest.py
│   ├── retrieve.py
│   └── vector_store/
│
├── risk/
│   ├── profiles.py
│   ├── portfolio.py
│   └── simulation.py
│
├── data/
│   ├── market/
│   ├── filings/
│   └── news/
│
├── tests/
│
├── docs/
│   └── ARCHITECTURE.md
│
├── README.md
└── .gitignore
🔄 HOW DATA FLOWS

This is what everyone should memorize:

symbol
  ↓
market_data
  ↓
signals
  ↓
agent_outputs
  ↓
retrieved_chunks + evidence
  ↓
bull_case + bear_case
  ↓
judge_output
  ↓
personalization
  ↓
portfolio
  ↓
scenario
  ↓
metrics
  ↓
data_quality
  ↓
investigation_result
  ↓
FRONTEND
👥 TEAM CONTRACT

Send this table to your group:

Person	Main files	Input	Output
You	backend/	Everything	investigation_result
Person 2	agents/	market_data, evidence, personalization	agent_output
Person 3	rag/, data/	symbol, query	retrieved_chunks, evidence
Person 4	frontend/	investigation_result	UI
Person 5	risk/	portfolio, risk_profile	personalization, scenario
🚨 ONE GOLDEN RULE
Don't pass 20 individual variables between modules.

Pass the master objects.

Bad:

analyze(symbol, price, volume, rsi, sentiment, risk, portfolio...)

Good:

analyze_stock(
    market_data,
    evidence,
    personalization,
    portfolio
)

And the final:

investigation_result

is what the backend sends to the frontend.

📌 Put this in GitHub NOW

Create:

docs/ARCHITECTURE.md

and paste the architecture/naming rules into it.

This file becomes your team's contract.

Then commit:

git add .
git commit -m "Add shared architecture and variable contract"
git push

Once this is pushed, don't change variable names casually.

Next, we should build the project in the fastest possible order: first the shared Python data models → then the agents → RAG → risk → backend → frontend integration. That way all five people can code simultaneously without waiting for each other.
---

15. LIVE DATA ADDENDUM (agreed after the fixture build)

The system originally read three hand-written JSON fixtures. It now reads live
sources through the `feeds/` package. Nothing above `feeds/` knows or cares where
a number came from, but a live number carries obligations a fixture does not, so
four fields were added. These are ADDITIONS. No existing name changed.

15.1 market_data gains provenance

  as_of    the timestamp the PROVIDER stamped on this quote, e.g.
           "2026-09-01 15:08:36". Not the time we fetched it.
  source   which adapter produced it, e.g. "moneycontrol", "cache", "fixture".

A live price with no timestamp and no provenance cannot be audited, and the UI
must be able to grey out a figure that is no longer current. Both are strings and
both default to "", so a fixture-mode object is still valid.

15.2 rsi, momentum and volatility become OPTIONAL

They are computed from accumulated daily closes, not handed to us by the quote
feed, so early on they are genuinely absent.

  rsi         float or null
  momentum    float or null
  volatility  float or null

null means MISSING, and the price agent must say so and drop that term from its
score. It must never be read as "neutral". Defaulting rsi to 50.0 would let an
indicator we do not have cast a vote — the same mistake this document rejects
everywhere else.

15.3 evidence gains a link

  url   the public address of the document the quote came from, e.g. the BSE
        attachment PDF. Empty string when the corpus entry has no public URL.

A citation the reader cannot open is a weaker citation. The grounding guard is
unchanged: url, like text, is copied from the corpus and never written by a model.

15.4 Modes

  DATA_MODE=auto      live, then last-known-good cache, then fixture (default)
  DATA_MODE=live      live only; a provider failure degrades that dimension
  DATA_MODE=fixtures  never touches the network. CI and validate.py run here.

Every downgrade appends a line to data_quality.warnings naming what failed. A
silent fallback would present stale or synthetic numbers as live.
