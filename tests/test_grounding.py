"""
P3's proof for the judges: a fabricated citation cannot reach the user.

Run:  python3 tests/test_grounding.py
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from rag.ingest import filing_data_status
from rag.retrieve import retrieve, build_evidence, verify_evidence

retrieved = retrieve("margin pressure debt", "RELIANCE", k=3)
real_id = retrieved[0]["chunk_id"]
print("retrieved:", [c["chunk_id"] for c in retrieved])

# 1. An agent cites one real chunk and one it invented.
evidence, warnings = verify_evidence([real_id, "FAKE_c9"], retrieved)
kept = [e["chunk_id"] for e in evidence]
print("\ncited [real, fabricated] -> kept:", kept)
print("warning:", warnings[0])
assert kept == [real_id], "FAIL: fabricated citation survived"
assert warnings, "FAIL: dropped citation was not reported"

# 2. Evidence text is copied verbatim from the corpus, never written by a model.
assert evidence[0]["text"] == retrieved[0]["text"], "FAIL: evidence text not verbatim"
assert evidence[0]["source_name"] and evidence[0]["page"], "FAIL: attribution incomplete"
print("verbatim + attributed:", evidence[0]["source_name"], "p.", evidence[0]["page"])

# 3. Every citation fabricated -> no evidence, and an explicit uncited warning.
evidence2, warnings2 = verify_evidence(["NOPE_1", "NOPE_2"], retrieved)
print("\nall fabricated -> evidence:", evidence2, "|", warnings2[-1])
assert evidence2 == [] and any("uncited" in w for w in warnings2)

# 4. A symbol with no filings degrades; it never fabricates a fundamental view.
print("\nno-filings symbol INFY ->", filing_data_status("INFY"), "| chunks:", len(retrieve("x", "INFY")))
assert filing_data_status("INFY") == "UNAVAILABLE" and retrieve("x", "INFY") == []

# 5. Symbol isolation: a RELIANCE query can never return a TCS filing.
assert all(c["symbol"] == "RELIANCE" for c in retrieve("margin growth deals", "RELIANCE", k=9))
print("symbol isolation held")

# 6. A LIVE-shaped chunk — the kind feeds/filings.py builds from a BSE
#    announcement, carrying a public url — goes through the identical guard.
#    The url must survive into the evidence (the UI links to it) and a
#    fabricated id must still be dropped even when the pool is live.
live_chunk = {
    "chunk_id": "BSEDEADBEEF_c1",
    "symbol": "RELIANCE",
    "source_name": "Quarterly Results",
    "source_type": "FILING",
    "source_date": "2026-08-14",
    "page": 1,
    "section": "Result",
    "text": ("EBITDA margin for the quarter stood at 16.4 per cent, down 140 basis "
             "points year on year on continued capex in the new energy segment."),
    "url": "https://www.bseindia.com/xml-data/corpfiling/AttachLive/deadbeef.pdf",
}
live_pool = retrieve("margin debt capex", "RELIANCE", k=2, candidates=[live_chunk] + retrieved)
assert any(c["chunk_id"] == "BSEDEADBEEF_c1" for c in live_pool), "FAIL: live chunk not retrievable"

live_ev, live_warn = verify_evidence(["BSEDEADBEEF_c1", "BSE_NOT_RETRIEVED_c1"], live_pool)
assert [e["chunk_id"] for e in live_ev] == ["BSEDEADBEEF_c1"], "FAIL: fabricated live id survived"
assert live_warn, "FAIL: dropped live citation was not reported"
assert live_ev[0]["url"] == live_chunk["url"], "FAIL: source url lost between corpus and evidence"
assert live_ev[0]["text"] == live_chunk["text"], "FAIL: live evidence text not verbatim"
print("\nlive BSE chunk: verbatim, linked, and fabricated ids still dropped")

# 7. Symbol isolation holds for a caller-supplied pool too — a live corpus is
#    re-filtered, not trusted, so one symbol's filings cannot leak into another.
leaked = retrieve("margin", "TCS", k=5, candidates=[live_chunk])
assert leaked == [], f"FAIL: a RELIANCE chunk reached a TCS query: {leaked}"
print("symbol isolation holds for live candidate pools")

print("\nPASS - no uncited or cross-symbol evidence can reach the user")
