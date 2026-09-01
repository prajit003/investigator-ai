"""
synthesis.py

NOTE FOR THE TEAM: this file is intentionally left as a stub.

The original task brief for Person 5 assumed a BUY/HOLD/AVOID/REDUCE
synthesis layer living here. That conflicts with the team's actual
shared contract in docs/ARCHITECTURE.md, which says:

    "Do not use BUY/SELL as the primary verdict. We're building an
    intelligence system, not an automated trading bot."

and assigns the verdict decision (STRONG_POSITIVE / POSITIVE /
CAUTION / NEGATIVE / INSUFFICIENT_DATA) to the Judge Agent
(agents/judge_agent.py), not to Person 5.

Person 5's actual implementation lives in risk/ instead:
    risk/portfolio.py    -> stock_exposure, concentration_score
    risk/profiles.py     -> personalization object (risk-profile rules)
    risk/simulation.py   -> scenario / what-if object

See docs/RiskModule.md for details.
"""
