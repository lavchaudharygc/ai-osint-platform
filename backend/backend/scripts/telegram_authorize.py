"""Create the local Telethon session used by read-only Telegram lookup."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from backend.core.config import settings


def main() -> int:
    if not settings.telegram_api_id or not settings.telegram_api_hash:
        print("Set TELEGRAM_API_ID and TELEGRAM_API_HASH in backend/.env first.")
        return 1

    try:
        from telethon.sync import TelegramClient
    except ImportError:
        print("Telethon is not installed. Run: pip install -r requirements.txt")
        return 1

    session_path = Path(settings.telegram_session_path).expanduser()
    session_path.parent.mkdir(parents=True, exist_ok=True)

    print("Telegram will request your phone, one-time login code, and 2FA password if enabled.")
    print("The resulting .session file grants account access. Never share or commit it.")
    client = TelegramClient(
        str(session_path),
        settings.telegram_api_id,
        settings.telegram_api_hash,
        receive_updates=False,
    )
    try:
        client.start()
        account = client.get_me()
        username = getattr(account, "username", None) or "no public username"
        print(f"Authorization complete for account ID {account.id} ({username}).")
    finally:
        client.disconnect()

    session_file = session_path if session_path.suffix == ".session" else Path(f"{session_path}.session")
    if session_file.exists():
        try:
            os.chmod(session_file, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
    print("Restart the backend after setting TELEGRAM_MTPROTO_ENABLED=true.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
