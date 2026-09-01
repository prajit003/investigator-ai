# RAG layer (Person 3)

Conforms to `docs/ARCHITECTURE.md`. Produces `retrieved_chunks` and `evidence`.
No external dependencies, no API key, no vector store — pure-Python TF-IDF.

## Interface

```python
from rag.retrieve import retrieve, build_evidence, verify_evidence
from rag.ingest import filing_data_status

retrieved_chunks = retrieve(query, symbol, k=3)   # [] if no filings for symbol
evidence         = build_evidence(retrieved_chunks)
```

## For the filing agent (Person 2)

Give the model the numbered chunk_ids, have it return which ones support its
claim, then pass those ids through `verify_evidence` — never let the model write
the quote itself:

```python
chunks = retrieve("margins, debt, growth, risks", symbol, k=3)
if not chunks:
    # filing_data is UNAVAILABLE -> status DEGRADED, do not invent a view
    ...
# ... model returns cited_chunk_ids ...
evidence, warnings = verify_evidence(cited_chunk_ids, chunks)
```

`verify_evidence` drops any chunk_id that was not actually retrieved and returns
`warnings` for `data_quality.warnings`. The evidence `text` is copied verbatim
from the corpus, so a displayed quote cannot be fabricated by the model.

## For data_quality (§14)

```python
"filing_data": filing_data_status(symbol)   # "AVAILABLE" | "UNAVAILABLE"
```

## Guarantees

- **Symbol isolation** — a RELIANCE query can never return a TCS filing (hard pre-filter).
- **No uncited output** — unverifiable citations are dropped and reported, never rendered.
- **Degraded, never fabricated** — an unknown symbol returns `[]` + `UNAVAILABLE`.

## Corpus

`data/filings/filings.json` — 9 pre-chunked synthetic filings/transcripts across
RELIANCE, TCS, ZOMATO. Each chunk already carries the full `evidence` contract
(source_name, source_type, source_date, page, section, text).

RELIANCE is deliberately **negative on fundamentals** — pair it with strong price
momentum in `market_data` to demo the agent-conflict requirement.

Tests: `python3 tests/test_grounding.py`
