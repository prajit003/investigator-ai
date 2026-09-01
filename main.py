"""
INVESTIGATOR backend. Three routes, one response shape.

The frontend consumes `investigation_result` (docs/ARCHITECTURE.md §12) and
nothing else. Adding a fourth route means adding a second integration point;
don't.
"""
import pathlib

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import store
from contracts import InvestigationResult
from orchestrator import investigate

BASE = pathlib.Path(__file__).resolve().parent
FIXTURES = BASE / "fixtures"

app = FastAPI(title="INVESTIGATOR API", version="1.0.0")

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# Serve fixtures so the frontend can develop against them before the API is live.
FIXTURES.mkdir(exist_ok=True)
app.mount("/fixtures", StaticFiles(directory=FIXTURES), name="fixtures")


@app.get("/api/symbols", response_model=list[str])
async def get_symbols():
    """Only symbols we have BOTH market data and filings for — never offer a
    symbol in the UI that would return empty evidence."""
    return store.symbols()


@app.get("/api/profiles")
async def get_profiles():
    return [{"user": u.model_dump(), "portfolio": p.model_dump()}
            for u, p in store.profiles().values()]


@app.get("/api/analyze", response_model=InvestigationResult)
async def analyze(symbol: str, user_id: str):
    """
    The whole pipeline. This must never return a 500 for a data problem —
    a dead agent is a DEGRADED result, not an error. Only an unknown symbol
    or user is a client error.
    """
    try:
        return await investigate(symbol, user_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


# Mounted last on purpose: a mount at "/" would shadow the API routes above.
FRONTEND = BASE / "frontend"
if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
