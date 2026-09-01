from pathlib import Path
import json
from datetime import datetime, timezone
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "sessions.jsonl"


def log_session(
    ticker: str,
    user_id: str,
    recommendation: str,
    metrics: Any,
) -> None:
    """
    Append one analysis session as a single JSON line.
    """

    LOG_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    if hasattr(metrics, "model_dump"):
        metrics_data = metrics.model_dump()
    else:
        metrics_data = metrics

    entry = {
        "timestamp": datetime.now(
            timezone.utc
        ).isoformat(),

        "ticker": ticker,

        "user_id": user_id,

        "recommendation": recommendation,

        "metrics": metrics_data,
    }

    with open(
        LOG_FILE,
        "a",
        encoding="utf-8"
    ) as file:

        file.write(
            json.dumps(entry)
            + "\n"
        )