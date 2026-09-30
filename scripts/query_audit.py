#!/usr/bin/env python3
"""Query tool for audit logs in data/audit.jsonl."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIT_LOG_PATH = REPO_ROOT / "data" / "audit.jsonl"


def query_audit_logs(
    *,
    event: str | None = None,
    actor: str | None = None,
    level: str | None = None,
    limit: int = 50,
) -> list[dict]:
    if not AUDIT_LOG_PATH.exists():
        print(f"No audit log file found at {AUDIT_LOG_PATH}")
        return []

    results = []
    for line in AUDIT_LOG_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue

        if event and record.get("event") != event:
            continue
        if actor and record.get("actor") != actor:
            continue
        if level and record.get("level") != level:
            continue

        results.append(record)

    return results[-limit:]


def main() -> None:
    parser = argparse.ArgumentParser(description="Query structured audit logs")
    parser.add_argument("--event", help="Filter by event name (e.g. incident_enabled, prompt_promoted)")
    parser.add_argument("--actor", help="Filter by actor (e.g. admin, user)")
    parser.add_argument("--level", help="Filter by level (info, warning, error)")
    parser.add_argument("--limit", type=int, default=20, help="Maximum records to display")
    args = parser.parse_args()

    records = query_audit_logs(event=args.event, actor=args.actor, level=args.level, limit=args.limit)
    print(f"Found {len(records)} audit record(s):")
    for r in records:
        print(f"[{r.get('ts')}] [{r.get('level').upper()}] {r.get('event')} by {r.get('actor')} | details={r.get('payload')}")


if __name__ == "__main__":
    main()
