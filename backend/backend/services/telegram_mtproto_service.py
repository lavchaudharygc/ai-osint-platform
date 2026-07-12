"""Read-only Telegram MTProto lookup using an existing authorized session."""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from backend.core.config import settings

try:
    from telethon import TelegramClient, functions

    TELETHON_AVAILABLE = True
except ImportError:  # The public scraper must keep working before optional setup.
    TelegramClient = None  # type: ignore[assignment]
    functions = None  # type: ignore[assignment]
    TELETHON_AVAILABLE = False


_SESSION_LOCK = asyncio.Lock()


class TelegramMTProtoService:
    """Resolve accessible Telegram entities without joining or reading messages."""

    INVITE_PATH_PATTERN = re.compile(r"^(?:joinchat/|\+)([A-Za-z0-9_-]+)$", re.IGNORECASE)

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        api_id: int | None = None,
        api_hash: str | None = None,
        session_path: str | None = None,
        timeout: float | None = None,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.enabled = settings.telegram_mtproto_enabled if enabled is None else enabled
        self.api_id = settings.telegram_api_id if api_id is None else api_id
        self.api_hash = settings.telegram_api_hash if api_hash is None else api_hash
        self.session_path = session_path or settings.telegram_session_path
        self.timeout = timeout or settings.telegram_mtproto_timeout_seconds
        self.dependency_available = TELETHON_AVAILABLE or client_factory is not None
        self.client_factory = client_factory or TelegramClient

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "dependency_available": self.dependency_available,
            "credentials_configured": bool(self.api_id and self.api_hash),
            "session_file_present": self._session_file().is_file(),
            "access_mode": "authorized_user_session_read_only",
            "auto_join": False,
            "message_history": False,
            "phone_and_contacts": False,
        }

    async def lookup(self, target: str) -> dict[str, Any]:
        scraped_at = datetime.now(UTC).isoformat()
        invite_hash = self.extract_invite_hash(target)
        normalized_username = self.normalize_username(target) if invite_hash is None else None
        target_type = "invite_link" if invite_hash else "username"

        unavailable = self._configuration_error(target_type, scraped_at)
        if unavailable:
            return unavailable
        if invite_hash is None and normalized_username is None:
            return self._response(
                success=False,
                exists=False,
                status="invalid_target",
                target_type=target_type,
                scraped_at=scraped_at,
                error="Provide a Telegram username or a t.me/+... / t.me/joinchat/... invite link.",
            )

        async with _SESSION_LOCK:
            try:
                return await asyncio.wait_for(
                    self._lookup_with_session(
                        username=normalized_username,
                        invite_hash=invite_hash,
                        scraped_at=scraped_at,
                    ),
                    timeout=self.timeout,
                )
            except TimeoutError:
                return self._response(
                    success=False,
                    exists=None,
                    status="authorized_lookup_timeout",
                    target_type=target_type,
                    scraped_at=scraped_at,
                    error="Authorized Telegram lookup timed out.",
                )

    async def _lookup_with_session(
        self,
        *,
        username: str | None,
        invite_hash: str | None,
        scraped_at: str,
    ) -> dict[str, Any]:
        client = self.client_factory(
            self.session_path,
            self.api_id,
            self.api_hash,
            receive_updates=False,
            auto_reconnect=False,
            connection_retries=1,
            request_retries=1,
            flood_sleep_threshold=0,
        )
        if hasattr(client, "session"):
            client.session.save_entities = False

        try:
            await client.connect()
            if not await client.is_user_authorized():
                return self._response(
                    success=False,
                    exists=None,
                    status="authorized_session_required",
                    target_type="invite_link" if invite_hash else "username",
                    scraped_at=scraped_at,
                    error="Run the local Telegram authorization command before using MTProto lookup.",
                )
            if invite_hash:
                return await self._check_invite(client, invite_hash, scraped_at)
            return await self._resolve_username(client, str(username), scraped_at)
        except Exception as exc:
            return self._handle_telegram_error(
                exc,
                target_type="invite_link" if invite_hash else "username",
                username=username,
                scraped_at=scraped_at,
            )
        finally:
            if client.is_connected():
                await client.disconnect()

    async def _resolve_username(self, client: Any, username: str, scraped_at: str) -> dict[str, Any]:
        entity = await client.get_entity(username)
        full_info = None
        entity_kind = self._entity_kind(entity)
        try:
            if entity_kind == "user":
                full_result = await client(functions.users.GetFullUserRequest(entity))
                full_info = getattr(full_result, "full_user", None)
            elif entity_kind in {"channel", "group"} and entity.__class__.__name__ == "Channel":
                full_result = await client(functions.channels.GetFullChannelRequest(entity))
                full_info = getattr(full_result, "full_chat", None)
        except Exception:
            # Entity resolution is still useful when Telegram withholds expanded fields.
            full_info = None

        return self._entity_response(
            entity,
            full_info=full_info,
            scraped_at=scraped_at,
            status="found_with_authorized_session",
        )

    async def _check_invite(self, client: Any, invite_hash: str, scraped_at: str) -> dict[str, Any]:
        invite = await client(functions.messages.CheckChatInviteRequest(invite_hash))
        invite_type = invite.__class__.__name__
        chat = getattr(invite, "chat", None)
        if chat is not None:
            response = self._entity_response(
                chat,
                full_info=None,
                scraped_at=scraped_at,
                status="invite_accessible" if invite_type == "ChatInviteAlready" else "invite_preview",
            )
        else:
            response = self._response(
                success=True,
                exists=True,
                status="invite_preview",
                target_type="invite_link",
                scraped_at=scraped_at,
                entity_type="channel" if getattr(invite, "broadcast", False) else "group",
                full_name=self._clean_text(getattr(invite, "title", None)),
                display_name=self._clean_text(getattr(invite, "title", None)),
                bio=self._clean_text(getattr(invite, "about", None)),
                member_count=getattr(invite, "participants_count", None),
                is_verified=bool(getattr(invite, "verified", False)),
                is_scam=bool(getattr(invite, "scam", False)),
                is_fake=bool(getattr(invite, "fake", False)),
                join_request_required=bool(getattr(invite, "request_needed", False)),
            )

        response.update(
            {
                "target_type": "invite_link",
                "invite_valid": True,
                "already_joined": invite_type == "ChatInviteAlready",
                "join_performed": False,
                "invite_hash_redacted": True,
            }
        )
        response.pop("profile_url", None)
        return response

    def _entity_response(
        self,
        entity: Any,
        *,
        full_info: Any,
        scraped_at: str,
        status: str,
    ) -> dict[str, Any]:
        username = self._clean_text(getattr(entity, "username", None))
        title = self._clean_text(getattr(entity, "title", None))
        first_name = self._clean_text(getattr(entity, "first_name", None))
        last_name = self._clean_text(getattr(entity, "last_name", None))
        full_name = title or " ".join(part for part in (first_name, last_name) if part) or username
        entity_type = self._entity_kind(entity)
        participant_count = getattr(full_info, "participants_count", None) or getattr(
            entity, "participants_count", None
        )
        status_data = self._status_data(getattr(entity, "status", None))

        response = self._response(
            success=True,
            exists=True,
            status=status,
            target_type="username",
            scraped_at=scraped_at,
            username=username,
            profile_url=f"https://t.me/{username}" if username else None,
            entity_id=getattr(entity, "id", None),
            entity_type=entity_type,
            full_name=full_name,
            display_name=full_name,
            bio=self._clean_text(getattr(full_info, "about", None)),
            description=self._clean_text(getattr(full_info, "about", None)),
            member_count=participant_count if entity_type == "group" else None,
            subscriber_count=participant_count if entity_type == "channel" else None,
            is_verified=bool(getattr(entity, "verified", False)),
            is_bot=bool(getattr(entity, "bot", False)),
            is_premium=bool(getattr(entity, "premium", False)),
            is_restricted=bool(getattr(entity, "restricted", False)),
            is_scam=bool(getattr(entity, "scam", False)),
            is_fake=bool(getattr(entity, "fake", False)),
            profile_photo_present=getattr(entity, "photo", None) is not None,
            common_chat_count=getattr(full_info, "common_chats_count", None),
            **status_data,
        )
        return response

    def _configuration_error(self, target_type: str, scraped_at: str) -> dict[str, Any] | None:
        if not self.enabled:
            return self._response(
                success=False,
                exists=None,
                status="authorized_lookup_disabled",
                target_type=target_type,
                scraped_at=scraped_at,
                error="Set TELEGRAM_MTPROTO_ENABLED=true after completing local authorization.",
            )
        if not self.dependency_available or self.client_factory is None:
            return self._response(
                success=False,
                exists=None,
                status="telethon_not_installed",
                target_type=target_type,
                scraped_at=scraped_at,
                error="Install backend requirements to enable authorized Telegram lookup.",
            )
        if not self.api_id or not self.api_hash:
            return self._response(
                success=False,
                exists=None,
                status="telegram_api_credentials_missing",
                target_type=target_type,
                scraped_at=scraped_at,
                error="Set TELEGRAM_API_ID and TELEGRAM_API_HASH locally.",
            )
        if not self._session_file().is_file():
            return self._response(
                success=False,
                exists=None,
                status="authorized_session_required",
                target_type=target_type,
                scraped_at=scraped_at,
                error="Run python -m backend.scripts.telegram_authorize to create the local session.",
            )
        return None

    def _handle_telegram_error(
        self,
        exc: Exception,
        *,
        target_type: str,
        username: str | None,
        scraped_at: str,
    ) -> dict[str, Any]:
        error_name = exc.__class__.__name__
        status = "telegram_api_error"
        exists: bool | None = None
        retry_after = None

        if error_name in {"UsernameInvalidError", "UsernameNotOccupiedError"}:
            status, exists = "not_found", False
        elif error_name == "InviteHashInvalidError":
            status, exists = "invite_invalid", False
        elif error_name == "InviteHashExpiredError":
            status, exists = "invite_expired", False
        elif error_name in {"ChannelPrivateError", "ChatAdminRequiredError"}:
            status = "access_denied"
        elif error_name == "FloodWaitError":
            status = "rate_limited"
            retry_after = getattr(exc, "seconds", None)
        elif isinstance(exc, ValueError):
            status, exists = "not_found_or_inaccessible", False

        return self._response(
            success=False,
            exists=exists,
            status=status,
            target_type=target_type,
            scraped_at=scraped_at,
            username=username,
            error_type=error_name,
            error="Telegram did not permit this read-only lookup for the authorized account.",
            retry_after_seconds=retry_after,
        )

    def _response(
        self,
        *,
        success: bool,
        exists: bool | None,
        status: str,
        target_type: str,
        scraped_at: str,
        **extra: Any,
    ) -> dict[str, Any]:
        response: dict[str, Any] = {
            "success": success,
            "platform": "telegram",
            "exists": exists,
            "status": status,
            "target_type": target_type,
            "source": "telegram_mtproto_authorized",
            "collection_method": "authorized_user_session_read_only",
            "scraped_at": scraped_at,
            "access_scope": "only_data_visible_to_the_authenticated_account",
            "join_performed": False,
            "message_history_accessed": False,
            "sensitive_fields_omitted": ["phone", "contacts", "access_hash"],
            "limitations": self._limitations(),
        }
        response.update({key: value for key, value in extra.items() if value is not None})
        return response

    def _session_file(self) -> Path:
        path = Path(self.session_path).expanduser()
        return path if path.suffix == ".session" else Path(f"{path}.session")

    @staticmethod
    def extract_invite_hash(value: str) -> str | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        if raw.lower().startswith("tg://"):
            parsed = urlparse(raw)
            invite = parse_qs(parsed.query).get("invite", [])
            return invite[0] if invite else None
        parsed = urlparse(raw if "://" in raw else f"https://{raw}")
        if parsed.netloc.lower() not in {"t.me", "telegram.me", "telegram.dog"}:
            return None
        path = parsed.path.strip("/")
        match = TelegramMTProtoService.INVITE_PATH_PATTERN.fullmatch(path)
        return match.group(1) if match else None

    @staticmethod
    def normalize_username(value: str) -> str | None:
        raw = str(value or "").strip().lstrip("@")
        if "://" in raw or raw.lower().startswith(("t.me/", "telegram.me/")):
            parsed = urlparse(raw if "://" in raw else f"https://{raw}")
            parts = [part for part in parsed.path.split("/") if part]
            raw = parts[0] if parts else ""
        raw = raw.split("?", 1)[0].split("#", 1)[0].lstrip("@").strip()
        return raw if re.fullmatch(r"[A-Za-z0-9_]{5,32}", raw) else None

    @staticmethod
    def _entity_kind(entity: Any) -> str:
        class_name = entity.__class__.__name__
        if class_name == "User":
            return "bot" if getattr(entity, "bot", False) else "user"
        if class_name == "Channel":
            return "group" if getattr(entity, "megagroup", False) else "channel"
        if class_name in {"Chat", "ChatInvite"}:
            return "group"
        return "telegram_entity"

    @staticmethod
    def _status_data(status: Any) -> dict[str, Any]:
        if status is None:
            return {}
        status_name = status.__class__.__name__
        mapping = {
            "UserStatusOnline": "online",
            "UserStatusOffline": "offline",
            "UserStatusRecently": "recently",
            "UserStatusLastWeek": "last_week",
            "UserStatusLastMonth": "last_month",
            "UserStatusEmpty": "hidden",
        }
        result: dict[str, Any] = {"activity_status": mapping.get(status_name, "unknown")}
        was_online = getattr(status, "was_online", None)
        if was_online:
            result["last_seen"] = was_online.isoformat() if hasattr(was_online, "isoformat") else str(was_online)
        return result

    @staticmethod
    def _clean_text(value: Any) -> str | None:
        if value is None:
            return None
        text = re.sub(r"\s+", " ", str(value)).strip()
        return text or None

    @staticmethod
    def _limitations() -> list[str]:
        return [
            "The authenticated Telegram account's privacy and membership permissions are enforced.",
            "Invite links are previewed only; the service never joins a group or channel.",
            "Messages, contacts, phone numbers, and private content are not collected.",
            "Telegram may rate-limit or deny entity resolution and expanded profile fields.",
        ]
