"""
filing_detective: the grounding guarantee, end to end through the agent.

The RAG layer is tested separately in test_grounding.py. This file tests that
the AGENT wires it up correctly — a fabricated citation must not survive the
trip through the agent either.
"""
import asyncio, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import store
from agents.filing_agent import run, _offline_verdict
from rag.retrieve import retrieve
from safety import attach_verified_evidence
from contracts import AgentOutput


def test_every_symbol_is_cited():
    for s in store.symbols():
        o = asyncio.run(run(s))
        assert o.status == "COMPLETE", f"{s} degraded: {o.reasons}"
        assert o.evidence, f"{s} produced a verdict with no evidence"
        for e in o.evidence:
            assert e.chunk_id and e.text and e.source_name, f"{s} evidence is incomplete"
    print("  PASS  every symbol yields a cited fundamental verdict")


def test_quotes_are_verbatim_from_the_corpus():
    """The model never writes the quote. Prove the text is byte-identical to
    the corpus, so a displayed citation cannot be fabricated."""
    for s in store.symbols():
        o = asyncio.run(run(s))
        corpus = {c["chunk_id"]: c["text"] for c in retrieve("", s, k=99)}
        for e in o.evidence:
            assert e.chunk_id in corpus, f"cited {e.chunk_id} was never retrieved"
            assert e.text in corpus[e.chunk_id] or e.text == corpus[e.chunk_id], (
                f"{s} quote is not verbatim from {e.chunk_id}")
    print("  PASS  every quote is verbatim corpus text")


def test_fabricated_citation_is_dropped():
    chunks = retrieve("margins debt", "RELIANCE", k=3)
    out = AgentOutput(agent_name="filing_detective", symbol="RELIANCE",
                      signal="BEARISH", confidence=0.9, reasons=["margins fell"])
    out, warnings = attach_verified_evidence(
        out, [chunks[0]["chunk_id"], "TOTALLY_MADE_UP"], chunks)
    ids = [e.chunk_id for e in out.evidence]
    assert "TOTALLY_MADE_UP" not in ids, "a fabricated citation survived"
    assert out.status == "DEGRADED" and warnings
    print("  PASS  fabricated citations are dropped and reported")


def test_missing_filings_degrade():
    o = asyncio.run(run("WIPRO"))
    assert o.signal == "UNAVAILABLE" and o.status == "DEGRADED" and not o.evidence
    print("  PASS  a symbol with no filings degrades, never guesses")


def test_offline_path_needs_no_api_key():
    """The demo must not depend on a network call. The offline verdict must
    cite only chunks it actually read."""
    chunks = retrieve("margins debt", "RELIANCE", k=3)
    v = _offline_verdict(chunks)
    retrieved_ids = {c["chunk_id"] for c in chunks}
    assert set(v.cited_chunk_ids) <= retrieved_ids, "offline path cited an unretrieved chunk"
    assert v.signal in ("BULLISH", "BEARISH", "NEUTRAL")
    print("  PASS  offline path works with no API key and cites only real chunks")


if __name__ == "__main__":
    print("filing agent tests")
    test_every_symbol_is_cited()
    test_quotes_are_verbatim_from_the_corpus()
    test_fabricated_citation_is_dropped()
    test_missing_filings_degrade()
    test_offline_path_needs_no_api_key()
    print("\nALL FILING AGENT TESTS PASSED")
