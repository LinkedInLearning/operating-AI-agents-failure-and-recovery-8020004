"""
Course 2 — Lesson 2: Detect and Attribute Agent Failures

Goal:
- Scan the agent output for sensitive info
- If found, attribute the write to a specific agent + tool call + timestamp using JSONL logs

Usage:
  python scanner.py --output 00_03_e/out/shopping_summary.json --log 00_03_e/logs/agent_events.jsonl

Note:
If your --output path differs from the path recorded in the log (different lesson folder),
this script will still attribute using a fallback: matching by filename (basename).
"""

import argparse
import json
import os
import re
from typing import Any, Dict, List, Optional


# Simple, practical email detector
EMAIL_RE = re.compile(
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    re.IGNORECASE,
)

# Examples it catches:
# - "ending in 4821"
# - "last 4: 4821"
# - "****4821"
# - "card ending 4821"
CARD_LAST4_RE = re.compile(
    r"""
    (?:ending\s+in|ending|last\s*4|last\s*four|card\s+ending|\*{2,})
    [^\d]{0,8}
    (?P<last4>\d{4})
    """,
    re.IGNORECASE | re.VERBOSE,
)


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def flatten_text(obj: Any) -> str:
    """
    Turn a nested JSON object into a single string we can scan.
    This keeps the scanner simple and tolerant of schema changes.
    """
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
    """
    Return findings with a consistent shape:
      - type: "card_last4" | "email"
      - match: matched text
      - value: extracted value (last4 or email)
    """
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


def _norm_path(p: str) -> str:
    return str(p).replace("\\", "/").strip()


def _same_basename(a: str, b: str) -> bool:
    return os.path.basename(a) == os.path.basename(b)


def attribute_writer(events: List[Dict[str, Any]], output_path: str) -> Optional[Dict[str, Any]]:
    """
    Attribute by finding the tool_completed event for write_local_json that wrote output_path.
    Matching strategy (in order):
      1) exact normalized match
      2) suffix match (endswith)
      3) basename match (filename only) as a last resort

    Then:
      - capture op_id for the write
      - walk backwards in the same run_id to find agent_run_started
      - find the corresponding tool_invoked for the same op_id (preferred) or nearest prior invoke
    """
    target_norm = _norm_path(output_path)
    target_base = os.path.basename(target_norm)

    # 1) Find the most recent write completion that matches this output.
    write_evt_idx: Optional[int] = None
    match_mode: Optional[str] = None

    for i in range(len(events) - 1, -1, -1):
        evt = events[i]
        if evt.get("event_type") != "tool_completed":
            continue
        if evt.get("tool_name") != "write_local_json":
            continue

        outp = evt.get("output_path") or evt.get("tool_args", {}).get("path")
        if not outp:
            continue

        outp_norm = _norm_path(outp)

        if outp_norm == target_norm:
            write_evt_idx = i
            match_mode = "exact_path"
            break

        if outp_norm.endswith(target_norm) or target_norm.endswith(outp_norm):
            write_evt_idx = i
            match_mode = "suffix_path"
            break

        if os.path.basename(outp_norm) == target_base:
            write_evt_idx = i
            match_mode = "basename"
            break

    if write_evt_idx is None:
        return None

    write_evt = events[write_evt_idx]
    run_id = write_evt.get("run_id")
    op_id = write_evt.get("op_id")
    tool_completed_ts = write_evt.get("ts")
    output_path_in_log = write_evt.get("output_path") or write_evt.get("tool_args", {}).get("path")

    # 2) Walk backwards in the same run to find which agent run this belongs to.
    agent_name: Optional[str] = None
    agent_run_started_ts: Optional[str] = None

    for j in range(write_evt_idx, -1, -1):
        evt = events[j]
        if run_id and evt.get("run_id") != run_id:
            continue
        if evt.get("event_type") == "agent_run_started" and evt.get("agent_name"):
            agent_name = evt.get("agent_name")
            agent_run_started_ts = evt.get("ts")
            break

    # 3) Find the tool_invoked event that corresponds to this write.
    # Prefer matching by op_id if available, otherwise fall back to nearest prior invoke in the same run.
    tool_invoked_ts: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None
    invoked_op_id: Optional[str] = None

    for j in range(write_evt_idx, -1, -1):
        evt = events[j]
        if run_id and evt.get("run_id") != run_id:
            continue
        if evt.get("event_type") != "tool_invoked":
            continue
        if evt.get("tool_name") != "write_local_json":
            continue

        if op_id and evt.get("op_id") == op_id:
            tool_invoked_ts = evt.get("ts")
            tool_args = evt.get("tool_args")
            invoked_op_id = evt.get("op_id")
            break

        # If we don't have an op_id on the completed event, take the nearest invoked.
        if not op_id and tool_invoked_ts is None:
            tool_invoked_ts = evt.get("ts")
            tool_args = evt.get("tool_args")
            invoked_op_id = evt.get("op_id")
            break

    return {
        "match_mode": match_mode,
        "target_output_arg": output_path,
        "output_path_in_log": output_path_in_log,
        "run_id": run_id,
        "agent_name": agent_name,
        "agent_run_started_ts": agent_run_started_ts,
        "tool_name": "write_local_json",
        "op_id": op_id or invoked_op_id,
        "tool_invoked_ts": tool_invoked_ts,
        "tool_completed_ts": tool_completed_ts,
        "tool_args": tool_args,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, help="Path to shopping_summary.json")
    parser.add_argument("--log", required=True, help="Path to agent_events.jsonl")
    args = parser.parse_args()

    output_obj = load_json(args.output)
    text = flatten_text(output_obj)
    findings = scan_for_sensitive(text)

    print("\n=== Scan Results ===")
    if not findings:
        print("No sensitive patterns found.")
        return

    print(f"Found {len(findings)} potential issue(s):")
    for fnd in findings:
        if fnd["type"] == "card_last4":
            print(f"- {fnd['type']}: {fnd['match']} (last4={fnd['value']})")
        elif fnd["type"] == "email":
            print(f"- {fnd['type']}: {fnd['match']}")
        else:
            print(f"- {fnd['type']}: {fnd.get('match','')}")

    events = iter_jsonl(args.log)
    attribution = attribute_writer(events, args.output)

    print("\n=== Attribution ===")
    if not attribution:
        print("Found sensitive content, but could not attribute the write in the log.")
        print("Confirm your --log is the log file produced by the same run that wrote the output.")
        return

    print(json.dumps(attribution, indent=2))


if __name__ == "__main__":
    main()
