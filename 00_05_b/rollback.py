"""
Course 2 — Lesson 4: Implement Agent Recovery

Goal:
- Demonstrate a simple rollback pattern for agent failures:
  1) detect an unsafe output
  2) quarantine the unsafe file
  3) restore a prior known-good snapshot

Usage:
  python rollback.py \
    --output 00_05_b/out/shopping_summary.json \
    --snapshots 00_05_b/snapshot \
    --quarantine 00_05_b/quarantine \
    --actionlog 00_05_b/action_log.jsonl

Notes:
- This is intentionally simple and file-based.
- It assumes you already have at least one "before" snapshot JSON for the output file.
"""

import argparse
import json
import os
import re
import shutil
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

def utc_now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

# -----------------------------
# Snapshot selection + recovery
# -----------------------------
def list_candidate_snapshots(snapshots_dir: str) -> List[str]:
    if not os.path.isdir(snapshots_dir):
        return []
    candidates: List[str] = []
    for name in os.listdir(snapshots_dir):
        # Your naming has been: shopping_summary.json.before.<timestamp>.<runid>.json
        if name.startswith("shopping_summary.json.before.") and name.endswith(".json"):
            candidates.append(os.path.join(snapshots_dir, name))
    candidates.sort()
    return candidates


def choose_latest_snapshot(snapshots_dir: str) -> Optional[str]:
    candidates = list_candidate_snapshots(snapshots_dir)
    if not candidates:
        return None
    # filenames are sortable by timestamp if you embed it; fall back to mtime if needed
    # We'll prefer the most recently modified file for robustness.
    candidates.sort(key=lambda p: os.path.getmtime(p))
    return candidates[-1]


def quarantine_file(
    output_path: str,
    quarantine_dir: str,
    reason: str,
) -> Optional[str]:
    if not os.path.exists(output_path):
        return None

    os.makedirs(quarantine_dir, exist_ok=True)
    base = os.path.basename(output_path)
    ts = utc_now_compact()
    quarantined_name = f"{base}.quarantine.{reason}.{ts}.json"
    quarantined_path = os.path.join(quarantine_dir, quarantined_name)

    shutil.copy2(output_path, quarantined_path)
    return quarantined_path


def restore_snapshot(snapshot_path: str, output_path: str) -> None:
    # Overwrite the output with the known-good snapshot
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    shutil.copy2(snapshot_path, output_path)

# -----------------------------
# Lightweight action log
# -----------------------------
def append_action_log(action_log_path: str, event: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(action_log_path) or ".", exist_ok=True)
    with open(action_log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")

# -----------------------------
# Main
# -----------------------------
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, help="Path to current shopping_summary.json")
    parser.add_argument("--snapshots", required=True, help="Directory containing before snapshots")
    parser.add_argument("--quarantine", required=True, help="Directory to store quarantined files")
    parser.add_argument("--actionlog", required=True, help="Path to action_log.jsonl")
    parser.add_argument(
        "--snapshot",
        default=None,
        help="Optional: explicit snapshot file to restore (otherwise chooses latest)",
    )
    args = parser.parse_args()

    if not os.path.exists(args.output):
        raise FileNotFoundError(f"Output file not found: {args.output}")

    # Select snapshot (known-good)
    snapshot_path = args.snapshot or choose_latest_snapshot(args.snapshots)
    if not snapshot_path:
        raise FileNotFoundError(
            f"No snapshots found in {args.snapshots}. "
            "Create a before snapshot first, then rerun recovery."
        )

    # Quarantine the unsafe file
    quarantined_path = quarantine_file(args.output, args.quarantine, reason="sensitive_leak")

    # Restore snapshot into output_path (rollback)
    restore_snapshot(snapshot_path, args.output)

    # Log the recovery action (lightweight transaction log)
    append_action_log(
        args.actionlog,
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event_type": "recovery_performed",
            "output_path": args.output,
            "snapshot_path": snapshot_path,
            "quarantined_path": quarantined_path
        },
    )

    print("\n=== Recovery Complete ===")
    print(f"Restored snapshot -> {args.output}")
    print(f"Snapshot used      -> {snapshot_path}")
    if quarantined_path:
        print(f"Quarantined copy   -> {quarantined_path}")
    print(f"Action log         -> {args.actionlog}")
    print("========================\n")


if __name__ == "__main__":
    main()
