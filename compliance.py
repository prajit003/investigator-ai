#!/usr/bin/env python3
"""
PS-01 compliance audit. Reports what a judge would actually find, per the
nine Minimum Requirements. Honest about what is not built.
"""
import asyncio, json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

MET, PARTIAL, MISSING = "MET", "PARTIAL", "MISSING"
rows = []


def req(n, title, state, note=""):
    rows.append((n, title, state, note))


def main():
    import store
    from orchestrator import investigate, AGENTS
    from rag.ingest import available_symbols

    r = asyncio.run(investigate("RELIANCE", "u1"))
    r2 = asyncio.run(investigate("RELIANCE", "u2"))
    s = r.signals

    # 1 — three independent signal dimensions with confidence and cited reasoning
    dims = {"price": s.price_signal, "volume": s.volume_signal, "sentiment": s.sentiment_signal}
    independent = s.price_signal.model_dump() != s.volume_signal.model_dump()
    have_conf = all(d.reasons for d in dims.values())
    req(1, "3 independent dimensions + confidence + reasoning",
        MET if independent and have_conf else PARTIAL,
        f"price/volume/sentiment distinct={independent}, all state reasons={have_conf}")

    # 2 — RAG grounded, attribution visible
    ev = r.evidence
    filing = next((a for a in r.agent_outputs if a.agent_name == "filing_detective"), None)
    req(2, "RAG output grounded with visible attribution",
        MET if ev else (PARTIAL if filing and filing.status != "FAILED" else MISSING),
        f"evidence items={len(ev)}, filing agent={'missing' if not filing or filing.status=='FAILED' else filing.status}")

    # 3 — 3+ agents in parallel with a structured contract into synthesis
    live = [a for a in r.agent_outputs if a.status != "FAILED"]
    req(3, "3+ specialised agents in parallel -> synthesis",
        MET if len(live) >= 3 else PARTIAL,
        f"{len(live)} of {len(AGENTS)} agents reporting; all return AgentOutput")

    # 4 — profiling changes output on identical input
    diverge = r.judge_output.verdict != r2.judge_output.verdict
    tcs = (asyncio.run(investigate("TCS", "u1")).judge_output.verdict
           != asyncio.run(investigate("TCS", "u2")).judge_output.verdict)
    req(4, "User profile changes output on identical data",
        MET if (diverge or tcs) else MISSING,
        f"RELIANCE diverges={diverge}, TCS diverges={tcs}")

    # 5 — live interface
    fe = pathlib.Path("frontend")
    has_ui = any(fe.glob("*.html")) or any(fe.glob("*.js")) if fe.exists() else False
    req(5, "Live interface (signals, synthesis+attribution, portfolio)",
        MET if has_ui else MISSING, "no frontend files" if not has_ui else "present")

    # 6 — >=3 metrics logged per session
    m = r.metrics.model_dump()
    logged = pathlib.Path("logs/sessions.jsonl").exists()
    req(6, ">=3 measurable metrics per session",
        MET if len([v for v in m.values() if v is not None]) >= 3 and logged else PARTIAL,
        f"{len(m)} metrics, persisted={logged}")

    # 7 — end-to-end demo scenario with the full chain visible
    chain = bool(r.market_data and r.agent_outputs and r.judge_output.verdict
                 and r.personalization.personalized_reason)
    req(7, "End-to-end scenario, reasoning chain visible",
        MET if chain and ev else PARTIAL,
        "chain complete but no evidence yet" if chain and not ev else "")

    # 8 — degraded data handled without failing or producing an uncited output
    import os
    os.environ["KILL_AGENT"] = "news_detective"
    import importlib, orchestrator
    importlib.reload(orchestrator)
    d = asyncio.run(orchestrator.investigate("RELIANCE", "u1"))
    os.environ.pop("KILL_AGENT")
    importlib.reload(orchestrator)
    ok = d.judge_output.verdict is not None and d.data_quality.overall_quality != "GOOD"
    req(8, "Degraded data handled, no uncited output",
        MET if ok else PARTIAL,
        f"killed agent -> quality={d.data_quality.overall_quality}, "
        f"verdict still produced={bool(d.judge_output.verdict)}")

    # 9 — written architecture summary for judges
    arch = pathlib.Path("docs/ARCHITECTURE.md")
    summary = pathlib.Path("docs/SUMMARY.md")
    req(9, "Written architecture summary for judges",
        MET if summary.exists() else PARTIAL,
        "ARCHITECTURE.md exists but is an internal naming contract; "
        "no judge-facing SUMMARY.md" if not summary.exists() else "")

    print("PS-01 COMPLIANCE AUDIT\n")
    counts = {MET: 0, PARTIAL: 0, MISSING: 0}
    for n, title, state, note in rows:
        counts[state] += 1
        print(f"  [{state:7s}] {n}. {title}")
        if note:
            print(f"             {note}")
    print(f"\n  {counts[MET]} met · {counts[PARTIAL]} partial · {counts[MISSING]} missing")
    return 0


if __name__ == "__main__":
    sys.exit(main())
