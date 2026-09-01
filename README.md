# INVESTIGATOR / AUREON

A multi-agent research system for Indian retail investors. Live NSE prices, real
SEBI-regulated filings and real news headlines go in; a cited, rule-decided,
profile-aware recommendation comes out, with every step of the reasoning visible.

Built for HACKVERSE PS-01. See [docs/PS01-COMPLIANCE.md](docs/PS01-COMPLIANCE.md)
for the requirement-by-requirement audit and
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the naming contract.

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn main:app --port 3000          # then open http://localhost:3000
```

No API key is needed. `ANTHROPIC_API_KEY` upgrades the fundamental agent from a
deterministic lexicon to Claude; `TWELVEDATA_API_KEY` switches the quote feed to
a licensed provider and backfills daily candles so the technical indicators work
from the first run.

## Data modes

| `DATA_MODE` | Behaviour |
|---|---|
| `auto` (default) | Live, falling back to the last-known-good cache, then the hand-written fixtures. Every step down is named in `data_quality.warnings`. |
| `live` | Live only. A provider failure degrades that dimension instead of substituting a fixture — this is the mode to demo honest failure in. |
| `fixtures` | Never opens a socket. CI and `validate.py` run here, so the build is deterministic and offline. |

## The full live checklist

`validate.py` proves the contract holds offline. `checklist.py` proves the
system works against the real providers — 317 checks across symbol resolution,
quotes, indicators, news, filings, agents, the grounding guard, the pipeline,
personalization, degradation, the session log, the HTTP API and the served
frontend:

```bash
DATA_MODE=live .venv/bin/python checklist.py --api
```

A check passes only when what came back is traceable to a real source: a
provider timestamp within minutes of now, a chunk id that exists in the corpus,
a quote copied out of the document it cites. Indicators that need history the
system has not accumulated yet are reported as not-yet-applicable rather than
failed — absent and honest about it is the correct state, and
`tests/test_indicators.py` covers the maths offline.

## Before pushing

```bash
DATA_MODE=fixtures .venv/bin/python validate.py
```

`validate.py` is the guard rail: it fails on field names that drift from
`docs/ARCHITECTURE.md`, on data files that no longer match the contract, on an
agent whose signature the orchestrator cannot call, and on a pipeline that
raises instead of degrading. CI runs exactly this file plus the six test suites.

## Warming the filing corpus

Filing PDFs are fetched out of band so no agent pays for a download inside its
12-second budget:

```bash
DATA_MODE=live .venv/bin/python -m feeds.filings RELIANCE TCS INFY
```

Without it the system still cites real filings, using the filed headline text
rather than the document body, and says which it is doing.

## A note on the data sources

The keyless providers this runs on — Moneycontrol quotes, BSE corporate
announcements, Google News RSS — are undocumented internal APIs, not licensed
market data. They work today and may stop without notice, and their terms are
not a commercial data licence. Everything that touches them lives behind the
`feeds/` interface precisely so a licensed feed can replace them by
configuration rather than by a rewrite.

Nothing here is investment advice.
