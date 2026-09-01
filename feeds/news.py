"""
Live headlines, via Google News RSS scoped to India.

Chosen because it is the only keyless headline source that answered: it returns
dated, publisher-attributed items, it covers the Indian financial press the way
a retail investor actually encounters it, and it needs no signup.

Parsed with stdlib xml.etree rather than feedparser — one fewer dependency for a
format we use six fields of.

What the sentiment agent gets back is a list of dicts, not bare strings, because
"Company X falls 5%" from a wire service two hours ago and the same words from a
blog three years ago are not the same evidence.
"""
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Optional
import xml.etree.ElementTree as ET

from feeds import FIXTURES, cache, http, mode, symbols

RSS = "https://news.google.com/rss/search"
TTL_S = 900.0            # 15 minutes; headlines do not move faster than that
WINDOW_DAYS = 7
MAX_ITEMS = 25
# Google News emits <source> UNNAMESPACED in this feed, despite declaring the
# news.google.com namespace on the channel. Looking it up namespaced silently
# returns nothing and every headline keeps its " - Publisher" suffix.
_SOURCE_TAG = "source"


def _query(company: str, symbol: str) -> str:
    # Quote the company name so a multi-word name is not scattered across the
    # index, and add "share OR stock" to keep out non-financial coverage of the
    # same brand — a food-delivery company's restaurant news is not a signal.
    return f'"{company}" (share OR stock OR shares OR NSE OR results) when:{WINDOW_DAYS}d'


def _parse(xml_text: str) -> list[dict]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS + 1)
    out, seen = [], set()
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        if not title:
            continue

        src_el = item.find(_SOURCE_TAG)
        publisher = (src_el.text or "").strip() if src_el is not None else ""
        # Google appends " - Publisher" to every title; strip it so the lexicon
        # scores the headline, not the outlet's name.
        if publisher and title.endswith(f" - {publisher}"):
            title = title[: -len(publisher) - 3].strip()

        norm = title.lower()
        if norm in seen:
            continue
        seen.add(norm)

        published = ""
        raw_date = item.findtext("pubDate")
        if raw_date:
            try:
                dt = parsedate_to_datetime(raw_date)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt < cutoff:
                    continue
                published = dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M")
            except (TypeError, ValueError):
                published = ""

        out.append({"title": title, "publisher": publisher,
                    "published": published, "url": (item.findtext("link") or "").strip()})
        if len(out) >= MAX_ITEMS:
            break
    return out


def _fixture(symbol: str) -> list[dict]:
    """The hand-written headlines, lifted into the live shape."""
    import json
    import pathlib
    path = pathlib.Path(__file__).resolve().parent.parent / "data" / "news" / "news.json"
    if not path.exists():
        return []
    for row in json.loads(path.read_text() or "[]"):
        if row.get("symbol", "").upper() == symbol.upper():
            return [{"title": h, "publisher": "fixture", "published": "", "url": ""}
                    for h in row.get("headlines", [])]
    return []


async def headlines_with_warnings(symbol: str) -> tuple[list[dict], list[str]]:
    """Returns (headlines, warnings). Never raises."""
    symbol = symbol.upper()
    key = f"news:{symbol}"
    warnings: list[str] = []

    if mode() != FIXTURES:
        fresh = cache.get(key, TTL_S)
        if fresh:
            return fresh, warnings

        ref = await symbols.resolve(symbol)
        company = (ref or {}).get("company_name") or symbol
        try:
            xml_text = await http.fetch_text(RSS, params={
                "q": _query(company, symbol), "hl": "en-IN", "gl": "IN", "ceid": "IN:en"})
            items = _parse(xml_text)
        except Exception as e:
            items, warnings = [], [f"News feed failed for {symbol}: {type(e).__name__}"]

        if items:
            cache.put(key, items)
            return items, warnings

        stale, age = cache.get_stale(key)
        if stale:
            warnings.append(f"Live news unavailable for {symbol}; using headlines "
                            f"{int(age // 60)} minute(s) old.")
            return stale, warnings

    from feeds import may_use_fixtures
    if not may_use_fixtures():
        return [], warnings + [f"No live news for {symbol} and DATA_MODE=live "
                               f"forbids substituting fixture headlines."]

    items = _fixture(symbol)
    if items and mode() != FIXTURES:
        warnings.append(f"Live news unavailable for {symbol}; fell back to "
                        f"hand-written headlines, which are NOT real coverage.")
    return items, warnings


async def headlines(symbol: str) -> list[dict]:
    items, _ = await headlines_with_warnings(symbol)
    return items
