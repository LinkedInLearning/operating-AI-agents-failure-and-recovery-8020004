import os
import json
import uuid
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# One run_id per execution
# ---------------------------------------------------------------------------
RUN_ID = str(uuid.uuid4())

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dirs(*paths: str) -> None:
    for path in paths:
        os.makedirs(path, exist_ok=True)


# ---------------------------------------------------------------------------
# Structured logging (JSONL)
# ---------------------------------------------------------------------------
def log_event(log_path: str, event_type: str, **fields: Any) -> None:
    """
    Write a single structured event as a JSON line.
    """
    event = {
        "ts": utc_now_iso(),
        "run_id": RUN_ID,
        "event_type": event_type,
        **fields,
    }

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


def summarize_run(log_path: str) -> dict[str, int]:
    """
    Return a count of event types for the current run_id.
    """
    counts: dict[str, int] = {}

    if not os.path.exists(log_path):
        return counts

    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                continue

            if evt.get("run_id") != RUN_ID:
                continue

            event_type = evt.get("event_type", "unknown")
            counts[event_type] = counts.get(event_type, 0) + 1

    return counts
