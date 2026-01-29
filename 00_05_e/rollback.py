"""
Course 2 — Lesson 4: Implement Agent Recovery

Goal:
- Demonstrate a simple rollback pattern for agent failures:
  1) detect an unsafe output
  2) quarantine the unsafe file
  3) restore a prior known-good snapshot

Usage:
  python recover_output.py \
    --output c2-lesson1-trigger-bad-agent-action/out/shopping_summary.json \
    --snapshots c2-lesson3-assess-failure-impact/snapshot \
    --quarantine c2-lesson4-implement-agent-recovery/quarantine \
    --actionlog c2-lesson4-implement-agent-recovery/action_log.jsonl

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


# -----------------------------
# Simple sensitive scanners
# -----------------------------
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)

# Matches:
# - "ending in 4821"
# - "card ending 4821"
# - "****4821"
CARD_LAST4_RE = re.compile(
    r"(?:ending\s+in|card\s+ending|\*{2,})\s*(?P<last4>\d{4})\b",
    re.IGNORECASE,
)


def utc_now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def dump_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)


def flatten_text(obj: Any) -> str:
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, (int, float, bool)):
        return str(obj)
    if isinstance(obj, list):
        return "\n".join(flatten_text(x) for x in obj)
    if isinstance(obj, dict):
        parts: List[str] = []
        for k, v in obj.items():
            parts.append(str(k))
            parts.append(flatten_text(v))
        return "\n".join(parts)
    return str(obj)


def scan_for_sensitive(text: str) -> List[Dict[str, str]]:
    findings: List[Dict[str, str]] = []

    for m in CARD_LAST4_RE.finditer(text):
        findings.append(
            {
                "type": "card_last4",
                "match": m.group(0).strip(),
                "value": m.group("last4"),
            }
        )

    for m in EMAIL_RE.finditer(text):
        findings.append(
            {
                "type": "email",
                "match": m.group(0),
                "value": m.group(0),
            }
        )

    return findings


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

    # 1) Scan the current output for sensitive patterns
    output_obj = load_json(args.output)
    text = flatten_text(output_obj)
    findings = scan_for_sensitive(text)

    print("\n=== Recovery Check ===")
    if not findings:
        print("No sensitive patterns found. No recovery needed.")
        append_action_log(
            args.actionlog,
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "event_type": "recovery_skipped",
                "output_path": args.output,
                "reason": "no_sensitive_patterns",
            },
        )
        return

    print(f"Found {len(findings)} sensitive finding(s). Recovery will run.")
    for fnd in findings:
        if fnd["type"] == "card_last4":
            print(f"- card_last4: {fnd['match']} (last4={fnd['value']})")
        else:
            print(f"- {fnd['type']}: {fnd['value']}")

    # 2) Select snapshot (known-good)
    snapshot_path = args.snapshot or choose_latest_snapshot(args.snapshots)
    if not snapshot_path:
        raise FileNotFoundError(
            f"No snapshots found in {args.snapshots}. "
            "Create a before snapshot first, then rerun recovery."
        )

    # 3) Quarantine the unsafe file
    quarantined_path = quarantine_file(args.output, args.quarantine, reason="sensitive_leak")

    # 4) Restore snapshot into output_path (rollback)
    restore_snapshot(snapshot_path, args.output)

    # 5) Log the recovery action (lightweight transaction log)
    append_action_log(
        args.actionlog,
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event_type": "recovery_performed",
            "output_path": args.output,
            "snapshot_path": snapshot_path,
            "quarantined_path": quarantined_path,
            "findings": findings,
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
