"""Safely provision Beta-v2 session and audit secrets in the local .env.

Secret values are generated locally, written atomically, and never printed.
The command is idempotent and refuses to replace invalid keys after a non-empty
audit chain exists because doing so would make that chain unverifiable.
"""

from __future__ import annotations

import argparse
import os
import re
import secrets
import stat
import tempfile
from pathlib import Path


BACKEND_PATH = Path(__file__).resolve().parents[1]
DEFAULT_ENV_PATH = BACKEND_PATH / ".env"
DEFAULT_AUDIT_PATH = BACKEND_PATH / "runtime" / "security_audit.jsonl"
MANAGED_KEYS = frozenset(
    {"AUTH_SESSION_SECRET", "AUDIT_HMAC_KEY", "AUTH_COOKIE_SECURE"}
)
ASSIGNMENT_PATTERN = re.compile(
    r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*="
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Provision distinct local Beta-v2 authentication and audit secrets"
    )
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_PATH)
    parser.add_argument("--audit-log", type=Path, default=DEFAULT_AUDIT_PATH)
    return parser


def _assignment(line: str) -> tuple[str, str] | None:
    match = ASSIGNMENT_PATTERN.match(line)
    if match is None:
        return None
    key = match.group(1)
    value = line.split("=", 1)[1].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return key, value


def _effective_values(lines: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in lines:
        assignment = _assignment(line)
        if assignment is not None and assignment[0] in MANAGED_KEYS:
            values[assignment[0]] = assignment[1]
    return values


def _valid_secret(value: str) -> bool:
    return len(value.encode("utf-8")) >= 32 and not value.casefold().startswith("your-")


def _write_atomic(path: Path, content: str, *, existing_mode: int | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_name = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(
            temporary_name,
            existing_mode if existing_mode is not None else stat.S_IRUSR | stat.S_IWUSR,
        )
        os.replace(temporary_name, path)
        temporary_name = None
    finally:
        if temporary_name is not None:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass


def configure(env_path: Path, audit_path: Path) -> bool:
    """Provision missing keys and return whether the environment file changed."""

    try:
        existing_text = env_path.read_text(encoding="utf-8-sig")
        existing_mode = stat.S_IMODE(env_path.stat().st_mode)
    except FileNotFoundError:
        existing_text = ""
        existing_mode = None
    lines = existing_text.splitlines()
    values = _effective_values(lines)
    session_secret = values.get("AUTH_SESSION_SECRET", "")
    audit_secret = values.get("AUDIT_HMAC_KEY", "")
    if (
        _valid_secret(session_secret)
        and _valid_secret(audit_secret)
        and not secrets.compare_digest(session_secret, audit_secret)
    ):
        return False

    if audit_path.is_file() and audit_path.stat().st_size > 0:
        raise RuntimeError(
            "refusing to replace security keys while a non-empty audit chain exists"
        )

    retained = []
    for line in lines:
        assignment = _assignment(line)
        if assignment is None or assignment[0] not in MANAGED_KEYS:
            retained.append(line)
    while retained and not retained[0].strip():
        retained.pop(0)

    new_session_secret = secrets.token_urlsafe(48)
    new_audit_secret = secrets.token_urlsafe(48)
    managed_block = [
        "# SOC AUTHENTICATION AND TAMPER-EVIDENT AUDIT (locally generated)",
        f"AUTH_SESSION_SECRET={new_session_secret}",
        f"AUDIT_HMAC_KEY={new_audit_secret}",
        "AUTH_COOKIE_SECURE=false",
        "",
    ]
    content = "\n".join(managed_block + retained).rstrip() + "\n"
    _write_atomic(env_path, content, existing_mode=existing_mode)
    return True


def main() -> int:
    args = _parser().parse_args()
    try:
        changed = configure(args.env_file, args.audit_log)
    except (OSError, UnicodeError, RuntimeError) as exc:
        print(f"Security configuration failed: {exc}")
        return 2
    if changed:
        print("Configured distinct local authentication and audit secrets.")
    else:
        print("Authentication and audit secrets are already valid; no change made.")
    print(f"Environment file: {args.env_file.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
