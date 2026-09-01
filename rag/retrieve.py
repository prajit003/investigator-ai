"""
P3 — retrieval + evidence construction.

Contract (docs/ARCHITECTURE.md):
    retrieve(query, symbol, k) -> retrieved_chunks
    build_evidence(retrieved_chunks)  -> evidence
    verify_evidence(cited_ids, retrieved_chunks) -> (evidence, warnings)

Pure-Python TF-IDF cosine — no vector DB, no embeddings API, no API key, no cold
start. Over a 9-chunk corpus the quality difference is nil and the dependency
cost is zero. Keep the signatures if we swap the implementation later.
"""
import math, re, sys, pathlib
from collections import Counter
from functools import lru_cache

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from rag.ingest import documents_for, load_documents

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = {
    "the","a","an","and","or","of","to","in","for","on","at","by","with","from",
    "is","was","were","be","been","as","that","this","it","its","we","our","has",
    "have","had","will","would","during","over","per","not","but","which","their",
}


# Crude suffix stripping. Not linguistics — it just makes "profitability" match
# "profitable" and "growth" match "growing", which is the difference between a
# sensible ranking and a wall of 0.000 scores on a 9-chunk corpus.
_SUFFIXES = ("ability", "ibility", "ations", "ation", "ingly", "ising", "izing",
             "ments", "ment", "ness", "ing", "ies", "ers", "ed", "es", "ly", "s")


def _stem(t: str) -> str:
    for suf in _SUFFIXES:
        if len(t) > len(suf) + 3 and t.endswith(suf):
            return t[: -len(suf)]
    return t


def _tokenize(text: str) -> list[str]:
    return [_stem(t) for t in _TOKEN.findall(text.lower())
            if t not in _STOP and len(t) > 2]


def _indexed_text(d: dict) -> str:
    """Index the section header and source name alongside the body — a query like
    'profitability' should match a chunk whose section IS 'Profitability'."""
    return f"{d['section']} {d['source_name']} {d['text']}"


@lru_cache(maxsize=1)
def _idf() -> dict[str, float]:
    docs = load_documents()
    n = len(docs) or 1
    df = Counter()
    for d in docs:
        df.update(set(_tokenize(_indexed_text(d))))
    return {t: math.log((n + 1) / (c + 1)) + 1.0 for t, c in df.items()}


def _vector(text: str) -> dict[str, float]:
    tf = Counter(_tokenize(text))
    if not tf:
        return {}
    idf, peak = _idf(), max(tf.values())
    v = {t: (c / peak) * idf.get(t, 1.0) for t, c in tf.items()}
    norm = math.sqrt(sum(w * w for w in v.values())) or 1.0
    return {t: w / norm for t, w in v.items()}


def retrieve(query: str, symbol: str, k: int = 3,
             candidates: list[dict] | None = None) -> list[dict]:
    """
    Top-k `retrieved_chunks` for this symbol, each with a relevance_score.

    The symbol filter is a hard pre-filter, not a ranking signal: an agent
    analysing RELIANCE must never be able to cite a TCS filing. That is a
    correctness guarantee, not an optimisation — so a caller-supplied `candidates`
    pool (the live BSE corpus) is re-filtered here rather than trusted.

    Returns [] when no filings exist for the symbol — the caller must then report
    filing_data UNAVAILABLE rather than inventing a fundamental view.
    """
    if candidates is None:
        candidates = documents_for(symbol)
    else:
        candidates = [c for c in candidates
                      if str(c.get("symbol", "")).upper() == symbol.upper()]
    if not candidates:
        return []
    qv = _vector(query)
    scored = []
    for d in candidates:
        dv = _vector(_indexed_text(d))
        score = sum(w * dv.get(t, 0.0) for t, w in qv.items()) if qv else 0.0
        scored.append({**d, "relevance_score": round(score, 4)})
    scored.sort(key=lambda d: d["relevance_score"], reverse=True)
    return scored[:k]


def build_evidence(retrieved_chunks: list[dict]) -> list[dict]:
    """Project retrieved_chunks into the `evidence` shape the frontend renders."""
    return [
        {
            "chunk_id": c["chunk_id"],
            "source_name": c["source_name"],
            "source_type": c["source_type"],
            "source_date": c["source_date"],
            "page": c["page"],
            "section": c["section"],
            "text": c["text"],
            "relevance_score": c.get("relevance_score", 0.0),
            # Live BSE chunks carry a public link; the fixture corpus does not.
            "url": c.get("url", ""),
        }
        for c in retrieved_chunks
    ]


def verify_evidence(cited_chunk_ids, retrieved_chunks: list[dict]):
    """
    THE GROUNDING GUARD — the answer to "how do you know it isn't hallucinated".

    An agent tells us WHICH chunk_ids support its claim. We return evidence only
    for ids that were actually retrieved; anything else is dropped and reported.
    The evidence `text` is copied verbatim from the corpus and is never written
    by the model, so a displayed quote physically cannot be fabricated.

    Returns (evidence, warnings) — warnings feed data_quality.warnings.
    """
    by_id = {c["chunk_id"]: c for c in retrieved_chunks}
    kept, bad = [], []
    for cid in cited_chunk_ids or []:
        (kept if cid in by_id else bad).append(cid)
    warnings = []
    if bad:
        warnings.append(
            f"{len(bad)} citation(s) referenced source material that was not retrieved "
            f"and were removed: {', '.join(sorted(bad))}."
        )
    if not kept:
        warnings.append("No verifiable source material supports this claim; treat it as uncited.")
    return build_evidence([by_id[c] for c in kept]), warnings


if __name__ == "__main__":
    for sym, q in [("RELIANCE", "margin pressure debt capex"),
                   ("TCS", "deal wins margin growth"),
                   ("ZOMATO", "profitability user growth"),
                   ("INFY", "anything")]:
        hits = retrieve(q, sym)
        print(f"\n{sym}: {q!r} -> {len(hits)} chunk(s)")
        for h in hits:
            print(f"   {h['relevance_score']:.3f}  {h['chunk_id']:16s} {h['section']:22s} {h['text'][:50]}...")
