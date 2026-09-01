"""
Frontend guard rails.

The UI renders exactly one object. These tests fail if the page stops being
servable, starts depending on a CDN, or drifts from the contract.
"""
import json, pathlib, re, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from contracts import InvestigationResult
from main import app

BASE = pathlib.Path(__file__).resolve().parent.parent
FE = BASE / "frontend"
client = TestClient(app)


def test_pages_are_served():
    for path in ("/", "/styles.css", "/app.js"):
        r = client.get(path)
        assert r.status_code == 200 and r.content, f"{path} -> {r.status_code}"
    # the mount at "/" must not shadow the API
    assert client.get("/api/symbols").status_code == 200, "frontend mount shadowed the API"
    print("  PASS  page, assets and API all served")


def test_no_external_dependencies():
    """A demo that needs wifi is a demo that can fail live. No CDN, no remote
    fonts, no remote images."""
    # XML namespace identifiers are not network fetches — an inline SVG data
    # URI must declare one. Everything else is a real remote dependency.
    ALLOWED = ("http://www.w3.org/",)
    offenders = []
    for f in FE.rglob("*"):
        if f.suffix not in {".html", ".css", ".js"}:
            continue
        for m in re.finditer(r"https?://[^\s\"')]+", f.read_text()):
            if m.group(0).startswith(ALLOWED):
                continue
            offenders.append(f"{f.relative_to(BASE)}: {m.group(0)}")
    assert not offenders, "frontend depends on external resources:\n  " + "\n  ".join(offenders)
    print("  PASS  frontend is fully self-contained")


def test_offline_fixture_matches_the_contract():
    """app.js falls back to this file when the API is down. If it drifts from
    InvestigationResult the fallback renders garbage."""
    p = BASE / "fixtures" / "investigation_result.json"
    assert p.exists(), "fixtures/investigation_result.json is missing"
    r = InvestigationResult.model_validate(json.loads(p.read_text()))
    assert r.agent_outputs and r.judge_output.verdict
    print("  PASS  offline fixture validates against the contract")


def test_demo_payload_has_what_the_ui_needs():
    """The three demo moments need: distinct dimensions, a citation to click,
    and a personalization sentence to read aloud."""
    a = client.get("/api/analyze", params={"symbol": "RELIANCE", "user_id": "u1"}).json()
    b = client.get("/api/analyze", params={"symbol": "RELIANCE", "user_id": "u2"}).json()
    s = a["signals"]
    assert s["price_signal"] != s["volume_signal"], "dimensions are not distinct in the payload"
    assert a["evidence"], "no evidence for the citation click"
    assert all(e.get("chunk_id") and e.get("text") for e in a["evidence"]), "evidence incomplete"
    assert a["personalization"]["personalized_reason"], "nothing to explain the verdict"
    assert a["judge_output"]["verdict"] != b["judge_output"]["verdict"], (
        "profiles no longer diverge — the toggle demo is dead")
    print("  PASS  payload supports all three demo moments")


if __name__ == "__main__":
    print("frontend tests")
    test_pages_are_served()
    test_no_external_dependencies()
    test_offline_fixture_matches_the_contract()
    test_demo_payload_has_what_the_ui_needs()
    print("\nALL FRONTEND TESTS PASSED")
