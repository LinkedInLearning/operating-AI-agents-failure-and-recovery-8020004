"""
Course 2 — Lesson 5: Validate Recovery Outcomes

Goal:
- Verify the system is back to a known-good state after recovery
- Confirm recovery was logged
- Confirm outputs meet basic integrity constraints (schema + sensitive scan)

Usage:
  python validate.py --output 00_05_b/out/shopping_summary.json --snapshot 00_05_b/snapshot --action-log 00_05_b/action_log.jsonl 

Notes:
- If you pass --baseline, we validate against that exact snapshot file.
- Otherwise, we choose the most recent snapshot in --snapshot.
"""

import argparse
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Files + snapshots
# ---------------------------------------------------------------------------
def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def iter_jsonl(path: str) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    if not os.path.exists(path):
        return events
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def most_recent_snapshot(snapshot_dir: str, output_filename: str) -> Optional[str]:
    if not os.path.isdir(snapshot_dir):
        return None

    candidates: List[str] = []
    for name in os.listdir(snapshot_dir):
        if output_filename in name:
            candidates.append(os.path.join(snapshot_dir, name))

    if not candidates:
        return None

    # Prefer mtime for “most recent”
    candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return candidates[0]

# ---------------------------------------------------------------------------
# Integrity checks
# ---------------------------------------------------------------------------
#TODO Validate the schema of the recovered file matches what the system expects:
# class AgentSummaryOutput(BaseModel):
#     input_file: str
#     budget: Optional[str]
#     key_needs: List[str]
#     summary: str
#     output_file: str
#     created_at: str

def validate_schema(obj: Dict[str, Any]) -> List[str]:
    issues: List[str] = []

    for field in REQUIRED_TOP_LEVEL_FIELDS:
        if field not in obj:
            issues.append(f"Missing required field: {field}")

    if "key_needs" in obj and not isinstance(obj["key_needs"], list):
        issues.append("Field key_needs must be a list.")

    if "created_at" in obj:
        # Not strict ISO validation; just sanity check that it looks like a timestamp string.
        if not isinstance(obj["created_at"], str) or len(obj["created_at"]) < 10:
            issues.append("Field created_at must be a timestamp string.")

    return issues


def validate_paths(obj: Dict[str, Any], expected_output_path: str) -> List[str]:
    issues: List[str] = []

    # output_file should match where we actually wrote
    out_file = obj.get("output_file")
    if isinstance(out_file, str):
        out_norm = out_file.replace("\\", "/")
        exp_norm = expected_output_path.replace("\\", "/")
        if not (out_norm == exp_norm or out_norm.endswith(exp_norm)):
            issues.append(f"output_file does not match expected path. output_file={out_file}")
    else:
        issues.append("output_file must be a string.")

    return issues


def validate_recovery_logged(
    action_events: List[Dict[str, Any]],
    output_path: str,
    snapshot_path: str,
    quarantine_dir: Optional[str],
) -> List[str]:
    issues: List[str] = []

    # Find most recent recovery_performed event for this output_path
    output_norm = output_path.replace("\\", "/")
    candidates = [
        e for e in action_events
        if e.get("event_type") == "recovery_performed"
        and str(e.get("output_path", "")).replace("\\", "/").endswith(output_norm)
    ]

    if not candidates:
        #TODO: Append an item to issues if no rollback event found in the log
        return issues

    candidates.sort(key=lambda e: str(e.get("ts", "")), reverse=True)
    evt = candidates[0]

    # Snapshot consistency (best-effort)
    logged_snapshot = str(evt.get("snapshot_path", ""))
    if snapshot_path and logged_snapshot and os.path.basename(snapshot_path) != os.path.basename(logged_snapshot):
        issues.append(
            "Most recent recovery_performed event used a different snapshot "
            f"(logged={os.path.basename(logged_snapshot)} expected={os.path.basename(snapshot_path)})."
        )

    # Quarantine artifact should exist if a quarantine_dir is provided
    quarantined_path = evt.get("quarantined_path")
    if quarantine_dir:
        if not quarantined_path:
            issues.append("Recovery event missing quarantined_path.")
        else:
            qp = str(quarantined_path)
            if not os.path.exists(qp):
                # If log stores a relative path, try joining
                joined = os.path.join(quarantine_dir, os.path.basename(qp))
                if not os.path.exists(joined):
                    issues.append(f"Quarantined file not found: {qp}")

    return issues


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
@dataclass
class ValidationResult:
    ok: bool
    checks: Dict[str, Any]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, help="Path to the recovered output JSON (shopping_summary.json)")
    parser.add_argument("--snapshot", required=True, help="Snapshot directory containing known-good snapshots")
    parser.add_argument("--action-log", required=True, help="Action log JSONL (from recovery)")
    parser.add_argument("--quarantine", required=False, default=None, help="Quarantine directory (optional)")
    parser.add_argument("--baseline", required=False, default=None, help="Optional explicit baseline snapshot file")
    args = parser.parse_args()

    output_path = args.output
    output_filename = os.path.basename(output_path)

    # Pick baseline snapshot
    baseline_path = args.baseline
    if not baseline_path:
        baseline_path = most_recent_snapshot(args.snapshot, output_filename)

    checks: Dict[str, Any] = {}

    if not os.path.exists(output_path):
        print("FAIL: output file does not exist:", output_path)
        raise SystemExit(2)

    if not baseline_path or not os.path.exists(baseline_path):
        print("FAIL: baseline snapshot not found. Provide --baseline or ensure snapshots exist in:", args.snapshot)
        raise SystemExit(2)

    # Load current + baseline
    current_obj = load_json(output_path)
    baseline_obj = load_json(baseline_path)

    # Schema/integrity checks
    schema_issues = validate_schema(current_obj)
    checks["schema"] = {"ok": len(schema_issues) == 0, "issues": schema_issues}

    path_issues = validate_paths(current_obj, output_path)
    checks["paths"] = {"ok": len(path_issues) == 0, "issues": path_issues}

    # Compare a small set of fields to confirm we’re back to known-good content
    compare_fields = ["summary", "key_needs", "budget", "input_file", "output_file"]
    diffs: List[str] = []
    for f in compare_fields:
        if current_obj.get(f) != baseline_obj.get(f):
            diffs.append(f"Field differs from baseline: {f}")
    checks["baseline_parity"] = {"ok": len(diffs) == 0, "differences": diffs, "baseline": baseline_path}

    # Confirm recovery was logged
    action_events = iter_jsonl(args.action_log)
    log_issues = validate_recovery_logged(
        action_events=action_events,
        output_path=output_path,
        snapshot_path=baseline_path,
        quarantine_dir=args.quarantine,
    )
    checks["recovery_log"] = {"ok": len(log_issues) == 0, "issues": log_issues}

    # Overall decision
    overall_ok = all(v.get("ok") is True for v in checks.values())

    print("\n=== Recovery Validation Report ===")
    print(f"Output:   {output_path}")
    print(f"Baseline: {baseline_path}")
    print(f"Action log: {args.action_log}")
    if args.quarantine:
        print(f"Quarantine: {args.quarantine}")
    print("---------------------------------\n")

    for name, result in checks.items():
        status = "PASS" if result.get("ok") else "FAIL"
        print(f"{status}: {name}")
        if not result.get("ok"):
            # print relevant details
            if "issues" in result and result["issues"]:
                for issue in result["issues"]:
                    print(f"  - {issue}")
            if "differences" in result and result["differences"]:
                for d in result["differences"]:
                    print(f"  - {d}")
            if "findings" in result and result["findings"]:
                for fnd in result["findings"]:
                    t = fnd.get("type")
                    val = fnd.get("value", "")
                    match = fnd.get("match", "")
                    print(f"  - finding: {t} value={val} match={match}")
        print("")

    print("=== Overall ===")
    print("READY" if overall_ok else "NOT READY")
    if not overall_ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
