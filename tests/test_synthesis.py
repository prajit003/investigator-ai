"""
The personalization requirement, pinned as a test.

A judge WILL toggle the profile twice on the same symbol. If these two verdicts
ever become equal, the demo fails live. This test must never be deleted to make
CI green.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from contracts import AgentOutput, Evidence, UserProfile, Portfolio
from synthesis import judge
import store

CONFLICTED = [
    AgentOutput(agent_name="market_detective", symbol="RELIANCE", signal="BULLISH",
                confidence=0.81, reasons=["Price above SMA20 and SMA50; RSI 71.2"]),
    AgentOutput(agent_name="news_detective", symbol="RELIANCE", signal="BULLISH",
                confidence=0.74, reasons=["Volume 2.0x the 30-day average"]),
    AgentOutput(agent_name="filing_detective", symbol="RELIANCE", signal="BEARISH",
                confidence=0.55, reasons=["EBITDA margin down 140bps YoY"],
                evidence=[Evidence(source_name="Reliance Q2 FY24 Earnings Call")]),
]


def test_profiles_diverge():
    profs = store.profiles()
    verdicts = {}
    for uid in ("u1", "u2"):
        user, portfolio = profs[uid]
        j, p = judge(CONFLICTED, user, portfolio)
        verdicts[uid] = j.verdict
        assert p.personalized_reason, f"{uid} gave no reason for its verdict"
    assert verdicts["u1"] != verdicts["u2"], (
        f"IDENTICAL VERDICTS {verdicts} on identical data — "
        f"the personalization requirement is not demonstrable")
    print(f"  PASS  profiles diverge: u1={verdicts['u1']} u2={verdicts['u2']}")


def test_conflict_is_surfaced():
    user, portfolio = store.profiles()["u1"]
    j, _ = judge(CONFLICTED, user, portfolio)
    assert j.agent_conflict is True, "disagreement was averaged away instead of surfaced"
    print("  PASS  agent disagreement is reported, not hidden")


def test_all_agents_dead_is_insufficient_data():
    user, portfolio = store.profiles()["u1"]
    dead = [AgentOutput.failed(a.agent_name, "RELIANCE", "killed") for a in CONFLICTED]
    j, _ = judge(dead, user, portfolio)
    assert j.verdict == "INSUFFICIENT_DATA", f"got {j.verdict} with no working agents"
    assert j.confidence == 0.0
    print("  PASS  no agents -> INSUFFICIENT_DATA, never a guess")


def test_conservative_never_exceeds_cap():
    user, portfolio = store.profiles()["u1"]
    hot = [AgentOutput(agent_name=a.agent_name, symbol="X", signal="BULLISH",
                       confidence=0.99, reasons=["very confident"]) for a in CONFLICTED]
    j, _ = judge(hot, user, portfolio)
    assert j.confidence <= 0.7 + 1e-9, f"conservative confidence {j.confidence} exceeded cap"
    print("  PASS  conservative confidence is capped at 0.7")


def test_reliance_is_the_conflict_showcase():
    """The rehearsed demo depends on RELIANCE disagreeing across agents AND
    diverging across profiles. If either breaks, the demo breaks live."""
    import asyncio
    from orchestrator import investigate
    a = asyncio.run(investigate("RELIANCE", "u1"))
    b = asyncio.run(investigate("RELIANCE", "u2"))
    assert a.judge_output.agent_conflict, "RELIANCE no longer shows agent disagreement"
    assert a.evidence, "RELIANCE has no citation to click"
    assert a.judge_output.verdict != b.judge_output.verdict, (
        f"RELIANCE no longer diverges by profile: {a.judge_output.verdict}")
    print(f"  PASS  RELIANCE demo intact: conflict + {len(a.evidence)} citation(s), "
          f"u1={a.judge_output.verdict} u2={b.judge_output.verdict}")


if __name__ == "__main__":
    print("synthesis tests")
    test_profiles_diverge()
    test_conflict_is_surfaced()
    test_all_agents_dead_is_insufficient_data()
    test_conservative_never_exceeds_cap()
    test_reliance_is_the_conflict_showcase()
    print("\nALL SYNTHESIS TESTS PASSED")
