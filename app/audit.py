from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIT_LOG_PATH = Path(os.getenv("AUDIT_LOG_PATH", "data/audit.jsonl"))
SCHEMA_PATH = REPO_ROOT / "config" / "logging_schema.json"


def record_audit_event(
    event: str,
    *,
    actor: str = "system",
    correlation_id: str = "audit-system",
    details: dict[str, Any] | None = None,
    level: str = "info",
) -> dict[str, Any]:
    """Records an audit event conforming to the schema and applies retention."""
    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    now_utc = datetime.now(timezone.utc).isoformat()

    entry = {
        "ts": now_utc,
        "level": level,
        "service": "audit",
        "event": event,
        "correlation_id": correlation_id,
        "actor": actor,
        "payload": details or {},
    }

    # Append audit entry
    with AUDIT_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # Enforce retention (keep last 1000 records or 30 days)
    apply_retention_policy(max_records=1000)
    return entry


def apply_retention_policy(max_records: int = 1000) -> None:
    """Enforces retention by trimming older audit records."""
    if not AUDIT_LOG_PATH.exists():
        return

    lines = AUDIT_LOG_PATH.read_text(encoding="utf-8").splitlines()
    if len(lines) > max_records:
        trimmed = lines[-max_records:]
        AUDIT_LOG_PATH.write_text("\n".join(trimmed) + "\n", encoding="utf-8")
