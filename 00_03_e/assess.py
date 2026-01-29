"""
Course 2 — Lesson 3: Assess Failure Impact

Goal:
- Measure blast radius by comparing the latest snapshot of system state (JSON)
  to the current output JSON.
- Produce a small, human-readable impact summary + a structured diff report.

Prereqs:
  pip install deepdiff
  python assess_failure_impact.py --snapshots 00_03_e/snapshots --current 00_03_e/out/shopping_summary.json

Notes:
- This script assumes your snapshots folder contains JSON snapshots of the SAME file
  you’re comparing (for example: shopping_summary.snapshot.<ts>.json).
- It will pick the most recent JSON file in the snapshots directory.
"""

import argparse
import json
import os
from typing import Any, Dict, Optional, Tuple

from deepdiff import DeepDiff


# -----------------------------
# File helpers
# -----------------------------
def load_json(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Missing file: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_latest_snapshot(snapshots_dir: str) -> str:
    if not os.path.isdir(snapshots_dir):
        raise FileNotFoundError(f"Snapshot directory not found: {snapshots_dir}")

    candidates = []
    for name in os.listdir(snapshots_dir):
        if name.lower().endswith(".json"):
            full = os.path.join(snapshots_dir, name)
            if os.path.isfile(full):
                candidates.append(full)

    if not candidates:
        raise FileNotFoundError(f"No .json snapshots found in: {snapshots_dir}")

    candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return candidates[0]


# -----------------------------
# Impact summary
# -----------------------------
def summarize_deepdiff(dd: DeepDiff) -> Dict[str, int]:
    """
    DeepDiff returns a dict-like object keyed by change type.
    We reduce that into counts per change type for a "blast radius" summary.
    """
    summary: Dict[str, int] = {}
    for change_type, changes in dd.items():
        # changes can be dict, list, set-like depending on type
        try:
            summary[change_type] = len(changes)
        except TypeError:
            # fallback if something isn't sized
            summary[change_type] = 1
    return summary


def print_top_changes(dd: DeepDiff, max_items: int = 8) -> None:
    """
    Show a small sample of changed paths so learners can see "what moved"
    without dumping pages of output.
    """
    printed = 0

    # value changes (old/new)
    vc = dd.get("values_changed", {}) or {}
    for path, info in vc.items():
        if printed >= max_items:
            return
        old_v = info.get("old_value")
        new_v = info.get("new_value")
        print(f"- values_changed: {path}: {repr(old_v)} -> {repr(new_v)}")
        printed += 1

    # added keys
    added = dd.get("dictionary_item_added", set()) or set()
    for path in list(added)[: max(0, max_items - printed)]:
        if printed >= max_items:
            return
        print(f"- dictionary_item_added: {path}")
        printed += 1

    # removed keys
    removed = dd.get("dictionary_item_removed", set()) or set()
    for path in list(removed)[: max(0, max_items - printed)]:
        if printed >= max_items:
            return
        print(f"- dictionary_item_removed: {path}")
        printed += 1

    # iterable additions/removals
    it_added = dd.get("iterable_item_added", {}) or {}
    for path, val in list(it_added.items())[: max(0, max_items - printed)]:
        if printed >= max_items:
            return
        print(f"- iterable_item_added: {path}: {repr(val)}")
        printed += 1

    it_removed = dd.get("iterable_item_removed", {}) or {}
    for path, val in list(it_removed.items())[: max(0, max_items - printed)]:
        if printed >= max_items:
            return
        print(f"- iterable_item_removed: {path}: {repr(val)}")
        printed += 1


def write_report(path: str, report: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)


# -----------------------------
# Main
# -----------------------------
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshots", required=True, help="Directory containing JSON snapshots")
    parser.add_argument("--current", required=True, help="Current output JSON path (e.g., shopping_summary.json)")
    parser.add_argument(
        "--report",
        default="cs-lesson3-access-failure-impact/impact/impact_report.json",
        help="Where to write the impact report JSON (default: impact_report.json in CWD)",
    )
    parser.add_argument(
        "--ignore-order",
        action="store_true",
        help="Ignore list ordering (reduces noise when lists reorder).",
    )
    args = parser.parse_args()

    snapshot_path = find_latest_snapshot(args.snapshots)
    before_obj = load_json(snapshot_path)
    after_obj = load_json(args.current)

    dd = DeepDiff(before_obj, after_obj, ignore_order=bool(args.ignore_order))
    impact = summarize_deepdiff(dd)

    print("\n=== Failure Impact (Blast Radius) ===")
    print(f"Snapshot used: {snapshot_path}")
    print(f"Current output: {args.current}")

    if not dd:
        print("\nNo differences detected. Blast radius is 0.")
        report = {
            "snapshot_path": snapshot_path,
            "current_path": args.current,
            "impact_summary": {},
            "diff": {},
        }
        write_report(args.report, report)
        print(f"\nWrote report: {args.report}")
        return

    print("\nImpact summary (counts by change type):")
    for k in sorted(impact.keys()):
        print(f"- {k}: {impact[k]}")

    print("\nSample of changes (top items):")
    print_top_changes(dd, max_items=10)

    report = {
        "snapshot_path": snapshot_path,
        "current_path": args.current,
        "impact_summary": impact,
        # DeepDiff is JSON-serializable when converted to dict
        "diff": dd.to_dict() if hasattr(dd, "to_dict") else dict(dd),
    }
    write_report(args.report, report)
    print(f"\nWrote report: {args.report}")
    print("====================================\n")


if __name__ == "__main__":
    main()
