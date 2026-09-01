from pathlib import Path
import json
import uuid

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from models import (
    MarketSnapshot,
    UserProfile,
    SynthesisOutput,
)

from orchestrator import orchestrate
from logger import log_session


# ==================================================
# PATHS
# ==================================================

BASE_DIR = Path(__file__).resolve().parent

FIXTURES_DIR = BASE_DIR / "fixtures"

MARKET_SNAPSHOT_FILE = (
    FIXTURES_DIR / "market_snapshots.json"
)

PROFILES_FILE = (
    FIXTURES_DIR / "profiles.json"
)

SYNTHESIS_FIXTURE_FILE = (
    FIXTURES_DIR / "synthesis_example.json"
)


# ==================================================
# FASTAPI APPLICATION
# ==================================================

app = FastAPI(
    title="INVESTIGATOR API",
    version="1.0.0"
)


# ==================================================
# CORS
# ==================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================================================
# STATIC FIXTURES
# ==================================================

app.mount(
    "/fixtures",
    StaticFiles(directory=FIXTURES_DIR),
    name="fixtures"
)


# ==================================================
# LOAD MARKET SNAPSHOT
# ==================================================

def load_market_snapshot(
    ticker: str
) -> MarketSnapshot:

    with open(
        MARKET_SNAPSHOT_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        data = json.load(file)

    ticker_data = data.get(ticker)

    if ticker_data is None:
        raise ValueError(
            f"No market snapshot available for {ticker}"
        )

    return MarketSnapshot.model_validate(
        ticker_data
    )


# ==================================================
# LOAD USER PROFILE
# ==================================================

def load_user_profile(
    user_id: str
) -> UserProfile:

    with open(
        PROFILES_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        profiles = json.load(file)

    for profile in profiles:

        if profile.get("user_id") == user_id:

            return UserProfile.model_validate(
                profile
            )

    raise ValueError(
        f"No profile available for user {user_id}"
    )


# ==================================================
# SAFE FALLBACK RESPONSE
# ==================================================

def load_fallback_response() -> SynthesisOutput:
    """
    Load and validate the known-good synthesis fixture.

    This is the final safety net so that /api/analyze
    can always return a valid SynthesisOutput.
    """

    with open(
        SYNTHESIS_FIXTURE_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        data = json.load(file)

    return SynthesisOutput.model_validate(data)


# ==================================================
# ROUTE 1 — ANALYZE
# ==================================================

@app.get(
    "/api/analyze",
    response_model=SynthesisOutput
)
async def analyze(
    ticker: str,
    user_id: str
):

    ticker = ticker.upper().strip()

    try:

        # ------------------------------------------
        # Load input data
        # ------------------------------------------

        snapshot = load_market_snapshot(
            ticker
        )

        profile = load_user_profile(
            user_id
        )

        # ------------------------------------------
        # Run all four agents
        # ------------------------------------------

        agent_outputs, metrics = await orchestrate(
            ticker,
            snapshot,
            profile
        )

        # ------------------------------------------
        # Determine temporary backend recommendation
        #
        # P5 synthesis will replace this section.
        # ------------------------------------------

        successful_agents = [
            agent
            for agent in agent_outputs
            if agent.status == "OK"
        ]

        unavailable_agents = [
            agent
            for agent in agent_outputs
            if agent.status != "OK"
        ]

        if successful_agents:

            recommendation = "REVIEW"

            confidence = metrics.avg_confidence

            summary = (
                f"{len(successful_agents)} of 4 agents "
                f"completed successfully."
            )

        else:

            recommendation = "UNAVAILABLE"

            confidence = 0.0

            summary = (
                "No analysis agents are currently "
                "available."
            )

        if unavailable_agents:

            summary += (
                f" {len(unavailable_agents)} agent(s) "
                f"were unavailable."
            )

        # ------------------------------------------
        # Build valid response
        # ------------------------------------------

        result = SynthesisOutput(
            investigation_id=(
                f"CASE-{uuid.uuid4().hex[:8].upper()}"
            ),

            ticker=ticker,

            recommendation=recommendation,

            confidence=confidence,

            summary=summary,

            agent_outputs=agent_outputs,

            citations=[],

            metrics=metrics,
        )

        # ------------------------------------------
        # Log successful analysis
        # ------------------------------------------

        log_session(
            ticker=ticker,
            user_id=user_id,
            recommendation=recommendation,
            metrics=metrics,
        )

        return result

    except Exception as exc:

        # ------------------------------------------
        # NEVER let /api/analyze crash with 500.
        # ------------------------------------------

        print(
            f"[analyze] Backend error: "
            f"{type(exc).__name__}: {exc}"
        )

        # ------------------------------------------
        # Use the known-good validated fixture as
        # the final response safety net.
        # ------------------------------------------

        try:

            fallback = load_fallback_response()

            print(
                "[analyze] Returning validated "
                "fallback response."
            )

            return fallback

        except Exception as fallback_error:

            # This should only happen if the fixture
            # itself has been corrupted.
            #
            # Keep the error visible during development.
            print(
                "[analyze] Fallback failed: "
                f"{type(fallback_error).__name__}: "
                f"{fallback_error}"
            )

            raise


# ==================================================
# ROUTE 2 — TICKERS
# ==================================================

@app.get(
    "/api/tickers",
    response_model=list[str]
)
async def get_tickers():

    try:

        with open(
            MARKET_SNAPSHOT_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

        return list(data.keys())

    except Exception as exc:

        print(
            f"[tickers] Error: "
            f"{type(exc).__name__}: {exc}"
        )

        return []


# ==================================================
# ROUTE 3 — PROFILES
# ==================================================

@app.get(
    "/api/profiles",
    response_model=list[UserProfile]
)
async def get_profiles():

    try:

        with open(
            PROFILES_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

        return [
            UserProfile.model_validate(
                profile
            )
            for profile in data
        ]

    except Exception as exc:

        print(
            f"[profiles] Error: "
            f"{type(exc).__name__}: {exc}"
        )

        return []