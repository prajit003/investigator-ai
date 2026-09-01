"""
Real regulatory disclosures, from the BSE corporate-announcements API.

These are the actual filings a company makes under SEBI's LODR regulations —
the same documents a professional desk reads — and each one carries a public PDF
that anyone can open. That is what makes a citation from this corpus checkable
rather than merely plausible.

LATENCY BUDGET, and why the design is shaped this way: the filing agent has 12
seconds (safety.AGENT_TIMEOUT_S) and PDFs here run to hundreds of kilobytes. So
a request-time call does exactly one cheap thing — fetch the announcement list —
and builds chunks from the HEADLINE text, which is real filed prose. PDF bodies
are used only when they are already extracted and cached. Warm them ahead of a
demo with:

    python -m feeds.filings RELIANCE TCS INFY

That way the corpus is real either way, and a cold start degrades to shorter
real citations rather than to a timeout.
"""
import asyncio
import io
import pathlib
import re
from datetime import datetime, timedelta
from typing import Optional

from feeds import FIXTURES, cache, http, mode, symbols

ANN_URL = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"
ATTACH_URL = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/{name}"
PDF_DIR = pathlib.Path(__file__).resolve().parent.parent / "data" / "filings" / "cache"

LIST_TTL_S = 6 * 3600
LOOKBACK_DAYS = 120
MAX_DOCS = 8               # per symbol, newest first
MAX_CHUNKS_PER_DOC = 3
CHUNK_WORDS = 90
MIN_CHUNK_WORDS = 25

# BSE category -> our SourceType. Anything unmapped is a FILING, which is what
# a corporate announcement is by default.
_TYPE_BY_CATEGORY = {
    "Result": "FILING",
    "Company Update": "FILING",
    "AGM/EGM": "SHAREHOLDER_LETTER",
    "Board Meeting": "FILING",
    "Corp. Action": "FILING",
    "Investor Presentation": "TRANSCRIPT",
    "Earnings Call Transcript": "TRANSCRIPT",
}
_WS = re.compile(r"\s+")


def _clean(text: str) -> str:
    """Filed prose arrives with double apostrophes and hard line breaks."""
    return _WS.sub(" ", (text or "").replace("''", "'")).strip()


def _source_type(row: dict) -> str:
    cat = (row.get("CATEGORYNAME") or "").strip()
    sub = (row.get("SUBCATNAME") or "").strip()
    if "transcript" in sub.lower() or "transcript" in cat.lower():
        return "TRANSCRIPT"
    return _TYPE_BY_CATEGORY.get(cat, "FILING")


def _chunk_words(text: str, size: int = CHUNK_WORDS) -> list[str]:
    words = text.split()
    return [" ".join(words[i:i + size]) for i in range(0, len(words), size)]


# A filing PDF opens with a letterhead and closes with a signature block. Taking
# the first N chunks therefore cites a registered office address as if it were
# fundamental evidence — real text, correctly attributed, and worthless. So rank
# chunks by substance instead of position.
_BOILERPLATE = re.compile(
    r"regd\.?\s*office|registered office|maker chambers|dalal street|telefax|"
    r"\bCIN[-\s]?[LU]\d|e-?mail\s*:|website\s*:|phone\s*#|encl\.?\s*:|"
    r"scrip code|stock exchange of india limited|bandra[- ]kurla|"
    r"company secretary and compliance officer|thanking you|yours faithfully",
    re.I)
_SUBSTANCE = re.compile(
    r"\b(revenue|ebitda|margin|profit|loss|growth|crore|lakh|turnover|debt|"
    r"borrowing|capex|dividend|earnings|guidance|order book|subscriber|"
    r"acquisition|impairment|contingent|liabilit|segment|quarter|per cent|%)",
    re.I)


def _substance_score(piece: str) -> float:
    """Higher is more worth citing. Negative means it is letterhead."""
    hits = len(_SUBSTANCE.findall(piece))
    noise = len(_BOILERPLATE.findall(piece))
    digits = sum(c.isdigit() for c in piece) / max(len(piece), 1)
    # A dense run of digits with no financial vocabulary is a phone number, a
    # pin code or a CIN — not a figure worth quoting.
    return hits * 2.0 - noise * 3.0 + (2.0 if hits and digits > 0.02 else 0.0)


def _pick_chunks(text: str, limit: int) -> list[str]:
    """Best `limit` chunks by substance, returned in document order so a quote
    still reads the way the filing reads."""
    pieces = [p for p in _chunk_words(text) if len(p.split()) >= 8]
    if not pieces:
        return []
    ranked = sorted(enumerate(pieces), key=lambda ip: -_substance_score(ip[1]))
    kept = [ip for ip in ranked[:limit] if _substance_score(ip[1]) > -1.0]
    if not kept:
        # Nothing substantive in the body. The filed headline is better evidence
        # than an address block, and the caller falls back to it.
        return []
    return [p for _, p in sorted(kept)]


# ---- announcement list ----

async def _announcements(symbol: str, bse_code: str) -> list[dict]:
    key = f"filings:list:{symbol}"
    fresh = cache.get(key, LIST_TTL_S)
    if fresh is not None:
        return fresh

    today = datetime.now()
    payload = await http.fetch_json(ANN_URL, params={
        "pageno": "1", "strCat": "-1",
        "strPrevDate": (today - timedelta(days=LOOKBACK_DAYS)).strftime("%Y%m%d"),
        "strScrip": bse_code, "strSearch": "P",
        "strToDate": today.strftime("%Y%m%d"), "strType": "C", "subcategory": "-1",
    })
    rows = payload.get("Table") if isinstance(payload, dict) else None
    rows = rows or []
    cache.put(key, rows)
    return rows


# ---- PDF text ----

async def _pdf_text(row: dict, *, download: bool) -> str:
    """
    Extracted body text for one announcement, or "".

    `download=False` is the request-time path: use what is already on disk and
    never pay for a fetch inside an agent's timeout budget.
    """
    name = (row.get("ATTACHMENTNAME") or "").strip()
    if not name or not name.lower().endswith(".pdf"):
        return ""

    key = f"filings:pdf:{name}"
    cached = cache.get(key, ttl_s=float("inf"))
    if cached is not None:
        return cached
    if not download:
        return ""

    PDF_DIR.mkdir(parents=True, exist_ok=True)
    path = PDF_DIR / name
    try:
        if not path.exists():
            path.write_bytes(await http.fetch_bytes(ATTACH_URL.format(name=name)))
        text = _extract(path.read_bytes())
    except Exception:
        text = ""

    # Cache the empty result too: a scanned, image-only filing yields no text
    # and must not be re-downloaded on every request to prove it again.
    cache.put(key, text)
    return text


def _extract(blob: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    try:
        reader = PdfReader(io.BytesIO(blob))
        # First few pages only: the substance of a LODR filing is at the front,
        # and the tail is signature blocks and boilerplate annexures.
        pages = [(p.extract_text() or "") for p in reader.pages[:4]]
    except Exception:
        return ""
    return _clean(" ".join(pages))


# ---- corpus construction ----

def _chunks_from(row: dict, symbol: str, body: str) -> list[dict]:
    news_id = (row.get("NEWSID") or row.get("BSENewsid") or "").replace("-", "")[:8].upper()
    headline = _clean(row.get("HEADLINE") or "")
    subject = _clean(row.get("NEWSSUB") or "")
    date = (row.get("NEWS_DT") or row.get("DT_TM") or "")[:10]
    attach = (row.get("ATTACHMENTNAME") or "").strip()

    base = {
        "symbol": symbol.upper(),
        "source_name": subject or headline[:80] or f"BSE filing {news_id}",
        "source_type": _source_type(row),
        "source_date": date,
        "section": (row.get("CATEGORYNAME") or "Corporate Announcement").strip(),
        "url": ATTACH_URL.format(name=attach) if attach else "",
    }

    # Prefer substantive PDF body text; fall back to the filed headline, which
    # is real prose the company submitted, not a summary we wrote.
    pieces = _pick_chunks(body, MAX_CHUNKS_PER_DOC) if body else []
    if not pieces and headline and len(headline.split()) >= 8:
        pieces = [headline]
    if not pieces:
        return []

    return [{**base, "chunk_id": f"BSE{news_id}_c{i + 1}", "page": i + 1, "text": piece}
            for i, piece in enumerate(pieces)]


async def corpus_with_warnings(symbol: str, *,
                               download: bool = False) -> tuple[list[dict], list[str]]:
    """
    Live filing chunks for one symbol, in rag.ingest's chunk shape.
    Returns ([], warnings) rather than raising — an empty corpus is a degraded
    fundamental dimension, which the filing agent already reports honestly.
    """
    symbol = symbol.upper()
    warnings: list[str] = []
    if mode() == FIXTURES:
        return [], warnings

    ref = await symbols.resolve(symbol)
    if not ref or not ref.get("bse_code"):
        return [], [f"No BSE scrip code for {symbol}; live filings unavailable."]

    try:
        rows = await _announcements(symbol, ref["bse_code"])
    except Exception as e:
        return [], [f"BSE filings feed failed for {symbol}: {type(e).__name__}"]

    chunks, with_body = [], 0
    for row in rows[:MAX_DOCS]:
        body = await _pdf_text(row, download=download)
        if body:
            with_body += 1
        chunks.extend(_chunks_from(row, symbol, body))

    if not chunks:
        warnings.append(f"BSE returned no usable filings for {symbol} in the last "
                        f"{LOOKBACK_DAYS} days.")
    elif with_body == 0:
        warnings.append(f"Citing filed headlines for {symbol}: no filing PDF is "
                        f"extracted yet. Run `python -m feeds.filings {symbol}` "
                        f"to include full document text.")
    return chunks, warnings


async def corpus(symbol: str, *, download: bool = False) -> list[dict]:
    chunks, _ = await corpus_with_warnings(symbol, download=download)
    return chunks


async def warm(symbols_: list[str]) -> None:
    """Download and extract PDFs ahead of time. Run before a demo."""
    try:
        await _warm(symbols_)
    finally:
        # Same event loop that opened the client, or httpx raises on close.
        await http.aclose()


async def _warm(symbols_: list[str]) -> None:
    for sym in symbols_:
        chunks, warns = await corpus_with_warnings(sym, download=True)
        bodies = len({c["source_name"] for c in chunks})
        print(f"{sym:12} {len(chunks):3d} chunk(s) from {bodies} document(s)")
        for w in warns:
            print(f"             note: {w}")


if __name__ == "__main__":
    import sys
    from feeds.symbols import watchlist

    targets = [s.upper() for s in sys.argv[1:]] or watchlist()
    asyncio.run(warm(targets))
