#!/usr/bin/env python3
"""
The feed layer's contract, tested WITHOUT the network.

Three things are worth pinning down, and none of them need a live provider:

  1. DATA_MODE=fixtures really does forbid a socket. This is what CI depends on;
     if it ever silently starts making requests, the build becomes flaky and we
     start sending traffic to someone else's servers from a shared runner.
  2. The fallback ladder degrades in the stated order AND says so. A fallback
     nobody can see is a lie about how fresh the number is.
  3. The volume plausibility guard drops a figure it cannot believe rather than
     letting it become a "nobody is trading this" signal.
"""
import asyncio
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from feeds import cache  # noqa: E402

_TMP = pathlib.Path(tempfile.mkdtemp()) / "test_cache.db"
cache.DB_PATH = _TMP
cache._CONN = None

import feeds  # noqa: E402
from feeds import http, quotes  # noqa: E402
from feeds.news import _parse as parse_rss  # noqa: E402
from feeds.filings import _chunks_from, _substance_score  # noqa: E402

PASSED, FAILED = [], []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail and not ok else ""))
    (PASSED if ok else FAILED).append(label)


def with_mode(mode):
    os.environ["DATA_MODE"] = mode


def test_fixtures_mode_cannot_open_a_socket():
    with_mode("fixtures")
    try:
        asyncio.run(http.fetch("https://example.invalid/should-never-be-called"))
        check("fixtures mode blocks network access", False, "the fetch was attempted")
    except http.OfflineError:
        check("fixtures mode blocks network access", True)
    except Exception as e:
        check("fixtures mode blocks network access", False,
              f"raised {type(e).__name__} instead of OfflineError")


def test_fixtures_mode_still_serves_a_quote():
    with_mode("fixtures")
    md, warnings = asyncio.run(quotes.quote_with_warnings("RELIANCE"))
    check("fixtures mode returns the hand-written snapshot",
          md is not None and md.source == "fixture", f"{md and md.source}")
    check("fixture mode adds no fallback warning", warnings == [], f"{warnings}")


def test_live_mode_refuses_to_substitute_a_fixture():
    """DATA_MODE=live exists so a demo can show the honest failure. If it
    quietly served the fixture, the failure would be invisible."""
    with_mode("live")

    async def dead(_symbol):
        raise RuntimeError("provider down")

    real = quotes._moneycontrol, quotes._twelvedata
    quotes._moneycontrol, quotes._twelvedata = dead, dead
    try:
        md, warnings = asyncio.run(quotes.quote_with_warnings("NO_SUCH_SYMBOL_XYZ"))
    finally:
        quotes._moneycontrol, quotes._twelvedata = real
    check("live mode returns no data rather than a fixture", md is None, f"{md}")
    check("live mode names the refusal in a warning",
          any("forbids" in w for w in warnings), f"{warnings}")


def test_auto_mode_falls_back_and_says_so():
    with_mode("auto")

    async def dead(_symbol):
        raise RuntimeError("provider down")

    real = quotes._moneycontrol, quotes._twelvedata
    quotes._moneycontrol, quotes._twelvedata = dead, dead
    try:
        md, warnings = asyncio.run(quotes.quote_with_warnings("RELIANCE"))
    finally:
        quotes._moneycontrol, quotes._twelvedata = real
    check("auto mode falls back to the fixture", md is not None and md.source == "fixture",
          f"{md and md.source}")
    check("the fallback is reported, not silent",
          any("NOT a market price" in w for w in warnings), f"{warnings}")
    check("the failing providers are named",
          any("quote failed" in w for w in warnings), f"{warnings}")


def test_volume_guard_rejects_an_implausible_figure():
    # A 30-day average of 10 million and 400 shares traded is not a quiet
    # market, it is a broken counter. Observed live on 2026-09-01.
    # Progress is passed explicitly so this test does not pass or fail
    # depending on what time of day it is run.
    ok, why = quotes._volume_is_credible(
        {"volume": 400, "average_volume": 10_000_000}, progress=1.0)
    credible, _ = quotes._volume_is_credible(
        {"volume": 9_000_000, "average_volume": 10_000_000}, progress=1.0)
    check("an impossible volume is rejected", not ok, f"accepted it: {why}")
    check("a normal volume is accepted", credible)
    check("zero volume is rejected", not quotes._volume_is_credible(
        {"volume": 0, "average_volume": 10_000_000}, progress=1.0)[0])
    # Early in the session a small figure is legitimate, and the guard must not
    # cry wolf on a genuinely quiet first ten minutes.
    early, _ = quotes._volume_is_credible(
        {"volume": 300_000, "average_volume": 10_000_000}, progress=0.05)
    check("an early-session figure is not rejected", early)
    check("the guard is armed outside market hours too",
          quotes.session_progress() > 0.0)


def test_rss_parsing_strips_the_publisher_suffix():
    xml = """<?xml version="1.0"?>
    <rss version="2.0"><channel>
      <item>
        <title>Reliance shares fall 2% after results - Reuters</title>
        <link>https://example.com/a</link>
        <source url="https://reuters.com">Reuters</source>
      </item>
      <item>
        <title>Reliance shares fall 2% after results - Reuters</title>
        <link>https://example.com/dupe</link>
        <source url="https://reuters.com">Reuters</source>
      </item>
    </channel></rss>"""
    items = parse_rss(xml)
    check("duplicate headlines are collapsed", len(items) == 1, f"got {len(items)}")
    check("the ' - Publisher' suffix is stripped from the title",
          items and items[0]["title"] == "Reliance shares fall 2% after results",
          f"got {items and items[0]['title']!r}")
    check("the publisher is kept as attribution",
          items and items[0]["publisher"] == "Reuters", f"got {items and items[0]['publisher']}")
    check("malformed XML yields no headlines rather than raising",
          parse_rss("<rss><channel><item>") == [])


def test_filing_chunks_prefer_substance_over_letterhead():
    letterhead = ("Regd. Office: 3rd Floor, Maker Chambers IV, 222, Nariman Point, "
                  "Mumbai 400 021 India Telefax: +91-22-2204 2268 E-mail: "
                  "investor.relations@example.com CIN- L17110MH1973PLC019786 BSE "
                  "Limited Phiroze Jeejeebhoy Towers Dalal Street Mumbai 400 001")
    substance = ("EBITDA margin for the quarter stood at 16.4 per cent, down 140 basis "
                 "points year on year, while consolidated revenue grew to 2,35,000 crore "
                 "and net debt increased on continued capex in the new energy segment.")
    check("letterhead scores below substance",
          _substance_score(letterhead) < _substance_score(substance),
          f"{_substance_score(letterhead)} vs {_substance_score(substance)}")

    row = {"NEWSID": "abcd-1234-ef", "HEADLINE": "Results for the quarter are attached.",
           "NEWSSUB": "Quarterly Results", "NEWS_DT": "2026-08-14T10:00:00",
           "CATEGORYNAME": "Result", "ATTACHMENTNAME": "x.pdf"}
    chunks = _chunks_from(row, "RELIANCE", f"{letterhead} {substance}")
    check("a chunk is produced from real filing text", bool(chunks))
    check("the chunk carries a public URL",
          chunks and chunks[0]["url"].startswith("https://www.bseindia.com/"),
          f"{chunks and chunks[0]['url']}")
    check("the chunk is scoped to its symbol",
          all(c["symbol"] == "RELIANCE" for c in chunks))

    # No body at all: the filed headline is real prose and better evidence than
    # nothing, but an empty body must never produce an empty chunk.
    empty = _chunks_from({**row, "HEADLINE": "", "NEWSSUB": ""}, "RELIANCE", "")
    check("no text produces no chunk", empty == [], f"{empty}")


if __name__ == "__main__":
    print("FEED LAYER")
    original = os.environ.get("DATA_MODE")
    try:
        for fn in (test_fixtures_mode_cannot_open_a_socket,
                   test_fixtures_mode_still_serves_a_quote,
                   test_live_mode_refuses_to_substitute_a_fixture,
                   test_auto_mode_falls_back_and_says_so,
                   test_volume_guard_rejects_an_implausible_figure,
                   test_rss_parsing_strips_the_publisher_suffix,
                   test_filing_chunks_prefer_substance_over_letterhead):
            fn()
    finally:
        if original is None:
            os.environ.pop("DATA_MODE", None)
        else:
            os.environ["DATA_MODE"] = original

    print()
    if FAILED:
        print(f"{len(FAILED)} FAILURE(S)\n")
        sys.exit(1)
    print(f"ALL {len(PASSED)} FEED CHECKS PASSED\n")
