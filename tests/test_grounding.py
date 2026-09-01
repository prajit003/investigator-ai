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

print("\nPASS - no uncited or cross-symbol evidence can reach the user")
