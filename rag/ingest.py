"""
P3 — corpus loading. Owns `documents` and `retrieved_chunks` per docs/ARCHITECTURE.md.

No external dependencies: the corpus is pre-chunked JSON on disk, so ingest is a
load-and-validate step rather than a pipeline. Swap the body later if we move to
a real vector store; keep the function names.
"""
import json, pathlib
from functools import lru_cache

FILINGS_PATH = pathlib.Path(__file__).resolve().parent.parent / "data" / "filings" / "filings.json"

# Every chunk must carry the full evidence contract from docs/ARCHITECTURE.md §6,
# so a chunk can become an `evidence` object with no extra lookups.
REQUIRED_FIELDS = {
    "chunk_id", "symbol", "source_name", "source_type",
    "source_date", "page", "section", "text",
}


@lru_cache(maxsize=1)
def load_documents() -> tuple[dict, ...]:
    """Return every chunk in the corpus. Raises at import time if the corpus is malformed."""
    if not FILINGS_PATH.exists():
        return ()
    rows = json.loads(FILINGS_PATH.read_text())
    for i, row in enumerate(rows):
        missing = REQUIRED_FIELDS - set(row)
        if missing:
            raise ValueError(f"{FILINGS_PATH.name} row {i} ({row.get('chunk_id')}) missing {sorted(missing)}")
    return tuple(rows)


def documents_for(symbol: str) -> list[dict]:
    return [d for d in load_documents() if d["symbol"].upper() == symbol.upper()]


def available_symbols() -> list[str]:
    return sorted({d["symbol"] for d in load_documents()})


async def live_documents_for(symbol: str) -> tuple[list[dict], list[str]]:
    """
    The corpus the filing agent should actually read: live BSE filings first,
    with the hand-written fixture chunks appended.

    Live wins on ordering, not by exclusion — the fixture corpus is the reason
    the demo still has something to cite when BSE is unreachable, and both carry
    real chunk_ids that the grounding guard can verify.
    """
    from feeds.filings import corpus_with_warnings

    live, warnings = await corpus_with_warnings(symbol)
    fixture = documents_for(symbol)
    seen = {c["chunk_id"] for c in live}
    return live + [c for c in fixture if c["chunk_id"] not in seen], warnings


def filing_data_status(symbol: str) -> str:
    """Feeds `data_quality.filing_data` (ARCHITECTURE.md §14)."""
    return "AVAILABLE" if documents_for(symbol) else "UNAVAILABLE"


if __name__ == "__main__":
    print(f"{len(load_documents())} chunks | symbols: {available_symbols()}")
    for s in available_symbols() + ["INFY"]:
        print(f"  {s:10s} {filing_data_status(s)}")
