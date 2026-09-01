from pathlib import Path
import json
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from models import SynthesisOutput, UserProfile, MarketSnapshot


BASE_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = BASE_DIR / "fixtures"

app = FastAPI(
    title="INVESTIGATOR API",
    version="1.0.0"
)


# Allow the frontend to communicate with the backend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Make fixtures available as static files.
app.mount(
    "/fixtures",
    StaticFiles(directory=FIXTURES_DIR),
    name="fixtures"
)


@app.get(
    "/api/analyze",
    response_model=SynthesisOutput
)
async def analyze(
    ticker: str,
    user_id: str
):
    fixture_path = (
        FIXTURES_DIR /
        "synthesis_example.json"
    )

    with open(
        fixture_path,
        "r",
        encoding="utf-8"
    ) as file:
        data = json.load(file)

    # Validate BEFORE returning.
    result = SynthesisOutput.model_validate(data)

    return result


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


@app.get(
    "/api/profiles",
    response_model=list[UserProfile]
)
async def get_profiles():

    profiles_path = (
        FIXTURES_DIR /
        "profiles.json"
    )

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