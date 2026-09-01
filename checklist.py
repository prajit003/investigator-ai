#!/usr/bin/env python3
"""
FULL-SCALE LIVE CHECKLIST.

    DATA_MODE=live .venv/bin/python checklist.py            # feeds + agents + pipeline
    DATA_MODE=live .venv/bin/python checklist.py --api      # also hit a running server

validate.py proves the CONTRACT holds offline. This proves the SYSTEM works
against real providers: that every function runs, that what it returns is
genuinely live rather than a fixture wearing a live label, and that the parts
which cannot be live right now say so instead of guessing.

The distinction it enforces everywhere: a check does not pass because a function
returned something. It passes because what came back is traceable to a real
source — a provider timestamp within minutes of now, a chunk id that exists in
the corpus, a quote that appears verbatim in the document it cites.

Exit code 0 only if every REQUIRED check passed. Checks that depend on data the
system has not accumulated yet (RSI needs 15 sessions) are reported as EXPECTED
rather than failed, because "absent and honest about it" is the correct state.
"""
import argparse
import asyncio
import json
import os
import pathlib
import sys
import time
from datetime import datetime, timedelta

BASE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

os.environ.setdefault("DATA_MODE", "live")

PASS, FAIL, EXPECTED = [], [], []
_section = ""


def section(title: str) -> None:
    global _section
    _section = title
    print(f"\n\033[1m{title}\033[0m")


def ok(label: str, detail: str = "") -> None:
    PASS.append((_section, label))
    print(f"  \033[32mPASS\033[0m  {label}" + (f"  — {detail}" if detail else ""))


def bad(label: str, detail: str = "") -> None:
    FAIL.append((_section, label, detail))
    print(f"  \033[31mFAIL\033[0m  {label}" + (f"  — {detail}" if detail else ""))


def expected(label: str, detail: str = "") -> None:
    """Not a failure: the honest absence of data we have not collected yet."""
    EXPECTED.append((_section, label))
    print(f"  \033[33mN/A \033[0m  {label}" + (f"  — {detail}" if detail else ""))


def check(cond: bool, label: str, detail: str = "") -> bool:
    (ok if cond else bad)(label, detail)
    return bool(cond)


def fresh_within(stamp: str, minutes: int) -> bool:
    """Is a provider timestamp recent? This is what separates a live number from
    a cached or fabricated one, so it is checked rather than assumed."""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            t = datetime.strptime(stamp[:19], fmt)
        except (ValueError, TypeError):
            continue
        # The feed stamps IST; compare against IST wall clock.
        from feeds.clock import now_ist
        return abs(now_ist().replace(tzinfo=None) - t) <= timedelta(minutes=minutes)
    return False


# ─────────────────────────────────────────────────────────────────────────────

async def check_config():
    section("1. CONFIGURATION")
    import feeds
    check(feeds.mode() == "live", "DATA_MODE is live", f"got {feeds.mode()!r}")
    check(not feeds.offline(), "network access is permitted")

    import importlib
    for mod in ("httpx", "pydantic", "fastapi", "pypdf"):
        try:
            importlib.import_module(mod)
            ok(f"{mod} importable")
        except ImportError as e:
            bad(f"{mod} importable", str(e))

    from feeds.symbols import watchlist
    wl = watchlist()
    check(len(wl) >= 3, "watchlist has at least 3 symbols", f"{wl}")
    return wl


async def check_symbol_resolution(watchlist):
    section("2. SYMBOL RESOLUTION")
    from feeds import symbols
    resolved = {}
    for sym in watchlist:
        ref = await symbols.resolve(sym)
        if not ref:
            bad(f"{sym} resolves", "no mapping")
            continue
        good = bool(ref.get("mc_scid")) and bool(ref.get("bse_code"))
        check(good, f"{sym} resolves",
              f"mc={ref.get('mc_scid')!r} bse={ref.get('bse_code')!r}")
        if good:
            resolved[sym] = ref
    # A wrong mapping prices the wrong company, which is worse than no data.
    unknown = await symbols.resolve("ZZZZ_NOT_A_COMPANY")
    check(unknown is None, "an unknown symbol resolves to nothing, not to a guess",
          f"got {unknown}")
    return resolved


async def check_quotes(watchlist):
    section("3. LIVE QUOTES")
    from feeds import quotes
    from feeds.clock import describe, is_session_open
    print(f"        ({describe()})")

    got = {}
    for sym in watchlist:
        md, warns = await quotes.quote_with_warnings(sym)
        if md is None:
            bad(f"{sym} quote", "; ".join(warns) or "no data")
            continue
        got[sym] = md

        check(md.current_price > 0, f"{sym} has a price", f"₹{md.current_price}")
        check(md.source in ("moneycontrol", "twelvedata"),
              f"{sym} came from a live provider", f"source={md.source!r}")
        # The provider's own timestamp, not our fetch time. Out of session hours
        # the last print can legitimately be hours old, so the window widens.
        window = 15 if is_session_open() else 24 * 60
        check(fresh_within(md.as_of, window),
              f"{sym} timestamp is current", f"as_of={md.as_of!r}")
        check(md.average_volume > 1, f"{sym} carries a 30-day average volume",
              f"{md.average_volume:,}")
        check(bool(md.company_name), f"{sym} carries a company name", md.company_name)

    check(len(got) == len(watchlist), "every watchlist symbol quoted",
          f"{len(got)}/{len(watchlist)}")

    # Two symbols must not return the same price — that would mean the resolver
    # is handing every request the same scrip.
    prices = {s: m.current_price for s, m in got.items()}
    check(len(set(prices.values())) == len(prices),
          "each symbol has a distinct price", f"{prices}")
    return got


async def check_indicators(quotes_by_symbol):
    section("4. TECHNICAL INDICATORS")
    from feeds import indicators
    for sym, md in quotes_by_symbol.items():
        cov = indicators.coverage(sym)
        if cov["rsi"]:
            check(md.rsi is not None and 0 <= md.rsi <= 100,
                  f"{sym} RSI computed", f"{md.rsi} from {cov['closes']} closes")
        else:
            # The correct state on a young history, and the reason rsi is
            # Optional in the contract.
            if md.rsi is None:
                expected(f"{sym} RSI absent and declared absent",
                         f"{cov['closes']} close(s) recorded, needs "
                         f"{indicators.RSI_PERIOD + 1}")
            else:
                bad(f"{sym} RSI absent and declared absent",
                    f"reported {md.rsi} from only {cov['closes']} closes")
        check(cov["closes"] >= 1, f"{sym} close recorded for today",
              f"{cov['closes']}")


async def check_news(watchlist):
    section("5. LIVE NEWS")
    from feeds import news
    for sym in watchlist:
        items, warns = await news.headlines_with_warnings(sym)
        if not items:
            bad(f"{sym} headlines", "; ".join(warns) or "none returned")
            continue
        real = [i for i in items if i.get("publisher") != "fixture"]
        check(bool(real), f"{sym} headlines are live, not fixture",
              f"{len(items)} item(s)")
        dated = [i for i in real if i.get("published")]
        check(len(dated) >= len(real) // 2, f"{sym} headlines carry dates",
              f"{len(dated)}/{len(real)}")
        attributed = [i for i in real if i.get("publisher")]
        check(bool(attributed), f"{sym} headlines carry a publisher",
              f"e.g. {attributed[0]['publisher']}" if attributed else "none")
        # Google appends " - Publisher" to every title; if that survives, the
        # sentiment lexicon is scoring the outlet's name.
        leaked = [i for i in real if i.get("publisher")
                  and i["title"].endswith(f" - {i['publisher']}")]
        check(not leaked, f"{sym} publisher suffix stripped from titles",
              f"{len(leaked)} leaked")


async def check_filings(watchlist):
    section("6. LIVE FILINGS (RAG CORPUS)")
    from feeds import filings
    corpora = {}
    for sym in watchlist:
        chunks, warns = await filings.corpus_with_warnings(sym)
        if not chunks:
            bad(f"{sym} filings", "; ".join(warns) or "no chunks")
            continue
        corpora[sym] = chunks
        check(all(c["symbol"] == sym for c in chunks),
              f"{sym} chunks are scoped to their symbol", f"{len(chunks)} chunk(s)")
        linked = [c for c in chunks if c.get("url", "").startswith("https://")]
        check(bool(linked), f"{sym} chunks carry a public document URL",
              f"{len(linked)}/{len(chunks)}")
        dated = [c for c in chunks if c.get("source_date")]
        check(len(dated) == len(chunks), f"{sym} chunks are dated",
              f"{len(dated)}/{len(chunks)}")
        ids = [c["chunk_id"] for c in chunks]
        check(len(set(ids)) == len(ids), f"{sym} chunk ids are unique")
        check(all(len(c["text"].split()) >= 8 for c in chunks),
              f"{sym} no empty or stub chunks")
    return corpora


async def check_agents(watchlist, quotes_by_symbol):
    section("7. AGENTS")
    from safety import run_agent_safely
    from orchestrator import AGENTS
    import importlib

    for agent_name, module_path in AGENTS.items():
        mod = importlib.import_module(module_path)
        for sym in watchlist:
            t0 = time.perf_counter()
            out = await run_agent_safely(mod.run, agent_name, sym,
                                         quotes_by_symbol.get(sym))
            ms = (time.perf_counter() - t0) * 1000
            good = out.status != "FAILED"
            check(good, f"{agent_name} runs for {sym}",
                  f"{out.signal} @ {out.confidence} ({out.status}, {ms:.0f}ms)")
            if good:
                check(bool(out.reasons), f"{agent_name}/{sym} states its reasoning")
                # A judge will ask where a confidence number came from; the
                # answer has to be in `reasons`, with the real figures in it.
                check(any(ch.isdigit() for r in out.reasons for ch in r),
                      f"{agent_name}/{sym} reasoning quotes real numbers")


async def check_grounding(watchlist):
    section("8. GROUNDING GUARD (live corpus)")
    from rag.ingest import live_documents_for
    from rag.retrieve import retrieve, verify_evidence
    from agents.filing_agent import QUERY, TOP_K

    for sym in watchlist:
        candidates, _ = await live_documents_for(sym)
        chunks = retrieve(QUERY, sym, k=TOP_K, candidates=candidates)
        if not chunks:
            bad(f"{sym} retrieval returns chunks")
            continue
        real_id = chunks[0]["chunk_id"]

        ev, warns = verify_evidence([real_id, "FABRICATED_c99"], chunks)
        check([e["chunk_id"] for e in ev] == [real_id],
              f"{sym} fabricated citation is dropped", f"kept {[e['chunk_id'] for e in ev]}")
        check(bool(warns), f"{sym} the drop is reported, not silent")
        check(ev and ev[0]["text"] == chunks[0]["text"],
              f"{sym} evidence text is verbatim from the corpus")

        # Cross-symbol leakage would let one company's filing justify another's
        # verdict. Hard requirement, not a ranking preference.
        others = [s for s in watchlist if s != sym]
        if others:
            leaked = retrieve(QUERY, others[0], k=5, candidates=candidates)
            check(all(c["symbol"] == others[0] for c in leaked),
                  f"{sym} corpus cannot leak into a {others[0]} query",
                  f"{[c['chunk_id'] for c in leaked]}")


async def check_pipeline(watchlist):
    section("9. FULL PIPELINE")
    import orchestrator
    import store

    profiles = list(store.profiles())
    check(len(profiles) >= 2, "at least two user profiles", f"{profiles}")

    results = {}
    for sym in watchlist:
        for uid in profiles:
            t0 = time.perf_counter()
            r = await orchestrator.investigate(sym, uid)
            ms = (time.perf_counter() - t0) * 1000
            results[(sym, uid)] = r

            check(r.judge_output.verdict in
                  ("STRONG_POSITIVE", "POSITIVE", "CAUTION", "NEGATIVE", "INSUFFICIENT_DATA"),
                  f"{sym}/{uid} returns a valid verdict",
                  f"{r.judge_output.verdict} @ {r.judge_output.confidence}")
            check(ms < 60_000, f"{sym}/{uid} inside the 60s PS-01 budget", f"{ms:.0f}ms")
            check(len(r.agent_outputs) == 3, f"{sym}/{uid} all three agents reported",
                  f"{[(a.agent_name, a.status) for a in r.agent_outputs]}")
            check(r.market_data is not None and r.market_data.source != "fixture",
                  f"{sym}/{uid} priced from a live source",
                  r.market_data.source if r.market_data else "no market data at all")
            check(bool(r.personalization.personalized_reason),
                  f"{sym}/{uid} states the rule that personalised it")
            check(r.portfolio is not None and r.portfolio.portfolio_value > 0,
                  f"{sym}/{uid} portfolio marked to market",
                  f"₹{r.portfolio and r.portfolio.portfolio_value:,.0f}")
            # Never present a claim as sourced when it is not.
            check(all(e.text for e in r.evidence),
                  f"{sym}/{uid} every citation carries its quote",
                  f"{len(r.evidence)} evidence item(s)")
            check(json.dumps(r.model_dump(), default=str) is not None,
                  f"{sym}/{uid} result serialises")

    section("10. PERSONALIZATION")
    u1, u2 = profiles[0], profiles[1]
    for sym in watchlist:
        a, b = results[(sym, u1)], results[(sym, u2)]
        if a.market_data is None or b.market_data is None:
            # Report it rather than crashing: a symbol with no quote is a
            # finding about the feed, not a reason to abandon the run.
            bad(f"{sym}: both profiles saw identical market input",
                "no market data for at least one profile")
            continue
        check(a.market_data.current_price == b.market_data.current_price,
              f"{sym}: both profiles saw identical market input",
              f"{a.market_data.current_price} vs {b.market_data.current_price}")

        # "Different output" is satisfied by a different VERDICT or, when the
        # day's data puts both profiles on the same side, by a different stated
        # rule. Requiring a verdict split every time would mean tuning the
        # thresholds until the demo disagreed with itself.
        verdict_differs = a.judge_output.verdict != b.judge_output.verdict
        reason_differs = (a.personalization.personalized_reason
                          != b.personalization.personalized_reason)
        check(verdict_differs or reason_differs,
              f"{sym}: the two profiles produce different output",
              f"{a.judge_output.verdict} vs {b.judge_output.verdict}"
              + ("" if verdict_differs else " (same verdict, different stated rule)"))
    # Concentration is what the conservative downgrade turns on, so it has to
    # differ between the two portfolios for the rule to be demonstrable at all.
    ca = results[(watchlist[0], u1)].portfolio.concentration_score
    cb = results[(watchlist[0], u2)].portfolio.concentration_score
    check(abs(ca - cb) > 1.0, "the two portfolios differ in concentration",
          f"{ca}% vs {cb}%")
    return results


async def check_degradation(watchlist):
    section("11. DEGRADED-DATA HANDLING")
    import importlib
    import orchestrator

    sym = watchlist[0]

    os.environ["KILL_AGENT"] = "news_detective"
    try:
        r = await orchestrator.investigate(sym, "u1")
    finally:
        os.environ.pop("KILL_AGENT", None)
    killed = [a for a in r.agent_outputs if a.status == "FAILED"]
    check(len(killed) == 1, "KILL_AGENT actually kills one agent",
          f"{[a.agent_name for a in killed]}")
    check(r.judge_output.verdict != "", "a verdict is still returned")
    check(r.data_quality.overall_quality in ("DEGRADED", "POOR"),
          "the result is marked degraded", r.data_quality.overall_quality)
    check(bool(r.data_quality.warnings), "the failure is named in warnings")
    check(all(e.text for e in r.evidence),
          "surviving citations still carry their quotes", f"{len(r.evidence)}")

    r = await orchestrator.investigate("ZZZZ_NOT_A_COMPANY", "u1")
    check(r.judge_output.verdict == "INSUFFICIENT_DATA",
          "an unknown symbol yields INSUFFICIENT_DATA, not a guess",
          r.judge_output.verdict)
    check(r.evidence == [], "an unknown symbol cites nothing")
    check(r.data_quality.overall_quality == "POOR", "quality reported POOR",
          r.data_quality.overall_quality)

    try:
        await orchestrator.investigate(watchlist[0], "no_such_user")
        bad("an unknown user raises KeyError for the API to turn into a 404")
    except KeyError:
        ok("an unknown user raises KeyError for the API to turn into a 404")

    # A dead provider must fall back and SAY it fell back.
    from feeds import quotes as q
    real = q._moneycontrol, q._twelvedata

    async def dead(_s):
        raise RuntimeError("simulated provider outage")

    q._moneycontrol, q._twelvedata = dead, dead
    try:
        md, warns = await q.quote_with_warnings("A_SYMBOL_WITH_NO_CACHE_ENTRY")
        check(md is None, "live mode refuses to invent a price when providers die",
              f"{md}")
        check(any("forbids" in w or "quote failed" in w for w in warns),
              "the outage is named in warnings", f"{warns}")
    finally:
        q._moneycontrol, q._twelvedata = real


def check_logging():
    section("12. SESSION LOG")
    path = BASE / "logs" / "sessions.jsonl"
    if not check(path.exists(), "logs/sessions.jsonl exists"):
        return
    lines = [l for l in path.read_text().splitlines() if l.strip()]
    check(bool(lines), "the log has entries", f"{len(lines)} line(s)")
    try:
        last = json.loads(lines[-1])
    except json.JSONDecodeError as e:
        bad("the last entry is valid JSON", str(e)); return
    ok("the last entry is valid JSON")
    for field in ("investigation_id", "symbol", "user_id", "verdict", "metrics"):
        check(field in last, f"log carries {field}")
    m = last.get("metrics", {})
    for field in ("total_latency_ms", "signal_confidence", "evidence_coverage",
                  "concentration_score", "agents_complete", "agents_failed"):
        check(field in m, f"metrics carry {field}", f"{m.get(field)}")
    check(m.get("total_latency_ms", 0) > 0,
          "latency is a real measurement, not zero", f"{m.get('total_latency_ms')}ms")


def check_api(base_url: str, watchlist):
    section(f"13. HTTP API ({base_url})")
    import httpx

    try:
        r = httpx.get(f"{base_url}/api/symbols", timeout=30)
    except Exception as e:
        bad("server is reachable", f"{type(e).__name__}: {e}")
        return
    check(r.status_code == 200, "GET /api/symbols", f"{r.status_code}")
    syms = r.json()
    check(set(syms) == set(watchlist), "symbols route returns the watchlist", f"{syms}")

    r = httpx.get(f"{base_url}/api/profiles", timeout=30)
    check(r.status_code == 200, "GET /api/profiles", f"{r.status_code}")
    profs = r.json()
    check(len(profs) >= 2, "profiles route returns both users", f"{len(profs)}")

    for sym in watchlist:
        for uid in ("u1", "u2"):
            r = httpx.get(f"{base_url}/api/analyze",
                          params={"symbol": sym, "user_id": uid}, timeout=60)
            if not check(r.status_code == 200, f"GET /api/analyze {sym}/{uid}",
                         f"{r.status_code}"):
                continue
            d = r.json()
            check(d["market_data"]["source"] != "fixture",
                  f"{sym}/{uid} served live data over HTTP",
                  d["market_data"]["source"])
            check(bool(d["judge_output"]["verdict"]), f"{sym}/{uid} has a verdict",
                  d["judge_output"]["verdict"])

    # These must never be a 500: a data problem is a degraded result.
    r = httpx.get(f"{base_url}/api/analyze",
                  params={"symbol": "ZZZZ_NOT_A_COMPANY", "user_id": "u1"}, timeout=60)
    check(r.status_code == 200, "unknown symbol returns 200, not 500", f"{r.status_code}")
    r = httpx.get(f"{base_url}/api/analyze",
                  params={"symbol": watchlist[0], "user_id": "ghost"}, timeout=60)
    check(r.status_code == 404, "unknown user returns 404", f"{r.status_code}")
    r = httpx.get(f"{base_url}/api/analyze", params={"symbol": watchlist[0]}, timeout=30)
    check(r.status_code == 422, "a missing parameter returns 422", f"{r.status_code}")

    section("14. FRONTEND ASSETS")
    for path, needle in (("/", "<title>"), ("/live.js", "/api/analyze"),
                         ("/app.js", "DOMContentLoaded"), ("/styles.css", ".agent-card")):
        r = httpx.get(f"{base_url}{path}", timeout=30)
        served = r.status_code == 200 and needle in r.text
        check(served, f"{path} is served", f"{r.status_code}")
    r = httpx.get(f"{base_url}/live.js", timeout=30)
    # Third-party filing text reaches the DOM; innerHTML there is an XSS hole.
    check("innerHTML" not in r.text.replace("There is no innerHTML", ""),
          "live.js writes no innerHTML")
    r = httpx.get(f"{base_url}/", timeout=30)
    check("data-priya" not in r.text, "no hardcoded profile mock attributes remain")
    check(r.text.count("data-bind") > 30, "the markup is bound to the API",
          f"{r.text.count('data-bind')} hooks")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", metavar="URL", nargs="?", const="http://localhost:3000",
                    help="also exercise a running server (default http://localhost:3000)")
    args = ap.parse_args()

    print("\033[1mAUREON — FULL LIVE CHECKLIST\033[0m")
    print(f"        DATA_MODE={os.environ.get('DATA_MODE')}  "
          f"started {time.strftime('%Y-%m-%d %H:%M:%S')}")

    t0 = time.perf_counter()
    watchlist = await check_config()
    await check_symbol_resolution(watchlist)
    quotes_by_symbol = await check_quotes(watchlist)
    await check_indicators(quotes_by_symbol)
    await check_news(watchlist)
    await check_filings(watchlist)
    await check_agents(watchlist, quotes_by_symbol)
    await check_grounding(watchlist)
    await check_pipeline(watchlist)
    await check_degradation(watchlist)
    check_logging()
    if args.api:
        check_api(args.api.rstrip("/"), watchlist)

    from feeds import http
    await http.aclose()

    total = len(PASS) + len(FAIL)
    print(f"\n\033[1mSUMMARY\033[0m  {len(PASS)}/{total} required checks passed"
          f"  ·  {len(EXPECTED)} not-yet-applicable"
          f"  ·  {time.perf_counter() - t0:.1f}s")
    if EXPECTED:
        print("\n  Not applicable yet (absent by design, reported honestly):")
        for sec, label in EXPECTED:
            print(f"    · {sec} — {label}")
    if FAIL:
        print("\n\033[31m  FAILURES:\033[0m")
        for sec, label, detail in FAIL:
            print(f"    · {sec} — {label}" + (f"  ({detail})" if detail else ""))
        print()
        return 1
    print("\n\033[32m  EVERY CHECK PASSED.\033[0m\n")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
