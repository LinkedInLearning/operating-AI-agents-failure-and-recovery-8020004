import os
import shutil
from datetime import datetime, timezone

def utc_ts_slug() -> str:
    # Safe filename timestamp
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def snapshot_file(
    src_path: str,
    snapshots_dir: str,
    label: str,
    run_id: str,
) -> str:
    """
    Copy src_path to snapshots_dir if src_path exists.
    Returns the snapshot path, or an empty string if there was nothing to snapshot.
    """
    ensure_dir(snapshots_dir)

    if not os.path.exists(src_path):
        return ""

    ts = utc_ts_slug()
    base = os.path.basename(src_path)
    snap_name = f"{base}.{label}.{ts}.{run_id}.json"
    snap_path = os.path.join(snapshots_dir, snap_name)

    shutil.copy2(src_path, snap_path)
    return snap_path


def quarantine_file(
    src_path: str,
    quarantine_dir: str,
    reason: str,
    run_id: str,
) -> str:
    """
    Move the unsafe artifact into quarantine for audit.
    Returns the quarantine path, or an empty string if file did not exist.
    """
    ensure_dir(quarantine_dir)

    if not os.path.exists(src_path):
        return ""

    ts = utc_ts_slug()
    base = os.path.basename(src_path)
    q_name = f"{base}.quarantine.{reason}.{ts}.{run_id}.json"
    q_path = os.path.join(quarantine_dir, q_name)

    shutil.move(src_path, q_path)
    return q_path


def restore_snapshot(snapshot_path: str, dest_path: str) -> None:
    """
    Restore dest_path from a known-good snapshot.
    Raises if snapshot doesn't exist.
    """
    if not snapshot_path or not os.path.exists(snapshot_path):
        raise FileNotFoundError(f"Snapshot not found: {snapshot_path}")

    ensure_dir(os.path.dirname(dest_path) or ".")
    shutil.copy2(snapshot_path, dest_path)
