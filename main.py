from pathlib import Path
import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from models import SynthesisOutput, UserProfile


# --------------------------------------------------
# Paths
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = BASE_DIR / "fixtures"


# --------------------------------------------------
# FastAPI application
# --------------------------------------------------

app = FastAPI(
    title="INVESTIGATOR API",
    version="1.0.0"
)


# --------------------------------------------------
# CORS
# --------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------
# Serve fixtures as static files
# --------------------------------------------------

app.mount(
    "/fixtures",
    StaticFiles(directory=FIXTURES_DIR),
    name="fixtures"
)


# --------------------------------------------------
# ROUTE 1 — Analyze
# --------------------------------------------------

@app.get(
    "/api/analyze",
    response_model=SynthesisOutput
)
async def analyze(
    ticker: str,
    user_id: str
):
    fixture_path = FIXTURES_DIR / "synthesis_example.json"

    try:
        with open(
            fixture_path,
            "r",
            encoding="utf-8"
        ) as file:
            data = json.load(file)

        # Validate the fixture before returning it.
        result = SynthesisOutput.model_validate(data)

        return result

    except Exception as exc:
        # The fixture should always be valid.
        # This prevents an unexpected 500 during development.
        print(f"Analyze error: {exc}")

        # Re-raise for now so we notice a broken fixture.
        raise


# --------------------------------------------------
# ROUTE 2 — Tickers
# --------------------------------------------------

@app.get(
    "/api/tickers",
    response_model=list[str]
)
async def get_tickers():

    return [
        "RELIANCE",
        "TCS",
        "INFY"
    ]


# --------------------------------------------------
# ROUTE 3 — Profiles
# --------------------------------------------------

@app.get(
    "/api/profiles",
    response_model=list[UserProfile]
)
async def get_profiles():

    profiles_path = FIXTURES_DIR / "profiles.json"

    with open(
        profiles_path,
        "r",
        encoding="utf-8"
    ) as file:
        data = json.load(file)

    return [
        UserProfile.model_validate(profile)
        for profile in data
    ]