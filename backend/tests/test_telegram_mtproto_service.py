import asyncio
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from backend.services.telegram_mtproto_service import TelegramMTProtoService


User = type("User", (), {})
ChatInvite = type("ChatInvite", (), {})
UserStatusRecently = type("UserStatusRecently", (), {})


class FakeTelegramClient:
    def __init__(self, *, authorized=True, entity=None, invite=None) -> None:
        self.authorized = authorized
        self.entity = entity
        self.invite = invite
        self.session = SimpleNamespace(save_entities=True)
        self.connected = False
        self.requests: list[str] = []
        self.sent_messages: list[tuple[object, str]] = []
        self._outbound_message_id = 99
        self.bot_lookup_error = False

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    def is_connected(self) -> bool:
        return self.connected

    async def is_user_authorized(self) -> bool:
        return self.authorized

    async def get_entity(self, username: str):
        if self.bot_lookup_error and str(username).startswith("@"):
            raise RuntimeError("bot unavailable")
        if self.entity is None:
            raise ValueError("entity unavailable")
        return self.entity

    async def send_message(self, entity, message: str):
        self._outbound_message_id += 2
        self.sent_messages.append((entity, message))
        return SimpleNamespace(id=self._outbound_message_id, date=datetime.now(UTC))

    async def get_messages(self, entity, limit: int = 2):
        target = self.sent_messages[-1][1]
        return [
            SimpleNamespace(
                text=f"Public bot response for {target}",
                id=self._outbound_message_id + 1,
                date=datetime.now(UTC),
                out=False,
                reply_to_msg_id=self._outbound_message_id,
            )
        ]

    async def __call__(self, request):
        request_name = request.__class__.__name__
        self.requests.append(request_name)
        if request_name == "GetFullUserRequest":
            return SimpleNamespace(
                full_user=SimpleNamespace(about="Visible account bio", common_chats_count=2)
            )
        if request_name == "CheckChatInviteRequest":
            return self.invite
        raise AssertionError(f"Unexpected Telegram request: {request_name}")


class TelegramMTProtoServiceTests(unittest.IsolatedAsyncioTestCase):
    def _service(
        self,
        temp_dir: str,
        client: FakeTelegramClient,
        *,
        enabled=True,
        bot_queries_enabled=False,
        timeout=5,
    ):
        session_path = Path(temp_dir) / "authorized.session"
        session_path.touch()
        return TelegramMTProtoService(
            enabled=enabled,
            api_id=12345,
            api_hash="test-api-hash",
            session_path=str(session_path),
            timeout=timeout,
            bot_queries_enabled=bot_queries_enabled,
            client_factory=lambda *args, **kwargs: client,
        )

    def test_extract_invite_hash_supports_current_and_legacy_links(self) -> None:
        self.assertEqual(
            TelegramMTProtoService.extract_invite_hash("https://t.me/+AbC_123-x"),
            "AbC_123-x",
        )
        self.assertEqual(
            TelegramMTProtoService.extract_invite_hash("t.me/joinchat/AbC_123-x"),
            "AbC_123-x",
        )
        self.assertEqual(
            TelegramMTProtoService.extract_invite_hash("tg://join?invite=AbC_123-x"),
            "AbC_123-x",
        )
        self.assertIsNone(TelegramMTProtoService.extract_invite_hash("https://t.me/public_user"))

    async def test_disabled_mode_never_creates_a_client(self) -> None:
        created = False

        def factory(*args, **kwargs):
            nonlocal created
            created = True
            return FakeTelegramClient()

        service = TelegramMTProtoService(
            enabled=False,
            api_id=12345,
            api_hash="test-api-hash",
            session_path="missing.session",
            client_factory=factory,
        )

        result = await service.lookup("public_user")

        self.assertEqual(result["status"], "authorized_lookup_disabled")
        self.assertFalse(created)

    async def test_existing_session_resolves_visible_user_without_sensitive_fields(self) -> None:
        user = User()
        user.id = 987654
        user.username = "visible_user"
        user.first_name = "Visible"
        user.last_name = "User"
        user.bot = False
        user.verified = True
        user.premium = True
        user.restricted = False
        user.scam = False
        user.fake = False
        user.photo = object()
        user.status = UserStatusRecently()
        client = FakeTelegramClient(entity=user)

        with tempfile.TemporaryDirectory() as temp_dir:
            result = await self._service(temp_dir, client).lookup("visible_user")

        self.assertTrue(result["success"])
        self.assertTrue(result["exists"])
        self.assertEqual(result["source"], "telegram_mtproto_authorized")
        self.assertEqual(result["entity_id"], 987654)
        self.assertEqual(result["full_name"], "Visible User")
        self.assertEqual(result["bio"], "Visible account bio")
        self.assertEqual(result["activity_status"], "recently")
        self.assertNotIn("phone", result)
        self.assertFalse(result["message_history_accessed"])
        self.assertFalse(result["third_party_bot_queries_performed"])
        self.assertFalse(result["bot_response_messages_read"])
        self.assertEqual(client.sent_messages, [])
        self.assertFalse(result["join_performed"])
        self.assertFalse(client.session.save_entities)
        self.assertFalse(client.connected)

    async def test_third_party_bot_queries_require_explicit_opt_in(self) -> None:
        user = User()
        user.id = 42
        user.username = "visible_user"
        user.first_name = "Visible"
        user.last_name = "User"
        user.bot = False
        user.verified = False
        user.premium = False
        user.restricted = False
        user.scam = False
        user.fake = False
        user.photo = None
        user.status = None
        client = FakeTelegramClient(entity=user)

        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch(
                "backend.services.telegram_mtproto_service.asyncio.sleep",
                new=AsyncMock(),
            ),
        ):
            result = await self._service(temp_dir, client, bot_queries_enabled=True).lookup(
                "visible_user"
            )

        self.assertTrue(result["third_party_bot_queries_performed"])
        self.assertTrue(result["bot_response_messages_read"])
        self.assertEqual(result["third_party_bot_queries_attempted"], 2)
        self.assertEqual(result["third_party_bot_queries_succeeded"], 2)
        self.assertEqual(result["bot_dialog_messages_fetched"], 2)
        self.assertFalse(result["target_message_history_accessed"])
        self.assertEqual(len(client.sent_messages), 2)
        self.assertEqual({message for _, message in client.sent_messages}, {"visible_user"})

    async def test_failed_bot_queries_do_not_claim_responses_were_read(self) -> None:
        user = User()
        user.id = 42
        user.username = "visible_user"
        user.first_name = "Visible"
        user.last_name = "User"
        user.bot = False
        user.verified = False
        user.premium = False
        user.restricted = False
        user.scam = False
        user.fake = False
        user.photo = None
        user.status = None
        client = FakeTelegramClient(entity=user)
        client.bot_lookup_error = True

        with tempfile.TemporaryDirectory() as temp_dir:
            result = await self._service(
                temp_dir,
                client,
                bot_queries_enabled=True,
            ).lookup("visible_user")

        self.assertEqual(result["third_party_bot_queries_attempted"], 2)
        self.assertFalse(result["third_party_bot_queries_performed"])
        self.assertEqual(result["third_party_bot_queries_succeeded"], 0)
        self.assertFalse(result["bot_response_messages_read"])
        self.assertNotIn("bot_responses", result)

    async def test_stale_bot_message_is_not_attached_to_current_target(self) -> None:
        user = User()
        user.id = 42
        user.username = "visible_user"
        user.first_name = "Visible"
        user.last_name = "User"
        user.bot = False
        user.verified = False
        user.premium = False
        user.restricted = False
        user.scam = False
        user.fake = False
        user.photo = None
        user.status = None
        client = FakeTelegramClient(entity=user)
        client.get_messages = AsyncMock(
            return_value=[
                SimpleNamespace(
                    text="Public bot response for visible_user_old",
                    id=999,
                    date=datetime.now(UTC),
                    out=False,
                    reply_to_msg_id=None,
                )
            ]
        )

        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch(
                "backend.services.telegram_mtproto_service.asyncio.sleep",
                new=AsyncMock(),
            ),
        ):
            result = await self._service(
                temp_dir,
                client,
                bot_queries_enabled=True,
            ).lookup("visible_user")

        self.assertTrue(result["third_party_bot_queries_performed"])
        self.assertEqual(result["third_party_bot_queries_succeeded"], 0)
        self.assertFalse(result["bot_response_messages_read"])
        self.assertNotIn("bot_responses", result)

    async def test_lookup_timeout_preserves_bot_disclosure_audit(self) -> None:
        user = User()
        user.id = 42
        user.username = "visible_user"
        user.first_name = "Visible"
        user.last_name = "User"
        user.bot = False
        user.verified = False
        user.premium = False
        user.restricted = False
        user.scam = False
        user.fake = False
        user.photo = None
        user.status = None
        client = FakeTelegramClient(entity=user)

        async def never_finish(_: float) -> None:
            await asyncio.Future()

        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch(
                "backend.services.telegram_mtproto_service.asyncio.sleep",
                new=never_finish,
            ),
        ):
            result = await self._service(
                temp_dir,
                client,
                bot_queries_enabled=True,
                timeout=0.02,
            ).lookup("visible_user")

        self.assertEqual(result["status"], "authorized_lookup_timeout")
        self.assertEqual(result["third_party_bot_queries_attempted"], 1)
        self.assertTrue(result["third_party_bot_queries_performed"])
        self.assertEqual(result["third_party_bot_queries_succeeded"], 0)
        self.assertFalse(result["bot_response_messages_read"])
        self.assertEqual(len(client.sent_messages), 1)

    async def test_direct_bot_query_honors_default_off_policy(self) -> None:
        client = FakeTelegramClient(entity=User())
        with tempfile.TemporaryDirectory() as temp_dir:
            result = await self._service(
                temp_dir,
                client,
                bot_queries_enabled=False,
            ).query_osint_bot(client, "@userinfobot", "visible_user")

        self.assertEqual(result["status"], "disabled_by_policy")
        self.assertFalse(result["query_attempted"])
        self.assertEqual(client.sent_messages, [])

    async def test_invite_is_previewed_without_joining(self) -> None:
        invite = ChatInvite()
        invite.title = "Private Research Group"
        invite.about = "Visible invite description"
        invite.participants_count = 42
        invite.broadcast = False
        invite.verified = False
        invite.scam = False
        invite.fake = False
        invite.request_needed = True
        client = FakeTelegramClient(invite=invite)

        with tempfile.TemporaryDirectory() as temp_dir:
            result = await self._service(temp_dir, client).lookup("https://t.me/+AbC_123-x")

        self.assertTrue(result["invite_valid"])
        self.assertEqual(result["status"], "invite_preview")
        self.assertEqual(result["full_name"], "Private Research Group")
        self.assertEqual(result["member_count"], 42)
        self.assertTrue(result["join_request_required"])
        self.assertFalse(result["join_performed"])
        self.assertNotIn("profile_url", result)
        self.assertEqual(client.requests, ["CheckChatInviteRequest"])

    async def test_unauthorized_session_returns_setup_status(self) -> None:
        client = FakeTelegramClient(authorized=False)

        with tempfile.TemporaryDirectory() as temp_dir:
            result = await self._service(temp_dir, client).lookup("visible_user")

        self.assertFalse(result["success"])
        self.assertIsNone(result["exists"])
        self.assertEqual(result["status"], "authorized_session_required")


if __name__ == "__main__":
    unittest.main()
