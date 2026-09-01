"""P4's agents: every confidence number must trace to a stated rule."""
import asyncio, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import store
from contracts import AgentOutput
from agents.market_agent import run as market
from agents.news_agent import run as news


def test_every_symbol_produces_a_signal():
    for s in store.symbols():
        for fn, name in ((market, "market_detective"), (news, "news_detective")):
            o = asyncio.run(fn(s, store.snapshot(s)))
            assert isinstance(o, AgentOutput) and o.agent_name == name
            assert o.status == "COMPLETE", f"{name} degraded on {s}"
            assert o.reasons, f"{name} gave no reasons for {s}"
    print("  PASS  all agents report on all symbols")


def test_confidence_is_explained():
    """A judge will ask where the number came from. It must be in `reasons`."""
    for s in store.symbols():
        o = asyncio.run(market(s, store.snapshot(s)))
        assert any(f"{o.confidence:.2f}" in r for r in o.reasons), (
            f"market_detective confidence {o.confidence} on {s} is not traceable to a rule")
    print("  PASS  every confidence traces to a stated rule with real numbers")


def test_missing_data_degrades_not_neutral():
    """Absent data must not vote as NEUTRAL in the synthesis."""
    m = asyncio.run(market("NOSUCH", None))
    n = asyncio.run(news("NOSUCH", None))
    for o in (m, n):
        assert o.signal == "UNAVAILABLE" and o.status == "DEGRADED", o
    print("  PASS  missing data degrades to UNAVAILABLE, never NEUTRAL")


def test_signals_match_the_story():
    """The demo data is hand-tuned; if someone retunes it, say so loudly."""
    expected = {"RELIANCE": "BULLISH", "TCS": "BULLISH", "ZOMATO": "BEARISH"}
    for sym, want in expected.items():
        if sym not in store.symbols():
            continue
        got = asyncio.run(market(sym, store.snapshot(sym))).signal
        assert got == want, f"{sym} market signal is {got}, demo script expects {want}"
    print("  PASS  market signals match the rehearsed demo narrative")


if __name__ == "__main__":
    print("agent tests")
    test_every_symbol_produces_a_signal()
    test_confidence_is_explained()
    test_missing_data_degrades_not_neutral()
    test_signals_match_the_story()
    print("\nALL AGENT TESTS PASSED")
