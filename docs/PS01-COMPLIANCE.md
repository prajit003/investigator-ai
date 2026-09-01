# PS-01 compliance audit

Checked against the nine Minimum Requirements in the HACKVERSE PS-01 brief.
Everything below was verified by running the code, not by reading it: the venv
is `.venv`, the API was served with `uvicorn main:app --port 8088`, and the
commands that produced each result are quoted.

Legend: **MET** / **PARTIAL** / **NOT MET**.

---

## 1. Signal classification across >= 3 independent dimensions — MET

`GET /api/analyze` returns `signals.price_signal`, `signals.volume_signal` and
`signals.sentiment_signal`, each with its own `signal`, `confidence` and
`reasons[]`.

Price and volume are computed by two separate functions in
`agents/market_agent.py` (`price_signal`, `volume_signal`) that share no terms —
`orchestrator._signals_from` calls them individually rather than reporting one
agent's verdict twice, and `tests/test_agents.py` asserts that independence.

## 2. RAG grounded in a document corpus, with attribution — MET (backend)

`rag/` ingests the corpus under `data/filings/`; `filing_detective` cites chunk
ids, and `safety.attach_verified_evidence` -> `rag.retrieve.verify_evidence`
drops any id that was not actually retrieved and copies the quote verbatim from
the corpus, so a displayed quote cannot be model-authored.
`tests/test_grounding.py` proves uncited and cross-symbol evidence cannot reach
the user.

Live check (`symbol=RELIANCE`): two Evidence objects, `REL_SEBI_c1` and
`REL_Q2FY24_c1`, each carrying `source_name`, `source_type`, `source_date` and
verbatim `text`.

Gap: `InvestigationResult.retrieved_chunks` is always `[]` — the retrieval set
behind the citation is not surfaced, only the cited subset. Attribution is
satisfied; retrieval transparency is not.

## 3. >= 3 specialised agents in parallel with a structured contract — MET

`orchestrator.run_agents` dispatches `market_detective`, `news_detective` and
`filing_detective` under one `asyncio.gather`. Every agent has the identical
signature `async def run(symbol, market_data) -> AgentOutput`, enforced by
`validate.py` section [4]. Each call is wrapped in `safety.run_agent_safely`
(12s timeout, exception capture, schema validation), so an agent is treated as
untrusted code. `synthesis.judge` is the synthesis layer consuming them.

## 4. User profiling that changes the output — MET

Identical market inputs, different profiles:

    symbol=RELIANCE&user_id=u1  ->  CAUTION  0.67
    symbol=RELIANCE&user_id=u2  ->  POSITIVE 0.72

The rules are deterministic and live in `synthesis.py` before any prose is
generated (conservative: confidence capped at 0.7, >=2 bullish agents required,
a bearish agent above 0.6 blocks a positive call, concentration above 25%
downgrades). `personalization.personalized_reason` names the rule that fired and
the alternative outcome, which is what the requirement asks for.

## 5. Live interface rendering signals, synthesis and portfolio — NOT MET

`frontend/` is a complete, polished static mockup. It contains no `fetch` call
and no reference to `/api/`; the profile toggle swaps hardcoded `data-priya` /
`data-arjun` attributes rather than re-querying the API. The mock also
contradicts the engine — it shows RELIANCE as "BUY, 82% confidence" for the
conservative profile where the pipeline returns CAUTION at 0.67.

This is the largest remaining gap. The backend contract it needs to consume is
already stable and served from the same origin, so the work is binding, not
plumbing.

## 6. Performance log, >= 3 metrics per session — MET

Every request appends one JSON line to `logs/sessions.jsonl` with seven metrics:
`total_latency_ms`, `agent_latency_ms`, `signal_confidence`,
`evidence_coverage`, `concentration_score`, `agents_complete`, `agents_failed`.

Caveat: with no `ANTHROPIC_API_KEY` set every agent takes the offline path, so
latency rounds to 0-2 ms. The number is real, but it does not yet demonstrate
latency under LLM load.

## 7. End-to-end demo, full reasoning chain visible — PARTIAL

The chain is complete and inspectable through the API — market data -> three
agents -> evidence with verified citations -> rule-decided verdict ->
personalized reason -> metrics — but it is visible as JSON, not in the UI. Once
requirement 5 lands this is MET.

## 8. Graceful degraded-data handling — MET

Three degradation paths were exercised:

    KILL_AGENT=news_detective  ->  news_detective FAILED, verdict still returned,
                                   overall_quality DEGRADED, evidence still cited
    symbol=NOPE                ->  200, INSUFFICIENT_DATA, quality POOR, no
                                   uncited claim
    user_id=nobody             ->  404 (a genuine client error, not a data problem)

Agent conflict is surfaced rather than averaged away: RELIANCE runs
market BULLISH + news BULLISH vs filing BEARISH, and `judge_output.agent_conflict`
is set with the disagreement named in the summary.

Two defects on this path were found and fixed during this audit:

- `synthesis.judge` counted an agent that ran but found no data (signal
  `UNAVAILABLE`) as a reporting agent, so a symbol with no data anywhere
  returned CAUTION at 0.0 confidence — a judgement the evidence did not
  support — instead of INSUFFICIENT_DATA.
- `safety.compute_data_quality` marked a source AVAILABLE whenever its agent had
  not crashed, so `market_data: AVAILABLE` was reported next to the warning
  "No market data for NOPE." The two blocks are read side by side in the UI.

## 9. Written architecture summary for judges — MET

`docs/ARCHITECTURE.md` (588 lines) is the naming authority; `contracts.py`
implements it and `validate.py` fails the build on drift.
`docs/RiskModule.md` covers the profile/risk layer.

---

## Summary

| # | Requirement | Status |
|---|---|---|
| 1 | Three independent signal dimensions | MET |
| 2 | RAG with verified attribution | MET |
| 3 | Three parallel agents, structured contract | MET |
| 4 | Profile changes the output | MET |
| 5 | Live interface | NOT MET — static mockup |
| 6 | Session metrics log | MET |
| 7 | End-to-end demo, chain visible | PARTIAL — visible as JSON, not in UI |
| 8 | Degraded-data handling | MET |
| 9 | Architecture write-up | MET |

Seven of nine met. Both open items are the same piece of work: bind the existing
frontend to `/api/analyze`.

## Reproducing this audit

    python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
    .venv/bin/python validate.py
    for t in tests/*.py; do .venv/bin/python $t; done
    .venv/bin/uvicorn main:app --port 8088
    curl -s "localhost:8088/api/analyze?symbol=RELIANCE&user_id=u1"
    KILL_AGENT=news_detective .venv/bin/uvicorn main:app --port 8088
