# Before you push

```bash
pip install -r requirements.txt
python validate.py && python tests/test_grounding.py && python tests/test_synthesis.py
```

CI runs exactly these three. A red check names the file and the fix.

## The four rules

1. **`contracts.py` is the only place a data shape is defined.** Import from it.
   Never redefine a model locally — that is how `ticker` vs `symbol` happened.
2. **Field names come from `docs/ARCHITECTURE.md`.** Models are `extra="forbid"`,
   so a drifted name raises immediately instead of being silently dropped.
   `validate.py` lists every banned spelling and its replacement.
3. **Every agent has the same signature**, so the orchestrator can call all of
   them without knowing anything about any of them:
   ```python
   async def run(symbol: str, market_data: MarketData) -> AgentOutput
   ```
   Agents that do not need `market_data` accept it and ignore it.
4. **An agent may never break the request.** `/api/analyze` returns 200 with a
   DEGRADED result when an agent dies. Only an unknown symbol or user is a 404.

## Adding an agent

Create `agents/<name>_agent.py` with the signature above, register it in
`orchestrator.AGENTS`, and return an `AgentOutput`. If it crashes, hangs past
12s, or returns the wrong shape, `safety.run_agent_safely` converts it to a
`FAILED` output — you do not need your own error handling.

If your agent cites sources, do not let the model write the quote. Return the
`chunk_id`s it claims support the finding and pass them through
`safety.attach_verified_evidence`, which copies the text verbatim from the
corpus. A displayed quote then cannot be fabricated.

## Adding a symbol

Add it to `data/market/market.json` **and** `data/filings/filings.json`.
`validate.py` fails if a symbol has price data but no filings — the UI would
offer it and show empty evidence.

## Running the demo

```bash
pip install -r requirements.txt
uvicorn main:app --port 8077
```

Open <http://localhost:8077>. The frontend is served by the same process, so
there is no separate build step and no node_modules.

Degraded-data demo: `KILL_AGENT=news_detective uvicorn main:app --port 8077`

## Frontend rules

- The UI renders exactly one object, `investigation_result`. There is no second
  data shape and no client-side business logic — verdict, confidence and
  personalization all arrive already decided.
- **No CDNs, no remote fonts, no remote images.** A demo that needs wifi is a
  demo that can fail live. `tests/test_frontend.py` fails the build on any
  external URL in `frontend/`.
