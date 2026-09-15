"""Offline Target Scan integration tests for GitHub and YouTube collectors."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException, Response

from app.api import investigation
from app.schemas.investigation import InvestigationRequest
from app.security.auth import AuthenticatedUser
from app.services.apify_client import ApifyAccountCapacity


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def investigator_user() -> AuthenticatedUser:
    return AuthenticatedUser(
        username="uppolice",
        roles=("investigator", "breach_pii_viewer"),
        expires_at=datetime.now(UTC),
        csrf_token="offline-csrf",
        session_id="offline-session",
    )


def _github_success() -> dict[str, Any]:
    profile_url = "https://github.com/alice"
    return {
        "success": True,
        "found": True,
        "configured": True,
        "status": "completed",
        "platform": "github",
        "provider": "github_rest",
        "source": "github_public_api",
        "username": "alice",
        "full_name": "Alice Analyst",
        "bio": "Public security projects",
        "email": "github-public@example.org",
        "url": profile_url,
        "profile_url": profile_url,
        "profile": {
            "username": "alice",
            "full_name": "Alice Analyst",
            "email": "github-public@example.org",
            "url": profile_url,
        },
        "repositories": [
            {
                "name": "incident-tools",
                "url": "https://github.com/alice/incident-tools",
                "description": "Public incident-response utilities",
            }
        ],
        "recent_activity": [
            {
                "id": "event-1",
                "type": "PushEvent",
                "repository": "alice/incident-tools",
                "text": "Pushed one commit to alice/incident-tools",
            }
        ],
        "recent_posts": [],
        "all_hashtags": [],
        "usage": {
            "calls_made": 3,
            "call_limit": 3,
            "fallback_used": False,
        },
    }


def _youtube_success() -> dict[str, Any]:
    profile_url = "https://www.youtube.com/@alice"
    return {
        "success": True,
        "found": True,
        "configured": True,
        "status": "completed",
        "platform": "youtube",
        "provider": "youtube_data_api_v3",
        "source": "youtube_data_api_v3",
        "username": "alice",
        "full_name": "Alice Security",
        "description": (
            "Public channel contact youtube-public@example.org or "
            "+91 91234 56789. #CyberSafe"
        ),
        "bio": "Public channel #CyberSafe",
        "url": profile_url,
        "profile_url": profile_url,
        "profile": {
            "channel_id": "UC123",
            "username": "alice",
            "full_name": "Alice Security",
            "url": profile_url,
        },
        "channel": {
            "channel_id": "UC123",
            "username": "alice",
            "full_name": "Alice Security",
            "url": profile_url,
        },
        "videos": [
            {
                "id": "video-1",
                "url": "https://www.youtube.com/watch?v=video-1",
                "title": "Investigation update #YouTubeOnly",
                "description": "A public update #CyberSafe",
                "hashtags": ["youtubeonly", "cybersafe"],
            }
        ],
        "recent_posts": [],
        "hashtags": ["cybersafe", "youtubeonly"],
        "all_hashtags": ["cybersafe", "youtubeonly"],
        "quota_units_used": 3,
        "usage": {
            "calls_made": 3,
            "call_limit": 3,
            "quota_units_used": 3,
        },
    }


def _install_offline_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    *,
    github_result: dict[str, Any] | None = None,
    youtube_result: dict[str, Any] | None = None,
    github_raises: bool = False,
    youtube_raises: bool = False,
) -> tuple[dict[str, list[str]], dict[str, Any]]:
    """Replace every provider used by the endpoint with in-memory doubles."""

    calls: dict[str, list[str]] = {"github": [], "youtube": []}
    captured: dict[str, Any] = {}
    monkeypatch.setattr(investigation.settings, "signalhire_api_key", None)
    monkeypatch.setattr(investigation.settings, "rocketreach_api_key", None)
    monkeypatch.setattr(investigation.settings, "hunter_api_key", None)
    monkeypatch.setattr(investigation.settings, "zerobounce_api_key", None)
    monkeypatch.setattr(investigation.settings, "groq_api_key", None)
    monkeypatch.setattr(
        investigation.settings,
        "cti_external_ai_filtering_enabled",
        False,
    )

    class FakeApifyClient:
        async def check_account_capacity(self) -> ApifyAccountCapacity:
            return ApifyAccountCapacity(
                state="not_checked",
                configured=False,
                checked=False,
                can_start_runs=None,
            )

    def async_service(method: str, result: object) -> SimpleNamespace:
        async def run(*_args: object, **_kwargs: object) -> object:
            return result

        return SimpleNamespace(**{method: run})

    class FakeGitHubService:
        async def fetch_profile_and_activity(self, username: str) -> dict[str, Any]:
            calls["github"].append(username)
            if github_raises:
                raise RuntimeError("offline GitHub collector failure")
            return github_result or _github_success()

    class FakeYouTubeService:
        async def fetch_channel_and_videos(self, username: str) -> dict[str, Any]:
            calls["youtube"].append(username)
            if youtube_raises:
                raise RuntimeError("offline YouTube collector failure")
            return youtube_result or _youtube_success()

    monkeypatch.setattr(investigation, "ApifyActorClient", FakeApifyClient)
    monkeypatch.setattr(investigation, "GitHubService", FakeGitHubService)
    monkeypatch.setattr(investigation, "YouTubeService", FakeYouTubeService)
    monkeypatch.setattr(
        investigation,
        "InstagramService",
        lambda **_kwargs: async_service(
            "fetch_profile_and_posts",
            {
                "success": False,
                "configured": False,
                "status": "disabled",
                "platform": "instagram",
                "posts": [],
            },
        ),
    )
    monkeypatch.setattr(
        investigation,
        "TikTokService",
        lambda **_kwargs: async_service(
            "fetch_profile_and_videos",
            {
                "success": False,
                "configured": False,
                "status": "disabled",
                "platform": "tiktok",
            },
        ),
    )
    monkeypatch.setattr(
        investigation,
        "TwitterService",
        lambda **_kwargs: async_service(
            "fetch_profile_and_tweets",
            {
                "success": False,
                "configured": False,
                "status": "disabled",
                "platform": "twitter",
            },
        ),
    )
    monkeypatch.setattr(
        investigation,
        "FacebookService",
        lambda **_kwargs: async_service(
            "fetch_page_or_profile",
            {
                "success": False,
                "configured": False,
                "status": "disabled",
                "platform": "facebook",
            },
        ),
    )
    monkeypatch.setattr(
        investigation,
        "DorkingService",
        lambda: async_service(
            "run_dorks",
            {
                "status": "completed",
                "results": [],
                "queries_run": 0,
                "results_count": 0,
            },
        ),
    )
    monkeypatch.setattr(
        investigation,
        "WhatsMyNameService",
        lambda: async_service(
            "probe_username",
            {"status": "success", "scanned": 0, "hits_count": 0, "hits": []},
        ),
    )
    monkeypatch.setattr(
        investigation,
        "WikidataService",
        lambda: async_service(
            "search_and_get_profile",
            {"success": False, "found": False, "status": "no_results"},
        ),
    )

    class FakeSignalHireService:
        async def search_candidate(self, _identifier: str) -> dict[str, Any]:
            raise AssertionError("SignalHire must not be called by this fixture")

    class FakeRocketReachService:
        async def lookup_by_linkedin_url(self, _url: str) -> dict[str, Any]:
            raise AssertionError("RocketReach must not be called by this fixture")

    class FakeEmailVerifierService:
        @staticmethod
        def process_pattern_guesses(
            _username: str,
            _full_name: str | None,
        ) -> list[dict[str, Any]]:
            return []

        @staticmethod
        async def verify_with_hunter(email: str) -> dict[str, Any]:
            return {
                "email": email,
                "status": "observed",
                "deliverable": None,
                "verification_provider": "local",
            }

    class FakeTelegramService:
        async def search_cti_breaches(self, _queries: list[str]) -> dict[str, Any]:
            return {
                "status": "no_results",
                "searches_performed": 0,
                "total_records": 0,
                "results": [],
                "databases": [],
            }

    class RecordingAnalyzer:
        async def analyze_personality(
            self,
            scraped_data: dict[str, Any],
            _dorking: dict[str, Any],
            _instagram: dict[str, Any],
            hashtag_analysis: dict[str, Any],
        ) -> dict[str, Any]:
            captured["scraped_data"] = scraped_data
            captured["hashtag_analysis"] = hashtag_analysis
            return {
                "summary": "Offline GitHub and YouTube analysis",
                "traits": [],
                "interests": ["youtubeonly"],
                "tone": "neutral",
                "riskFlags": [],
                "primaryCategory": "Cybersecurity & Incident Response",
                "confidence": 60,
                "confidenceLabel": "moderate",
                "evidence": ["#youtubeonly"],
                "secondaryCategories": [],
                "crossPlatformNote": "YouTube hashtag evidence was analyzed",
                "platformCount": len(scraped_data),
            }

    monkeypatch.setattr(investigation, "SignalHireService", FakeSignalHireService)
    monkeypatch.setattr(investigation, "RocketReachService", FakeRocketReachService)
    monkeypatch.setattr(investigation, "EmailVerifierService", FakeEmailVerifierService)
    monkeypatch.setattr(investigation, "TelegramService", FakeTelegramService)
    monkeypatch.setattr(
        investigation,
        "HiTekService",
        lambda: SimpleNamespace(
            search_records=lambda _query: {"status": "not_available", "matches": []}
        ),
    )
    monkeypatch.setattr(
        investigation,
        "AssociatedAccountsService",
        SimpleNamespace(verify_account_matches=lambda *_args: []),
    )
    monkeypatch.setattr(investigation, "AIAnalyzer", RecordingAnalyzer)

    async def no_audit(**_kwargs: object) -> None:
        return None

    monkeypatch.setattr(investigation, "_record_contact_investigation_access", no_audit)

    from app.services import linkedin_apify_service

    class FakeLinkedInService:
        def __init__(self, **_kwargs: object) -> None:
            pass

        async def get_profile(self, _username: str) -> dict[str, Any]:
            return {
                "success": False,
                "configured": False,
                "status": "disabled",
                "platform": "linkedin",
            }

        async def search_posts(self, **_kwargs: object) -> dict[str, Any]:
            raise AssertionError("LinkedIn posts must not run without a profile")

    monkeypatch.setattr(
        linkedin_apify_service,
        "LinkedInApifyService",
        FakeLinkedInService,
    )
    return calls, captured


@pytest.mark.anyio
async def test_username_collectors_reach_target_scan_hashtags_and_contacts(
    monkeypatch: pytest.MonkeyPatch,
    investigator_user: AuthenticatedUser,
) -> None:
    calls, captured = _install_offline_pipeline(monkeypatch)

    result = await investigation.run_investigation(
        InvestigationRequest(username="@alice"),
        Response(),
        investigator_user,
        investigator_user,
    )

    assert calls == {"github": ["alice"], "youtube": ["alice"]}
    assert result.status == "completed"
    assert result.scraped_data is not None
    assert result.scraped_data["github"]["repositories"][0]["name"] == "incident-tools"
    assert result.scraped_data["youtube"]["videos"][0]["id"] == "video-1"
    assert result.provider_statuses is not None
    assert result.provider_statuses["github"]["status"] == "completed"
    assert result.provider_statuses["github"]["provider"] == "github_rest"
    assert result.provider_statuses["youtube"]["status"] == "completed"
    assert result.provider_statuses["youtube"]["provider"] == "youtube_data_api_v3"

    assert result.hashtag_analysis is not None
    youtube_hashtags = result.hashtag_analysis.platforms["youtube"].hashtags
    assert "cybersafe" in youtube_hashtags
    assert "youtubeonly" in youtube_hashtags
    assert captured["scraped_data"]["youtube"]["videos"][0]["id"] == "video-1"
    assert "youtube" in captured["hashtag_analysis"]["platforms"]
    captured_tags = {
        item["tag"] for item in captured["hashtag_analysis"]["top_hashtags"]
    }
    assert {"cybersafe", "youtubeonly"}.issubset(captured_tags)
    assert result.ai_personality is not None
    assert result.ai_personality.interests == ["youtubeonly"]

    assert result.contact_discovery is not None
    emails = {item.email: item for item in result.contact_discovery.emails}
    assert {"github-public@example.org", "youtube-public@example.org"}.issubset(emails)
    github_source = emails["github-public@example.org"].sources[0]
    assert (
        github_source.source,
        github_source.field,
        github_source.collection_method,
        github_source.platform,
        github_source.provider,
    ) == (
        "github",
        "email",
        "public_profile",
        "github",
        "github_rest",
    )
    youtube_source = emails["youtube-public@example.org"].sources[0]
    assert (
        youtube_source.source,
        youtube_source.field,
        youtube_source.collection_method,
        youtube_source.platform,
        youtube_source.provider,
    ) == (
        "youtube",
        "description",
        "public_profile_text",
        "youtube",
        "youtube_data_api_v3",
    )
    youtube_phone = next(
        item for item in result.contact_discovery.phones if item.e164 == "+919123456789"
    )
    assert youtube_phone.sources[0].source == "youtube"
    assert youtube_phone.sources[0].field == "description"
    assert youtube_phone.sources[0].collection_method == "public_profile_text"


@pytest.mark.anyio
async def test_non_username_skips_both_collectors_with_reason(
    monkeypatch: pytest.MonkeyPatch,
    investigator_user: AuthenticatedUser,
) -> None:
    calls, _captured = _install_offline_pipeline(monkeypatch)

    result = await investigation.run_investigation(
        InvestigationRequest(username="alice@example.org"),
        Response(),
        investigator_user,
        investigator_user,
    )

    assert calls == {"github": [], "youtube": []}
    assert result.status == "completed"
    assert result.provider_statuses is not None
    for platform in ("github", "youtube"):
        assert result.provider_statuses[platform]["status"] == "skipped"
        assert (
            result.provider_statuses[platform]["error_code"]
            == "identifier_not_username"
        )
    assert "github" not in (result.scraped_data or {})
    assert "youtube" not in (result.scraped_data or {})


@pytest.mark.anyio
@pytest.mark.parametrize("target", ["@alice/bob", "alice?account=mallory"])
async def test_malformed_username_is_rejected_without_retargeting_collectors(
    monkeypatch: pytest.MonkeyPatch,
    investigator_user: AuthenticatedUser,
    target: str,
) -> None:
    calls, _captured = _install_offline_pipeline(monkeypatch)

    with pytest.raises(HTTPException) as raised:
        await investigation.run_investigation(
            InvestigationRequest(username=target),
            Response(),
            investigator_user,
            investigator_user,
        )

    assert raised.value.status_code == 422
    assert raised.value.detail == "Invalid username target"
    assert calls == {"github": [], "youtube": []}


@pytest.mark.anyio
async def test_one_collector_exception_is_nonfatal_and_other_survives(
    monkeypatch: pytest.MonkeyPatch,
    investigator_user: AuthenticatedUser,
) -> None:
    calls, _captured = _install_offline_pipeline(
        monkeypatch,
        github_raises=True,
    )

    result = await investigation.run_investigation(
        InvestigationRequest(username="alice"),
        Response(),
        investigator_user,
        investigator_user,
    )

    assert calls == {"github": ["alice"], "youtube": ["alice"]}
    assert result.status == "completed"
    assert "github" not in (result.scraped_data or {})
    assert (result.scraped_data or {})["youtube"]["status"] == "completed"
    assert result.provider_statuses is not None
    assert result.provider_statuses["github"]["success"] is False
    assert result.provider_statuses["github"]["status"] == "error"
    assert result.provider_statuses["github"]["error_code"] == "missing_result"
    assert result.provider_statuses["youtube"]["success"] is True
    assert result.provider_statuses["youtube"]["status"] == "completed"


@pytest.mark.anyio
async def test_diagnostics_reports_github_and_youtube_without_health_calls(
    monkeypatch: pytest.MonkeyPatch,
    investigator_user: AuthenticatedUser,
) -> None:
    monkeypatch.setattr(investigation.settings, "github_enabled", True)
    monkeypatch.setattr(investigation.settings, "github_api_token", None)
    monkeypatch.setattr(investigation.settings, "youtube_enabled", True)
    monkeypatch.setattr(investigation.settings, "youtube_api_key", "offline-youtube-key")

    diagnostics = await investigation.get_keys_diagnostics(
        Response(),
        refresh_apify=False,
        _user=investigator_user,
    )

    assert diagnostics["github"]["configured"] is True
    assert diagnostics["github"]["available"] is True
    assert diagnostics["github"]["authenticated"] is False
    assert diagnostics["github"]["status"] == "Active (public anonymous access)"
    assert diagnostics["youtube"]["configured"] is True
    assert diagnostics["youtube"]["available"] is True
    assert diagnostics["youtube"]["status"] == "Active"
