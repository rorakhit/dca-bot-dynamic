"""
audit.py — Audit log read/write for tracking all bot activity.
"""

import json
from datetime import datetime, timezone

from config import AUDIT_LOG_PATH, log


def write_audit_entry(event: str, data: dict):
    """Append a JSON-lines entry to the audit log."""
    entry = {"timestamp": datetime.now(timezone.utc).isoformat(), "event": event, **data}
    with open(AUDIT_LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


def read_audit_log() -> list[dict]:
    """Read all audit entries, return newest first."""
    if not AUDIT_LOG_PATH.exists():
        return []
    entries = []
    for line in AUDIT_LOG_PATH.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return list(reversed(entries))


def get_audit_history_summary(max_entries: int = 10) -> list[dict]:
    """
    Return the most recent portfolio snapshots and AI allocation entries
    for AI context. Helps Claude see recent trends and past decisions.
    """
    if not AUDIT_LOG_PATH.exists():
        return []

    entries = []
    for line in AUDIT_LOG_PATH.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                entry = json.loads(line)
                if entry.get("event") in (
                    "portfolio_snapshot",
                    "dynamic_allocation_proposed",
                    "orders_placed",
                ):
                    entries.append(entry)
            except json.JSONDecodeError:
                pass

    # Return most recent entries (newest first)
    return list(reversed(entries))[:max_entries]
