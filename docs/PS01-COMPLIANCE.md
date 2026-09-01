# PS-01 compliance audit

Checked against the nine Minimum Requirements in the HACKVERSE PS-01 brief.
Everything below was verified by running the code against **live market data**,
not by reading it.

Reproduce with:

    python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
    DATA_MODE=fixtures .venv/bin/python validate.py      # offline, deterministic
    DATA_MODE=live .venv/bin/uvicorn main:app --port 8088

---

## Where the data comes from

| Dimension | Source | Verified |
|---|---|---|
| Price, volume, 30-day average volume | Moneycontrol NSE quote feed | RELIANCE ₹1,309, provider timestamp `2026-09-01 15:31:20` |
| Regulatory filings | BSE corporate announcements API + the filed PDFs | 46 announcements for scrip 500325; PDFs download and parse |
| News sentiment | Google News RSS, India edition | 25 dated, publisher-attributed headlines in a 7-day window |
| RSI, momentum, volatility | Daily closes this system accumulates itself | Absent until enough sessions exist — and it says so |

Yahoo Finance (429), NSE India (403) and stooq (JS challenge) were tested and
are unusable. Alpha Vantage, Twelve Data and Finnhub work but need a key; a
Twelve Data adapter is wired in and activates on `TWELVEDATA_API_KEY`.

**Stated plainly:** the three working sources are undocumented internal APIs,
not licensed feeds. They can change shape or block an IP without notice, and
their terms are not a commercial data licence. Every one sits behind the
`feeds/` provider interface so a licensed feed replaces it by configuration.

---

## 1. Signal classification across >= 3 independent dimensions — MET

`signals.price_signal`, `signals.volume_signal` and `signals.sentiment_signal`,
each with its own signal, confidence and `reasons[]` quoting the rule and the
real numbers that produced it. Price and volume come from two functions in
`agents/market_agent.py` that share no terms; `tests/test_agents.py` asserts
that independence.

Live example, verbatim from the UI:

> Volume 12,613,543 vs 30-day average 10,903,851 = 1.16x — below the 1.5x
> anomaly threshold, the move is not volume-confirmed (NEUTRAL)

## 2. RAG grounded in a document corpus, with attribution — MET

`feeds/filings.py` pulls real BSE announcements, downloads the filed PDF,
extracts text and chunks it. `safety.attach_verified_evidence` ->
`rag.retrieve.verify_evidence` drops any chunk_id that was not retrieved and
copies the quote verbatim from the corpus, so a displayed quote cannot be
model-authored.

Verified end to end: the UI cited `BSEE48E0687_c2` from
*Media Release — Reliance Industries and Rolls-Royce…*, dated 2026-08-14, and
the quoted sentence was confirmed present character-for-character in the
downloaded PDF. The citation links to that PDF.

Chunk selection ranks by substance rather than position — a filing opens with a
registered office address, and citing letterhead as fundamental evidence is
real, correctly attributed and worthless.

## 3. >= 3 specialised agents in parallel with a structured contract — MET

`orchestrator.run_agents` dispatches `market_detective`, `news_detective` and
`filing_detective` under one `asyncio.gather`, each with the identical signature
`async def run(symbol, market_data) -> AgentOutput` and each wrapped in
`safety.run_agent_safely` (12s timeout, exception capture, schema validation).
The agents now perform their own network I/O, which is exactly the untrusted-
dependency case that wrapper was built for.

## 4. User profiling that changes the output — MET

Rules are deterministic and run before any prose is generated. The UI fetches
both profiles for the same symbol at the same moment, so a difference cannot be
an artefact of the market moving between two clicks.

Live, on identical market input:

| | Priya (conservative) | Arjun (aggressive) |
|---|---|---|
| Verdict | CAUTION | CAUTION |
| Stated rule | "Only 1 bullish agent(s); a conservative profile requires at least 2" | "No agent reached the conviction threshold for an aggressive position" |
| Largest position | 30.0% (above the 25% ceiling) | 12.0% |

On the day of this audit both profiles reach the same verdict for different
stated reasons, and the UI says so rather than manufacturing a disagreement.
`tests/test_synthesis.py` pins the case where they diverge; the fixture corpus
reproduces it deterministically under `DATA_MODE=fixtures`.

## 5. Live interface — MET

`frontend/live.js` renders the whole page from one `/api/analyze` response and
polls every 30 seconds, pausing when the tab is hidden. The previous build was
a static mockup whose profile toggle swapped two hardcoded strings.

What it shows: live price with the **provider's** timestamp and a STALE badge
when the quote is not fresh; the three signal dimensions with classification
labels; one card per agent with its full reasoning and clickable citations; the
portfolio marked to market with a live allocation ring; and every entry in
`data_quality.warnings` verbatim.

Content removed rather than rebuilt, because no part of the system computes it:
the price chart with its invented support and resistance lines, the MACD/SMA
tiles, and the "Rebalance Suggestions" panel of BUY/REDUCE target weights. An
invented support level is a price somebody might act on.

Third-party text (filings, headlines) reaches the DOM only through
`textContent`; `frontend/live.js` contains no `innerHTML`.

## 6. Performance log, >= 3 metrics per session — MET

One JSON line per request in `logs/sessions.jsonl` with seven metrics. Latency
is now meaningful: a cold request costs ~750 ms against live providers, a warm
one ~15 ms, against a 12s per-agent timeout and PS-01's 60s budget.

## 7. End-to-end demo, full reasoning chain visible — MET

Live quote -> three parallel agents -> retrieved filings -> verified citations
-> rule-decided verdict -> the named rule that personalised it -> metrics, all
visible in the UI, with each citation opening the source document.

## 8. Graded degraded-data handling — MET

| Scenario | Result |
|---|---|
| `KILL_AGENT=news_detective` | 200. news FAILED, verdict still returned, quality DEGRADED, evidence still cited with working links |
| Unknown symbol, live mode | 200, `INSUFFICIENT_DATA`, quality POOR, no uncited claim |
| Provider down, auto mode | Falls back live -> cache -> fixture, naming every step in `data_quality.warnings` |
| Provider down, live mode | Refuses to substitute the fixture and says so |
| Backend unreachable | UI shows the error overlay instead of leaving stale numbers looking current |
| Unknown user | 404 — a genuine client error, not a data problem |

Two feed-specific defects were found by running against real data and fixed:

- **The exchange's own volume counter went backwards mid-session** — 11.6M at
  15:08, 415k at 15:22, with BSE independently reporting 712k. A ratio computed
  from that figure reads as "nobody is trading this", which is a claim about the
  market rather than about our feed. `feeds/quotes.py` now compares reported
  volume against the 30-day average pro-rated by session progress and marks the
  dimension UNAVAILABLE when the number is not credible.
- **Indicators had no honest value on day one.** RSI, momentum and volatility
  are `Optional` in the contract and stay `None` until enough closes accumulate.
  The price agent drops those terms and says so, rather than scoring a default
  of 50.0 as a real reading.

## 9. Written architecture summary for judges — MET

`docs/ARCHITECTURE.md` is the naming authority, with §15 covering the live-data
addendum; `validate.py` fails the build on drift from it.

---

## Summary

All nine minimum requirements met. Nothing in the pipeline reads a hand-written
number in `DATA_MODE=live`; the fixture corpus remains as the bottom rung of the
fallback ladder, which is what makes the degradation story real rather than
staged.
