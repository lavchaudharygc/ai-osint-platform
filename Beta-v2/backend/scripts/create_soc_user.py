"""Provision or replace a PBKDF2-hashed Beta-v2 SOC operator.

Passwords are read interactively so they do not appear in shell history or the
process list. Run this script from the Beta-v2 backend virtual environment.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any


BACKEND_PATH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_PATH))

from app.config import settings  # noqa: E402
from app.security.auth import (  # noqa: E402
    ALLOWED_ROLES,
    create_password_record,
    normalize_username,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create or replace a local SOC operator")
    parser.add_argument("--username", required=True, help="ASCII operator login name")
    parser.add_argument(
        "--role",
        action="append",
        dest="roles",
        choices=sorted(ALLOWED_ROLES),
        required=True,
        help="Assign a role; repeat to assign both roles",
    )
    parser.add_argument(
        "--users-file",
        type=Path,
        default=settings.auth_users_file,
        help="User store path (defaults to AUTH_USERS_FILE)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=settings.auth_pbkdf2_iterations,
        help="PBKDF2-HMAC-SHA256 iteration count",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace an existing user with this username",
    )
    return parser


def _load_document(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "users": []}
    if path.is_symlink() or not path.is_file():
        raise ValueError("users file must be a regular file, not a symbolic link")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("existing users file is unreadable or malformed") from exc
    if not isinstance(document, dict) or document.get("version") != 1:
        raise ValueError("existing users file has an unsupported version")
    if not isinstance(document.get("users"), list):
        raise ValueError("existing users file has an invalid users list")
    return document


def _atomic_write(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("refusing to replace a symbolic-link users file")
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
            json.dump(document, handle, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_name, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(temporary_name, path)
        temporary_name = None
    finally:
        if temporary_name is not None:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass


def main() -> int:
    args = _parser().parse_args()
    try:
        username = normalize_username(args.username)
        if args.iterations < 100_000:
            raise ValueError("iterations must be at least 100000")
        document = _load_document(args.users_file)
        matching = [
            index
            for index, record in enumerate(document["users"])
            if isinstance(record, dict)
            and isinstance(record.get("username"), str)
            and record["username"].strip().casefold() == username
        ]
        if matching and not args.replace:
            raise ValueError("user already exists; pass --replace to rotate its password or roles")
        password = getpass.getpass("New password (minimum 12 characters): ")
        confirmation = getpass.getpass("Confirm password: ")
        if not password or password != confirmation:
            raise ValueError("passwords did not match")
        record = {
            "username": username,
            "active": True,
            "roles": sorted(set(args.roles)),
            "password": create_password_record(password, iterations=args.iterations),
        }
        if matching:
            document["users"][matching[0]] = record
        else:
            document["users"].append(record)
        document["users"].sort(key=lambda item: str(item.get("username", "")))
        _atomic_write(args.users_file, document)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    print(f"Provisioned SOC user '{username}' with roles: {', '.join(record['roles'])}")
    print(f"User store: {args.users_file.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
