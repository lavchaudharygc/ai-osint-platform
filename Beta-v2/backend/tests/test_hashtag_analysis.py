"""Offline tests for cross-platform hashtag aggregation and AI propagation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import Response

from app.api import investigation
from app.config import settings
from app.schemas.investigation import InvestigationRequest, InvestigationResponse
from app.security.auth import AuthenticatedUser
from app.services.apify_client import ApifyAccountCapacity
from app.services.ai_analyzer import AIAnalyzer
from app.services.hashtag_analysis_service import (
    HashtagAnalysisService,
    extract_hashtags_from_text,
    normalize_hashtag_values,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _profiles() -> dict[str, object]:
    return {
        "instagram": {
            "success": True,
            "bio": "Safety updates #CyberSafe",
            "posts": [
                {
                    "caption": "Alert #CyberSafe,#UPPolice",
                    "hashtags": [{"text": "#Explicit"}],
                },
                {"caption": "Follow #cybersafe"},
            ],
            "post_hashtags": ["CyberSafe", "IGOnly", "AggregateOnly"],
            "hashtags": ["cybersafe", "igonly", "aggregateonly"],
        },
        "tiktok": {
            "success": True,
            "videos": [
                {"text": "Watch #CyberSafe#DigitalIndia"},
                {"text": "Again #cybersafe"},
            ],
            "hashtags": ["CyberSafe", "TikTokOnly"],
        },
        "twitter": {
            "success": True,
            "tweets": [
                {
                    "text": "Public advisory #CyberSafe #UPPolice",
                    "hashtags": [{"tag": "DFIR"}],
                }
            ],
            "hashtags": ["CyberSafe", "UPPolice", "XOnly"],
        },
        "facebook": {
            "success": True,
            "posts": [{"text": "Notice #CyberSafe #UPPolice"}],
            "all_hashtags": ["CyberSafe", "UPPolice", "FbOnly"],
        },
    }


def test_parser_handles_adjacent_unicode_and_provider_shapes() -> None:
    assert extract_hashtags_from_text("#One#TWO, #यूपीपुलिस") == [
        "one",
        "two",
        "यूपीपुलिस",
    ]
    assert normalize_hashtag_values(
        ["#CyberSafe", {"text": "UPPolice"}, {"tag": "#DFIR"}, "one two"]
    ) == ["cybersafe", "dfir", "one", "two", "uppolice"]


def test_analysis_counts_and_attributes_all_four_platforms() -> None:
    analysis = HashtagAnalysisService.analyze(_profiles())

    assert analysis.status == "completed"
    assert analysis.total_unique_hashtags == 10
    assert analysis.total_mentions == 18
    assert analysis.platforms_with_hashtags == 4
    assert analysis.platforms["instagram"].total_mentions == 7
    assert analysis.platforms["instagram"].source_items_with_hashtags == 3
    assert analysis.platforms["tiktok"].total_mentions == 4
    assert analysis.platforms["twitter"].total_mentions == 4
    assert analysis.platforms["facebook"].total_mentions == 3

    metrics = {metric.tag: metric for metric in analysis.top_hashtags}
    assert metrics["cybersafe"].mentions == 7
    assert metrics["cybersafe"].platforms == [
        "facebook",
        "instagram",
        "tiktok",
        "twitter",
    ]
    assert metrics["cybersafe"].cross_platform is True
    assert metrics["uppolice"].mentions == 3
    assert metrics["uppolice"].platforms == ["facebook", "instagram", "twitter"]
    assert [metric.tag for metric in analysis.cross_platform_hashtags] == [
        "cybersafe",
        "uppolice",
    ]


def test_analysis_includes_attributed_linkedin_posts() -> None:
    profiles = _profiles()
    profiles["linkedin"] = {
        "success": True,
        "posts": [
            {
                "text": "Public #CyberSafe #LinkedInOnly update",
                "hashtags": ["CyberSafe", "LinkedInOnly"],
            },
            {"text": "Follow-up #LinkedInOnly"},
        ],
        "all_hashtags": ["CyberSafe", "LinkedInOnly", "AggregateOnly"],
    }

    analysis = HashtagAnalysisService.analyze(profiles)

    assert analysis.platforms_with_hashtags == 5
    assert analysis.platforms["linkedin"].hashtags == [
        "linkedinonly",
        "aggregateonly",
        "cybersafe",
    ]
    assert analysis.platforms["linkedin"].total_mentions == 4
    metrics = {metric.tag: metric for metric in analysis.top_hashtags}
    assert "linkedin" in metrics["cybersafe"].platforms
    assert metrics["linkedinonly"].mentions == 2


def test_analysis_rejects_markup_and_returns_stable_empty_state() -> None:
    malformed = {
        "instagram": {
            "posts": [{"hashtags": ["<img src=x>", "#safe"]}],
            "hashtags": ["x" * 101, "#also_safe"],
        },
        "tiktok": {"hashtags": None},
        "twitter": "not-an-object",
    }
    analysis = HashtagAnalysisService.analyze(malformed)
    assert [metric.tag for metric in analysis.top_hashtags] == ["also_safe", "safe"]

    empty = HashtagAnalysisService.analyze(None)
    assert empty.status == "no_data"
    assert empty.total_unique_hashtags == 0
    assert empty.total_mentions == 0
    assert empty.top_hashtags == []
    assert empty.platforms == {}


@pytest.mark.anyio
async def test_all_platform_hashtags_reach_ai_corpus_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}
    analyzer = AIAnalyzer()
    analyzer.api_key = "offline-test-key"

    async def capture_corpus(corpus: str) -> dict[str, object]:
        captured["corpus"] = corpus
        return {}

    monkeypatch.setattr(analyzer, "_run_groq_analysis", capture_corpus)
    profiles = _profiles()
    profiles["linkedin"] = {
        "success": True,
        "posts": [{"text": "Public #LinkedInOnly update"}],
    }
    analysis = HashtagAnalysisService.analyze(profiles)
    result = await analyzer.analyze_personality(
        profiles,
        dorking=None,
        ig_data=profiles["instagram"],  # type: ignore[arg-type]
        hashtag_analysis=analysis.model_dump(mode="python"),
    )

    corpus = captured["corpus"]
    for marker in (
        "[instagram-hashtags]",
        "[linkedin-hashtags]",
        "[tiktok-hashtags]",
        "[twitter-hashtags]",
        "[facebook-hashtags]",
        "[cross-platform-hashtags]",
    ):
        assert marker in corpus
    assert "#cybersafe" in corpus
    assert "#linkedinonly" in corpus
    assert "#tiktokonly" in corpus
    assert "#xonly" in corpus
    assert "#fbonly" in corpus
    assert result["primaryCategory"] == "Cybersecurity & Incident Response"


def test_analysis_survives_response_model_serialization() -> None:
    analysis = HashtagAnalysisService.analyze(_profiles())
    response = InvestigationResponse(
        investigation_id="UPP-HASHTAG",
        status="completed",
        classified_kind="username",
        target_query="fixture",
        scraped_data=_profiles(),
        hashtag_analysis=analysis,
        timestamp=datetime.now(UTC),
    )
    serialized = response.model_dump(mode="json")

    assert serialized["hashtag_analysis"]["status"] == "completed"
    assert serialized["hashtag_analysis"]["platforms_with_hashtags"] == 4
    assert serialized["hashtag_analysis"]["top_hashtags"][0]["tag"] == "cybersafe"


@pytest.mark.anyio
async def test_investigation_propagates_collector_hashtags_to_ai_and_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise the real endpoint pipeline with offline provider doubles."""

    profiles = _profiles()
    captured: dict[str, Any] = {}
    shared_apify_clients: list[Any] = []
    linkedin_post_calls: list[dict[str, Any]] = []
    linkedin_post_failure = {"enabled": False}

    class FakeApifyClient:
        async def check_account_capacity(self) -> ApifyAccountCapacity:
            return ApifyAccountCapacity(
                state="ready",
                configured=True,
                checked=True,
                can_start_runs=True,
            )

    class FakeInstagramService:
        def __init__(self, **kwargs: Any) -> None:
            shared_apify_clients.append(kwargs.get("client"))

        async def fetch_profile_and_posts(self, _username: str) -> dict[str, Any]:
            return profiles["instagram"]  # type: ignore[return-value]

    class FakeTikTokService:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        async def fetch_profile_and_videos(self, _username: str) -> dict[str, Any]:
            return profiles["tiktok"]  # type: ignore[return-value]

    class FakeTwitterService:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        async def fetch_profile_and_tweets(self, _username: str) -> dict[str, Any]:
            return profiles["twitter"]  # type: ignore[return-value]

    class FakeFacebookService:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        async def fetch_page_or_profile(self, _username: str) -> dict[str, Any]:
            return profiles["facebook"]  # type: ignore[return-value]

    class FakeDorkingService:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        async def run_dorks(self, _query: str) -> dict[str, Any]:
            return {"status": "completed", "results": [], "queries_run": 0, "results_count": 0}

    class FakeWhatsMyNameService:
        async def probe_username(self, _query: str) -> dict[str, Any]:
            return {"status": "success", "scanned": 0, "hits_count": 0, "hits": []}

    class FakeWikidataService:
        async def search_and_get_profile(self, _query: str) -> dict[str, Any]:
            return {"found": False}

    class FakeLinkedInService:
        def __init__(self, **kwargs: Any) -> None:
            shared_apify_clients.append(kwargs.get("client"))

        async def get_profile(self, _username: str) -> dict[str, Any]:
            return {
                "success": True,
                "configured": True,
                "status": "completed",
                "platform": "linkedin",
                "full_name": "Alice Analyst",
                "profile_url": "https://www.linkedin.com/in/alice/",
            }

        async def search_posts(self, **kwargs: Any) -> dict[str, Any]:
            linkedin_post_calls.append(kwargs)
            if linkedin_post_failure["enabled"]:
                raise RuntimeError("offline LinkedIn posts failure")
            post = {
                "id": "linkedin-post-1",
                "url": "https://www.linkedin.com/posts/alice_public-update-1",
                "text": "Public #CyberSafe #LinkedInOnly update",
                "hashtags": ["CyberSafe", "LinkedInOnly"],
                "author": {
                    "name": "Alice Analyst",
                    "profile_url": "https://www.linkedin.com/in/alice/",
                },
            }
            return {
                "success": True,
                "configured": True,
                "status": "completed",
                "platform": "linkedin",
                "source": "apify_linkedin_posts_search",
                "actor_id": "test/linkedin-posts",
                "posts": [post],
                "recent_posts": [post],
                "all_hashtags": ["CyberSafe", "LinkedInOnly"],
                "total": 1,
                "provider_total": 1,
            }

    class FakeSignalHireService:
        async def search_candidate(self, _query: str) -> dict[str, Any]:
            return {"success": False}

    class FakeRocketReachService:
        async def lookup_by_linkedin_url(self, _url: str) -> dict[str, Any]:
            return {"success": False, "emails": [], "phones": []}

    class FakeEmailVerifierService:
        @staticmethod
        def process_pattern_guesses(_username: str, _full_name: str | None) -> list[dict[str, Any]]:
            return []

        @staticmethod
        async def verify_with_hunter(_email: str) -> dict[str, Any]:
            raise AssertionError("No email verification should be scheduled in this fixture")

    class FakeTelegramService:
        async def search_cti_breaches(self, _queries: list[str]) -> dict[str, Any]:
            return {
                "status": "no_results",
                "searches_performed": 0,
                "total_records": 0,
                "results": [],
                "databases": [],
            }

    class FakeHiTekService:
        def search_records(self, _query: str) -> dict[str, Any]:
            return {"status": "not_available", "matches": []}

    class FakeAssociatedAccountsService:
        @staticmethod
        def verify_account_matches(*_args: Any) -> list[dict[str, Any]]:
            return []

    class RecordingAnalyzer:
        async def analyze_personality(
            self,
            _scraped: dict[str, Any],
            _dorking: dict[str, Any],
            _instagram: dict[str, Any],
            hashtag_analysis: dict[str, Any],
        ) -> dict[str, Any]:
            captured["hashtag_analysis"] = hashtag_analysis
            return {
                "summary": "Offline hashtag analysis complete.",
                "traits": [],
                "interests": ["cybersafe"],
                "tone": "neutral",
                "riskFlags": [],
                "primaryCategory": "Cybersecurity & Incident Response",
                "confidence": 55,
                "confidenceLabel": "moderate",
                "evidence": ["cybersafe"],
                "secondaryCategories": [],
                "crossPlatformNote": "Cross-platform hashtag evidence",
                "platformCount": 5,
            }

    async def no_audit(**_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(investigation, "ApifyActorClient", FakeApifyClient)
    monkeypatch.setattr(investigation, "InstagramService", FakeInstagramService)
    monkeypatch.setattr(investigation, "TikTokService", FakeTikTokService)
    monkeypatch.setattr(investigation, "TwitterService", FakeTwitterService)
    monkeypatch.setattr(investigation, "FacebookService", FakeFacebookService)
    monkeypatch.setattr(investigation, "DorkingService", FakeDorkingService)
    monkeypatch.setattr(investigation, "WhatsMyNameService", FakeWhatsMyNameService)
    monkeypatch.setattr(investigation, "WikidataService", FakeWikidataService)
    monkeypatch.setattr(investigation, "SignalHireService", FakeSignalHireService)
    monkeypatch.setattr(investigation, "RocketReachService", FakeRocketReachService)
    monkeypatch.setattr(investigation, "EmailVerifierService", FakeEmailVerifierService)
    monkeypatch.setattr(investigation, "TelegramService", FakeTelegramService)
    monkeypatch.setattr(investigation, "HiTekService", FakeHiTekService)
    monkeypatch.setattr(investigation, "AssociatedAccountsService", FakeAssociatedAccountsService)
    monkeypatch.setattr(investigation, "AIAnalyzer", RecordingAnalyzer)
    monkeypatch.setattr(investigation, "_record_contact_investigation_access", no_audit)

    from app.services import linkedin_apify_service

    monkeypatch.setattr(linkedin_apify_service, "LinkedInApifyService", FakeLinkedInService)

    user = AuthenticatedUser(
        username="uppolice",
        roles=("investigator", "breach_pii_viewer"),
        expires_at=datetime.now(UTC),
        csrf_token="offline-csrf",
        session_id="offline-session",
    )
    result = await investigation.run_investigation(
        InvestigationRequest(username="alice"),
        Response(),
        user,
        user,
    )

    assert result.hashtag_analysis is not None
    assert len(linkedin_post_calls) == 1
    assert linkedin_post_calls[0] == {
        "keyword": "Alice Analyst",
        "sort_type": "date_posted",
        "limit": settings.apify_linkedin_posts_limit,
        "total_posts": settings.apify_linkedin_posts_limit,
        "expected_author_profile_url": "https://www.linkedin.com/in/alice/",
    }
    assert len(shared_apify_clients) == 2
    assert shared_apify_clients[0] is shared_apify_clients[1]
    linkedin_dossier = (result.scraped_data or {})["linkedin"]
    assert [post["id"] for post in linkedin_dossier["posts"]] == [
        "linkedin-post-1"
    ]
    assert linkedin_dossier["post_count"] == 1
    assert linkedin_dossier["posts_status"] == "completed"
    assert result.provider_statuses is not None
    assert result.provider_statuses["linkedin_posts"]["status"] == "completed"
    assert result.hashtag_analysis.platforms_with_hashtags == 5
    assert result.hashtag_analysis.top_hashtags[0].tag == "cybersafe"
    assert captured["hashtag_analysis"]["platforms_with_hashtags"] == 5
    assert set(captured["hashtag_analysis"]["platforms"]) == {
        "instagram",
        "linkedin",
        "tiktok",
        "twitter",
        "facebook",
    }

    linkedin_post_failure["enabled"] = True
    failure_result = await investigation.run_investigation(
        InvestigationRequest(username="alice"),
        Response(),
        user,
        user,
    )
    assert failure_result.status == "completed"
    assert len(linkedin_post_calls) == 2
    failed_linkedin = (failure_result.scraped_data or {})["linkedin"]
    assert failed_linkedin["full_name"] == "Alice Analyst"
    assert failed_linkedin["posts"] == []
    assert failed_linkedin["posts_status"] == "error"
    assert failure_result.provider_statuses is not None
    assert failure_result.provider_statuses["linkedin"]["success"] is True
    assert failure_result.provider_statuses["linkedin_posts"]["status"] == "error"

    calls_before_non_username = len(linkedin_post_calls)
    non_username_result = await investigation.run_investigation(
        InvestigationRequest(username="Alice Analyst"),
        Response(),
        user,
        user,
    )
    assert non_username_result.status == "completed"
    assert len(linkedin_post_calls) == calls_before_non_username
    assert non_username_result.provider_statuses is not None
    assert non_username_result.provider_statuses["linkedin_posts"]["status"] == "skipped"
    assert (
        non_username_result.provider_statuses["linkedin_posts"]["error_code"]
        == "identifier_not_username"
    )
