"""
Persistence for the feed layer. stdlib sqlite3 — no new dependency, and it
survives a restart, which is what makes "last known good" mean anything.

Three tables, three jobs:
  response_cache  raw provider payloads with a fetch time, so a TTL can be
                  applied and a dead provider can still be answered from disk
  daily_close     one row per symbol per session close. This is how RSI and
                  volatility come to exist at all: no keyless provider gives us
                  daily candles, so we accumulate our own history.
  symbol_map      NSE symbol -> Moneycontrol scId + BSE scrip code, so we ask
                  the resolver once per symbol ever, not once per request.
"""
import json
import pathlib
import sqlite3
import threading
import time
from typing import Any, Optional

DB_PATH = pathlib.Path(__file__).resolve().parent.parent / "data" / "cache.db"
# Reentrant on purpose: every writer takes the lock and then calls _conn(),
# which takes it again to lazily open the connection. A plain Lock deadlocks
# on the first write.
_LOCK = threading.RLock()
_CONN: Optional[sqlite3.Connection] = None

_SCHEMA = """
CREATE TABLE IF NOT EXISTS response_cache (
    key        TEXT PRIMARY KEY,
    fetched_at REAL NOT NULL,
    payload    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS daily_close (
    symbol TEXT NOT NULL,
    date   TEXT NOT NULL,
    close  REAL NOT NULL,
    volume INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (symbol, date)
);
CREATE TABLE IF NOT EXISTS symbol_map (
    symbol       TEXT PRIMARY KEY,
    mc_scid      TEXT NOT NULL DEFAULT '',
    bse_code     TEXT NOT NULL DEFAULT '',
    isin         TEXT NOT NULL DEFAULT '',
    company_name TEXT NOT NULL DEFAULT ''
);
"""


def _conn() -> sqlite3.Connection:
    global _CONN
    with _LOCK:
        if _CONN is None:
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            # check_same_thread=False: FastAPI serves requests off a threadpool,
            # and every write here is already serialised by _LOCK.
            _CONN = sqlite3.connect(DB_PATH, check_same_thread=False)
            _CONN.executescript(_SCHEMA)
            _CONN.commit()
        return _CONN


# ---- response cache ----

def get(key: str, ttl_s: float) -> Optional[Any]:
    """Return the cached payload if it is younger than ttl_s, else None."""
    row = _conn().execute(
        "SELECT fetched_at, payload FROM response_cache WHERE key = ?", (key,)
    ).fetchone()
    if not row or time.time() - row[0] > ttl_s:
        return None
    return json.loads(row[1])


def get_stale(key: str) -> tuple[Optional[Any], float]:
    """
    Return (payload, age_seconds) IGNORING the TTL, or (None, 0.0).

    This is the "last known good" path. It is deliberately separate from get():
    serving stale data is a decision the caller must make explicitly and must
    report in data_quality.warnings, never something a TTL check does quietly.
    """
    row = _conn().execute(
        "SELECT fetched_at, payload FROM response_cache WHERE key = ?", (key,)
    ).fetchone()
    if not row:
        return None, 0.0
    return json.loads(row[1]), time.time() - row[0]


def put(key: str, payload: Any) -> None:
    with _LOCK:
        c = _conn()
        c.execute("INSERT OR REPLACE INTO response_cache VALUES (?, ?, ?)",
                  (key, time.time(), json.dumps(payload)))
        c.commit()


# ---- daily close history ----

def record_close(symbol: str, date: str, close: float, volume: int = 0) -> None:
    """
    One row per symbol per day. Called on every quote; the primary key makes
    repeat calls within a session a no-op update rather than a duplicate.
    """
    with _LOCK:
        c = _conn()
        c.execute("INSERT OR REPLACE INTO daily_close VALUES (?, ?, ?, ?)",
                  (symbol.upper(), date, close, volume))
        c.commit()


def closes(symbol: str, limit: int = 120) -> list[float]:
    """Most recent `limit` closes in CHRONOLOGICAL order (oldest first)."""
    rows = _conn().execute(
        "SELECT close FROM daily_close WHERE symbol = ? ORDER BY date DESC LIMIT ?",
        (symbol.upper(), limit),
    ).fetchall()
    return [r[0] for r in reversed(rows)]


def close_count(symbol: str) -> int:
    return _conn().execute(
        "SELECT COUNT(*) FROM daily_close WHERE symbol = ?", (symbol.upper(),)
    ).fetchone()[0]


# ---- symbol map ----

def get_symbol(symbol: str) -> Optional[dict]:
    row = _conn().execute(
        "SELECT symbol, mc_scid, bse_code, isin, company_name FROM symbol_map WHERE symbol = ?",
        (symbol.upper(),),
    ).fetchone()
    if not row:
        return None
    keys = ("symbol", "mc_scid", "bse_code", "isin", "company_name")
    return dict(zip(keys, row))


def put_symbol(symbol: str, mc_scid: str = "", bse_code: str = "",
               isin: str = "", company_name: str = "") -> None:
    with _LOCK:
        c = _conn()
        c.execute("INSERT OR REPLACE INTO symbol_map VALUES (?, ?, ?, ?, ?)",
                  (symbol.upper(), mc_scid, bse_code, isin, company_name))
        c.commit()
