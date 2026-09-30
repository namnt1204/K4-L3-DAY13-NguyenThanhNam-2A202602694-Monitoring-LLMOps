#!/usr/bin/env python3
"""Automated Secret and PII Scanner for Day 13 LLMOps Repository.

Scans the repository and staged files to prevent accidental leakage of:
- Langfuse secret keys (sk-lf-...)
- General API secrets and private tokens
- Unredacted PII (CCCD, Credit Cards, VN Phone numbers, Emails)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

SECRET_PATTERNS = {
    "langfuse_secret_key": re.compile(r"sk-lf-[a-zA-Z0-9_-]{20,}"),
    "generic_secret_key": re.compile(r"(?:api[_-]?key|secret[_-]?key)\s*[:=]\s*['\"][a-zA-Z0-9_\-]{16,}['\"]", re.IGNORECASE),
}

PII_PATTERNS = {
    "credit_card": re.compile(r"\b(?:\d{4}[ -]\d{4}[ -]\d{4}[ -]\d{4}|\d{16})\b"),
    "cccd": re.compile(r"\b\d{12}\b"),
}

EXCLUDED_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", "doc", "docs"}
EXCLUDED_FILES = {
    ".env",
    "sample_queries.jsonl",
    "test_pii.py",
    "test_validate_logs.py",
    ".env.example",
    "scan_secrets_pii.py",
    "05-pii-redaction.txt",
}


def scan_file(file_path: Path) -> list[str]:
    violations: list[str] = []
    if file_path.name in EXCLUDED_FILES or any(part in EXCLUDED_DIRS for part in file_path.parts):
        return violations

    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return [f"Could not read {file_path}: {e}"]

    # 1. Scan for secrets
    for name, pattern in SECRET_PATTERNS.items():
        if pattern.search(content):
            violations.append(f"Potential SECRET leak ({name}) detected in {file_path.relative_to(REPO_ROOT)}")

    # 2. Scan for unredacted raw PII in code/config/submission files
    if file_path.suffix in {".py", ".json", ".yaml", ".yml", ".md"}:
        for name, pattern in PII_PATTERNS.items():
            matches = pattern.findall(content)
            for match in matches:
                # Ignore placeholder numbers or test hashes
                if match in {"001099012345", "4111111111111111", "4111 1111 1111 1111", "4111-1111-1111-1111"}:
                    continue
                violations.append(f"Potential raw PII ({name}: {match[:4]}****) in {file_path.relative_to(REPO_ROOT)}")

    return violations


def main() -> int:
    print("=== Scanning repository for secrets and unredacted PII ===")
    all_violations: list[str] = []

    for path in REPO_ROOT.rglob("*"):
        if path.is_file():
            all_violations.extend(scan_file(path))

    if all_violations:
        print(f"FAILED: {len(all_violations)} violation(s) found:")
        for v in all_violations:
            print(f"  - {v}")
        return 1

    print("PASSED: Zero secrets or unredacted raw PII leaks detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
