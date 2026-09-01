"""
Symbol resolution: an NSE symbol is not enough to ask anyone for data.

Moneycontrol wants its own opaque code (RELIANCE is "RI", Infosys is "IT",
Bharti Airtel is "BTV"), and BSE wants a numeric scrip code. Neither is
derivable from the symbol, so they have to be looked up.

data/universe.json seeds the common names — every one of those was resolved
against the live endpoint rather than guessed, because guessing got four of
eleven wrong. Anything not seeded is resolved once via autosuggest and cached in
data/cache.db, so a symbol costs at most one extra request in its lifetime.
"""
import json
import pathlib
import re
from functools import lru_cache
from typing import Optional

from feeds import cache, http

UNIVERSE_PATH = pathlib.Path(__file__).resolve().parent.parent / "data" / "universe.json"
AUTOSUGGEST = "https://www.moneycontrol.com/mccode/common/autosuggestion_solr.php"

# "Reliance Industries&nbsp;<span>INE002A01018, RELIANCE, 500325</span>"
#                                  ^isin       ^nse symbol ^bse code
_DIS = re.compile(r"<span>([^<]*)</span>")


@lru_cache(maxsize=1)
def _universe() -> dict:
    if not UNIVERSE_PATH.exists():
        return {"watchlist": [], "seed": []}
    return json.loads(UNIVERSE_PATH.read_text())


def watchlist() -> list[str]:
    return [s.upper() for s in _universe().get("watchlist", [])]


@lru_cache(maxsize=1)
def _seed() -> dict[str, dict]:
    return {row["symbol"].upper(): row for row in _universe().get("seed", [])}


def _from_seed(symbol: str) -> Optional[dict]:
    row = _seed().get(symbol.upper())
    if not row:
        return None
    return {"symbol": row["symbol"].upper(), "mc_scid": row.get("mc_scid", ""),
            "bse_code": row.get("bse_code", ""), "isin": row.get("isin", ""),
            "company_name": row.get("company_name", ""),
            # The id the exchange currently lists under, when it differs from
            # the name people search by (NSE renamed ZOMATO to ETERNAL).
            "nse_id": row.get("nse_id", row["symbol"]).upper()}


async def resolve(symbol: str) -> Optional[dict]:
    """
    Return {symbol, mc_scid, bse_code, isin, company_name} or None.

    Order: the seed file, then the sqlite cache, then the network. A resolution
    is written back to the cache so this is a once-ever cost per symbol.
    """
    symbol = symbol.upper()

    seeded = _from_seed(symbol)
    if seeded:
        return seeded

    cached = cache.get_symbol(symbol)
    if cached:
        return {**cached, "nse_id": cached.get("nse_id") or symbol}

    try:
        rows = await http.fetch_json(
            AUTOSUGGEST,
            params={"classic": "true", "query": symbol, "type": "1", "format": "json"},
        )
    except Exception:
        return None

    if not isinstance(rows, list):
        return None

    for row in rows[:8]:
        m = _DIS.search(row.get("pdt_dis_nm", ""))
        if not m:
            continue
        bits = [b.strip() for b in m.group(1).split(",")]
        # Require an EXACT symbol match. Autosuggest is fuzzy — a query for one
        # symbol cheerfully returns a different company's listing, and pricing
        # the wrong company is worse than reporting no data at all.
        if len(bits) >= 3 and bits[1].upper() == symbol:
            out = {"symbol": symbol, "mc_scid": row.get("sc_id", ""),
                   "bse_code": bits[2], "isin": bits[0],
                   "company_name": row.get("name", "")}
            cache.put_symbol(**out)
            # An exact-match resolution is by definition listed under the
            # symbol we asked for.
            return {**out, "nse_id": symbol}
    return None
