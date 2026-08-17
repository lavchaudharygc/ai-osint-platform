"""Verify the configured Beta-v2 tamper-evident security audit chain."""

from __future__ import annotations

import sys
from pathlib import Path


BACKEND_PATH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_PATH))

from app.security.audit import AuditUnavailable, get_audit_logger  # noqa: E402


def main() -> int:
    """Verify every chained audit record without modifying the audit file."""

    try:
        record_count = get_audit_logger().verify_integrity()
    except AuditUnavailable as exc:
        print(f"Audit verification failed: {exc}", file=sys.stderr)
        return 2
    print(f"Audit chain verified: {record_count} record(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
