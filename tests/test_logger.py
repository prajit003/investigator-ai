import sys
from pathlib import Path

# Allow imports from the project root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import json

from models import Metrics
from logger import log_session, LOG_FILE


def main():

    print("===== LOGGER TEST =====")

    metrics = Metrics(
        total_latency_ms=120.5,
        avg_confidence=0.82,
        concentration_score=24.0,
        agents_ok=4,
        agents_failed=0
    )

    # Write one test session.
    log_session(
        ticker="RELIANCE",
        user_id="u1",
        recommendation="CAUTION",
        metrics=metrics
    )

    print("Log file:")
    print(LOG_FILE)

    # Read the log back.
    with open(
        LOG_FILE,
        "r",
        encoding="utf-8"
    ) as file:
        lines = file.readlines()

    assert len(lines) > 0

    # Parse the most recent JSON line.
    last_entry = json.loads(lines[-1])

    # Verify required fields.
    assert last_entry["ticker"] == "RELIANCE"
    assert last_entry["user_id"] == "u1"
    assert last_entry["recommendation"] == "CAUTION"

    assert (
        last_entry["metrics"]["total_latency_ms"]
        == 120.5
    )

    assert (
        last_entry["metrics"]["agents_ok"]
        == 4
    )

    assert (
        last_entry["metrics"]["agents_failed"]
        == 0
    )

    print()
    print("PASS: Session was written.")
    print("PASS: JSON log was read successfully.")
    print("PASS: Required fields are correct.")
    print()
    print("ALL LOGGING TESTS PASSED")


if __name__ == "__main__":
    main()