"""Deterministic tests for discovered-contact aggregation and provenance."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import logging
from types import SimpleNamespace

from fastapi import Response
import pytest

from app.api import investigation
from app.schemas.investigation import (
    ContactDiscovery,
    ContactProvenance,
    InvestigationRequest,
)
from app.security.auth import AuthenticatedUser
from app.services.contact_aggregation_service import (
    ContactAggregationService,
    normalize_email,
    normalize_phone,
)


def test_contact_collection_normalizes_deduplicates_and_unions_provenance() -> None:
    discovery = ContactAggregationService.collect(
        target_query="alice",
        target_kind="username",
        request_email=" Alice@Example.ORG ",
        request_phone="+91 98765 43210",
        linkedin={
            "email": "alice@example.org",
            "emails": [{"email": "ALICE@example.org"}],
            "phone": "+91-98765-43210",
            "phone_numbers": [{"number": "+919876543210"}],
        },
        signalhire={
            "emails": ["alice@example.org"],
            "phones": ["+91 (98765) 43210"],
        },
        rocketreach={
            "emails": [{"email": "ALICE@EXAMPLE.ORG"}],
            "phones": [{"e164": "+919876543210"}],
        },
        facebook={
            "email": "alice@example.org",
            "phone": "98765 43210",
        },
        instagram={
            "businessEmail": "alice@example.org",
            "businessPhoneNumber": "+91 98765 43210",
        },
    )

    assert discovery.status == "completed"
    assert discovery.email_count == 1
    assert discovery.phone_count == 1

    email = discovery.emails[0]
    assert email.email == "alice@example.org"
    assert [(item.source, item.collection_method) for item in email.sources] == [
        ("request", "user_supplied"),
        ("linkedin", "public_profile"),
        ("linkedin", "public_profile"),
        ("signalhire", "enrichment_provider"),
        ("rocketreach", "enrichment_provider"),
        ("facebook", "public_profile"),
        ("instagram", "public_profile"),
    ]
    assert {item.field for item in email.sources} == {
        "email",
        "emails",
        "businessEmail",
    }

    phone = discovery.phones[0]
    assert phone.phone == "+919876543210"
    assert phone.normalized == "+919876543210"
    assert phone.e164 == "+919876543210"
    assert phone.status == "valid"
    assert phone.valid is True
    assert phone.possible is True
    assert phone.region == "IN"
    assert [item.source for item in phone.sources] == [
        "request",
        "linkedin",
        "linkedin",
        "signalhire",
        "rocketreach",
        "facebook",
        "instagram",
    ]


def test_contact_collection_uses_target_email_and_phone_as_user_supplied_sources() -> None:
    email_result = ContactAggregationService.collect(
        target_query="TARGET@Example.org",
        target_kind="email",
    )
    assert [item.email for item in email_result.emails] == ["target@example.org"]
    assert email_result.emails[0].sources[0].source == "request"
    assert email_result.emails[0].sources[0].field == "target_email"
    assert email_result.emails[0].sources[0].collection_method == "user_supplied"

    phone_result = ContactAggregationService.collect(
        target_query="+91 98765 43210",
        target_kind="phone",
    )
    assert [item.normalized for item in phone_result.phones] == ["+919876543210"]
    assert phone_result.phones[0].sources[0].field == "target_phone"


def test_provider_national_phone_does_not_invent_indian_country_code() -> None:
    discovery = ContactAggregationService.collect(
        target_query="alice",
        target_kind="username",
        linkedin={"success": True, "phone": "2025550123"},
    )

    assert discovery.phone_count == 1
    phone = discovery.phones[0]
    assert phone.phone == "2025550123"
    assert phone.normalized == "2025550123"
    assert phone.e164 is None
    assert phone.status == "unverified"
    assert phone.valid is None
    assert phone.possible is None
    assert phone.region is None


def test_contact_provenance_uses_actual_provider_and_confirmed_platform_only() -> None:
    discovery = ContactAggregationService.collect(
        target_query="alice@example.org",
        target_kind="email",
        signalhire={
            "success": True,
            "provider": "signalhire",
            "emails": ["alice@example.org"],
        },
        instagram={
            "success": True,
            "source": "flashapi_profile+apify_posts",
            "profile_source": "flashapi",
            "business_email": "public@example.org",
            "bio": "Email the public desk at bio-contact@example.org",
        },
    )

    signalhire_source = next(
        source
        for source in discovery.emails[0].sources
        if source.source == "signalhire"
    )
    assert signalhire_source.provider == "signalhire"
    assert signalhire_source.platform is None

    instagram_email = next(
        item for item in discovery.emails if item.email == "public@example.org"
    )
    assert instagram_email.sources[0].source == "instagram"
    assert instagram_email.sources[0].provider == "flashapi"
    assert instagram_email.sources[0].platform == "instagram"
    instagram_bio_email = next(
        item for item in discovery.emails if item.email == "bio-contact@example.org"
    )
    assert instagram_bio_email.sources[0].provider == "flashapi"
    assert instagram_bio_email.sources[0].collection_method == "public_profile_text"

    linked_discovery = ContactAggregationService.collect(
        target_query="alice@example.org",
        target_kind="email",
        signalhire={
            "success": True,
            "emails": ["alice@example.org"],
            "url": "https://www.linkedin.com/in/alice-analyst/",
        },
    )
    assert next(
        source
        for source in linked_discovery.emails[0].sources
        if source.source == "signalhire"
    ).platform == "linkedin"


def test_user_phone_country_context_deduplicates_provider_national_form() -> None:
    discovery = ContactAggregationService.collect(
        target_query="alice",
        target_kind="username",
        request_phone="98765 43210",
        facebook={"success": True, "phone": "98765 43210"},
    )

    assert discovery.phone_count == 1
    assert discovery.phones[0].e164 == "+919876543210"
    assert [source.source for source in discovery.phones[0].sources] == [
        "request",
        "facebook",
    ]


def test_failed_provider_payload_cannot_contribute_stale_contacts() -> None:
    discovery = ContactAggregationService.collect(
        target_query="alice",
        target_kind="username",
        linkedin={
            "success": False,
            "status": "error",
            "email": "stale-linkedin@example.org",
            "phone": "+12025550123",
            "bio": "stale-bio@example.org +1 202 555 0199",
        },
        signalhire={
            "success": False,
            "status": "not_found",
            "emails": ["stale-signalhire@example.org"],
            "phones": ["+12025550124"],
        },
    )

    assert discovery == ContactDiscovery()


def test_non_phone_contact_value_and_profile_date_are_not_phone_evidence() -> None:
    discovery = ContactAggregationService.collect(
        target_query="alice",
        target_kind="username",
        linkedin={
            "success": True,
            "contacts": [
                {
                    "type": "linkedin",
                    "value": "https://linkedin.com/in/person2025550123",
                },
                {"type": "email", "value": "person2025550123@example.org"},
            ],
            "about": "Established 2020-01-01 12 years ago",
        },
    )

    assert [item.email for item in discovery.emails] == [
        "person2025550123@example.org"
    ]
    assert discovery.phones == []


def test_profile_text_requires_phone_context_for_national_digit_sequences() -> None:
    discovery = ContactAggregationService.collect(
        target_query="alice",
        target_kind="username",
        linkedin={
            "success": True,
            "about": "Employee ID 1234567890. Call: 98765 43210.",
        },
    )

    assert discovery.phone_count == 1
    assert discovery.phones[0].normalized == "9876543210"
    assert discovery.phones[0].e164 is None
    assert discovery.phones[0].status == "unverified"


def test_typed_generic_contact_values_are_routed_to_the_declared_kind() -> None:
    discovery = ContactAggregationService.collect(
        target_query="alice",
        target_kind="username",
        signalhire={
            "success": True,
            "contacts": [
                {"type": "email", "value": "typed@example.org"},
                {"type": "mobile", "value": "+1 202 555 0123"},
            ],
        },
    )

    assert [item.email for item in discovery.emails] == ["typed@example.org"]
    assert [item.e164 for item in discovery.phones] == ["+12025550123"]


def test_explicit_partial_provider_payload_can_contribute_contacts() -> None:
    discovery = ContactAggregationService.collect(
        target_query="alice",
        target_kind="username",
        rocketreach={
            "success": False,
            "status": "partial",
            "email": "partial@example.org",
        },
    )

    assert [item.email for item in discovery.emails] == ["partial@example.org"]


def test_key_diagnostics_reports_signalhire_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(investigation.settings, "signalhire_api_key", "test-key")

    response = Response()
    diagnostics = asyncio.run(
        investigation.get_keys_diagnostics(response, refresh_apify=False)
    )

    assert diagnostics["signalhire"] == {"configured": True, "status": "Active"}
    assert response.headers["cache-control"] == "no-store, private"


@pytest.mark.parametrize(
    ("value", "expected_kind"),
    [
        ("alice@example.org", "email"),
        ("+91 98765 43210", "phone"),
        ("john.doe", "domain"),
        ("@john.doe", "username"),
        ("John Doe", "name"),
        ("example.com", "domain"),
        ("sub.example.co.in", "domain"),
        ("https://sub.example.tech/path", "domain"),
        ("example.tech", "domain"),
        ("example.online", "domain"),
        ("example.xn--p1ai", "domain"),
        ("192.168.1.1", "domain"),
        ("2001:db8::1", "domain"),
    ],
)
def test_backend_input_classification_distinguishes_dotted_handles_from_domains(
    value: str,
    expected_kind: str,
) -> None:
    assert investigation.classify_input(value) == expected_kind


def test_contact_collection_ignores_malformed_containers_and_unapproved_nested_data() -> None:
    service = ContactAggregationService()
    provenance = ContactProvenance(
        source="fixture",
        field="profile",
        collection_method="public_profile",
        platform="fixture",
    )

    # Public helpers reject malformed and overlong candidates without raising.
    assert normalize_email("not-an-email") is None
    assert normalize_email(f"{'x' * 65}@example.org") is None
    assert normalize_email(f"x@{'d' * 256}.org") is None
    assert normalize_phone("123") is None
    assert normalize_phone("9" * 65) is None

    service.add_payload(
        {
            "email": [
                None,
                12345,
                {"unexpected": "nested-secret@example.org"},
                "Public Contact <Allowed@Example.org>",
            ],
            "phones": [
                None,
                {"unexpected": "+919111111111"},
                "+91 98765 43210",
            ],
            "raw_data": {
                "email": "raw-secret@example.org",
                "phone": "+919111111111",
            },
            "posts": [{"email": "other-person@example.org"}],
        },
        source="fixture",
        collection_method="public_profile",
        platform="fixture",
        provider=None,
    )
    # Direct add methods are equally defensive about provider-controlled text.
    service.add_email("<script>alert(1)</script>", provenance)
    service.add_phone("<img src=x onerror=alert(1)>", provenance)

    result = service.result()
    assert [item.email for item in result.emails] == ["allowed@example.org"]
    assert [item.normalized for item in result.phones] == ["+919876543210"]
    serialized = result.model_dump(mode="json")
    assert "raw-secret@example.org" not in str(serialized)
    assert "other-person@example.org" not in str(serialized)
    assert "+919111111111" not in str(serialized)
    assert "<script>" not in str(serialized)
    assert "<img" not in str(serialized)


def test_contact_collection_caps_provider_controlled_values_with_stable_order() -> None:
    service = ContactAggregationService()
    service.add_payload(
        {
            "emails": [f"person{index}@example.org" for index in range(75)],
            "phones": [f"+1202555{index:04d}" for index in range(75)],
        },
        source="fixture",
        collection_method="enrichment_provider",
        platform=None,
        provider="fixture",
    )

    result = service.result()
    assert result.email_count == service.MAX_EMAILS
    assert result.phone_count == service.MAX_PHONES
    assert result.emails[0].email == "person0@example.org"
    assert result.emails[-1].email == "person49@example.org"
    assert result.phones[0].normalized == "+12025550000"
    assert result.phones[-1].normalized == "+12025550049"


def test_generated_guesses_stay_separate_and_verification_updates_observed_once() -> None:
    discovery = ContactAggregationService.collect(
        target_query="alice",
        target_kind="username",
        linkedin={
            "emails": [
                "Alice@Example.org",
                " alice@example.org ",
                {"email": "ALICE@example.org"},
            ]
        },
        signalhire={"emails": ["alice@example.org"]},
        rocketreach={"emails": ["ALICE@EXAMPLE.ORG"]},
    )

    # A caller scheduling verification from this canonical list makes exactly
    # one paid call, even though five provider values represented the address.
    verification_calls = [item.email for item in discovery.emails]
    assert verification_calls == ["alice@example.org"]
    assert len(verification_calls) <= ContactAggregationService.MAX_EMAIL_VERIFICATIONS

    ContactAggregationService.apply_email_verifications(
        discovery,
        [
            {
                "email": "ALICE@EXAMPLE.ORG",
                "status": "verified",
                "deliverable": True,
                "reason": "Confirmed by Hunter.io verification API",
                "score": 97,
            },
            {
                "email": "not-collected@example.org",
                "status": "verified",
                "deliverable": True,
            },
        ],
    )
    observed = discovery.emails[0]
    assert observed.status == "verified"
    assert observed.deliverable is True
    assert observed.score == 97
    assert observed.verification_provider == "hunter"
    assert [item.email for item in discovery.emails] == ["alice@example.org"]

    ContactAggregationService.add_email_guesses(
        discovery,
        [
            {"email": "alice@example.org", "status": "likely"},
            {
                "email": "Alice.Guess@Gmail.com",
                "status": "likely",
                "deliverable": True,
                "reason": "Generated pattern; not independently observed",
            },
            {"email": "not-an-email", "status": "likely"},
        ],
    )
    assert discovery.email_count == 1
    assert discovery.email_guess_count == 1
    assert [item.email for item in discovery.email_guesses] == [
        "alice.guess@gmail.com"
    ]
    assert discovery.email_guesses[0].sources[0].collection_method == "generated_pattern"
    assert discovery.email_guesses[0].deliverable is None
    assert "mailbox existence was not verified" in (
        discovery.email_guesses[0].reason or ""
    )


def test_investigation_verifies_each_canonical_email_once_and_returns_contacts(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Exercise collector -> dedupe -> verification -> CTI -> response offline."""

    email_sentinel = "duplicate@example.org"
    phone_sentinel = "+919876543210"
    verifier_calls: list[str] = []
    cti_calls: list[list[str]] = []
    audit_calls: list[dict[str, object]] = []
    signalhire_calls: list[str] = []
    rocketreach_calls: list[str] = []
    monkeypatch.setattr(investigation.settings, "hunter_api_key", "hunter-test-key")

    class FakeCapacity:
        def as_dict(self) -> dict[str, object]:
            return {"state": "available", "configured": True}

    class FakeApifyClient:
        async def check_account_capacity(self) -> FakeCapacity:
            return FakeCapacity()

    def async_service(method: str, result: object) -> SimpleNamespace:
        async def run(*_args: object, **_kwargs: object) -> object:
            return result

        return SimpleNamespace(**{method: run})

    linkedin = {
        "success": True,
        "platform": "linkedin",
        "profile_url": "https://www.linkedin.com/in/alice",
        "email": " Duplicate@Example.ORG ",
        "phone": "+91 98765 43210",
        "full_name": "Alice Analyst",
    }
    facebook = {
        "success": True,
        "platform": "facebook",
        "email": email_sentinel,
        "phone": "9876543210",
    }
    instagram = {
        "success": True,
        "platform": "instagram",
        "businessEmail": email_sentinel,
        "businessPhoneNumber": "+91 (98765) 43210",
        "posts": [],
    }

    monkeypatch.setattr(investigation, "ApifyActorClient", FakeApifyClient)
    monkeypatch.setattr(
        investigation,
        "InstagramService",
        lambda **_kwargs: async_service("fetch_profile_and_posts", instagram),
    )
    monkeypatch.setattr(
        investigation,
        "TikTokService",
        lambda **_kwargs: async_service(
            "fetch_profile_and_videos",
            {"success": False, "platform": "tiktok"},
        ),
    )
    monkeypatch.setattr(
        investigation,
        "TwitterService",
        lambda **_kwargs: async_service(
            "fetch_profile_and_tweets",
            {"success": False, "platform": "twitter"},
        ),
    )
    monkeypatch.setattr(
        investigation,
        "FacebookService",
        lambda **_kwargs: async_service("fetch_page_or_profile", facebook),
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
            {"status": "success", "hits": [], "hits_count": 0, "scanned": 0},
        ),
    )
    monkeypatch.setattr(
        investigation,
        "WikidataService",
        lambda: async_service("search_and_get_profile", {"found": False}),
    )
    class FakeSignalHire:
        async def search_candidate(self, identifier: str) -> dict[str, object]:
            signalhire_calls.append(identifier)
            return {"success": False, "emails": [], "phones": []}

    class FakeRocketReach:
        async def lookup_by_linkedin_url(self, url: str) -> dict[str, object]:
            rocketreach_calls.append(url)
            return {"success": False, "emails": [], "phones": []}

    monkeypatch.setattr(investigation, "SignalHireService", FakeSignalHire)
    monkeypatch.setattr(investigation, "RocketReachService", FakeRocketReach)

    class FakeVerifier:
        @staticmethod
        def process_pattern_guesses(
            _username: str,
            _full_name: str | None,
        ) -> list[dict[str, object]]:
            return [
                {"email": email_sentinel, "status": "likely"},
                {
                    "email": "alice.guess@gmail.com",
                    "status": "likely",
                    "deliverable": True,
                },
            ]

        @staticmethod
        async def verify_with_hunter(email: str) -> dict[str, object]:
            verifier_calls.append(email)
            return {
                "email": email,
                "status": "verified",
                "deliverable": True,
                "reason": "Confirmed by Hunter.io verification API",
                "verification_provider": "hunter",
            }

    monkeypatch.setattr(investigation, "EmailVerifierService", FakeVerifier)

    class FakeTelegram:
        async def search_cti_breaches(self, queries: list[str]) -> dict[str, object]:
            cti_calls.append(queries)
            return {
                "status": "no_results",
                "results": [],
                "total_records": 0,
                "databases": [],
            }

    monkeypatch.setattr(investigation, "TelegramService", FakeTelegram)
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
    monkeypatch.setattr(
        investigation,
        "AIAnalyzer",
        lambda: async_service(
            "analyze_personality",
            {
                "summary": "Offline contact test",
                "traits": [],
                "interests": [],
                "tone": "neutral",
                "riskFlags": [],
                "primaryCategory": "Unable to Classify",
                "confidence": 0,
                "confidenceLabel": "insufficient",
                "evidence": [],
                "secondaryCategories": [],
                "crossPlatformNote": None,
                "platformCount": 0,
            },
        ),
    )

    async def fake_audit(**kwargs: object) -> None:
        audit_calls.append(kwargs)

    monkeypatch.setattr(investigation, "_record_contact_investigation_access", fake_audit)

    from app.services import linkedin_apify_service

    monkeypatch.setattr(
        linkedin_apify_service,
        "LinkedInApifyService",
        lambda **_kwargs: async_service("get_profile", linkedin),
    )

    user = AuthenticatedUser(
        username="uppolice",
        roles=("investigator", "breach_pii_viewer"),
        expires_at=datetime.now(UTC),
        csrf_token="offline-csrf",
        session_id="offline-session",
    )
    caplog.set_level(logging.INFO)

    completed_runs: list[tuple[object, Response]] = []
    for _ in range(2):
        run_response = Response()
        run_result = asyncio.run(
            investigation.run_investigation(
                InvestigationRequest(
                    username="alice",
                    email=" Duplicate@Example.ORG ",
                    phone_number="+91 98765 43210",
                    cache_mode="use",
                ),
                run_response,
                user,
                user,
            )
        )
        completed_runs.append((run_result, run_response))
    result, response = completed_runs[-1]

    assert verifier_calls == [email_sentinel]
    assert cti_calls == [
        [email_sentinel, phone_sentinel],
        [email_sentinel, phone_sentinel],
    ]
    assert signalhire_calls == []
    assert rocketreach_calls == []
    assert result.contact_discovery is not None
    assert result.contact_discovery.email_count == 1
    assert result.contact_discovery.phone_count == 1
    assert result.contact_discovery.email_guess_count == 1
    assert [item.email for item in result.contact_discovery.emails] == [email_sentinel]
    assert [item.normalized for item in result.contact_discovery.phones] == [
        phone_sentinel
    ]
    assert result.contact_discovery.emails[0].status == "verified"
    assert result.contact_discovery.emails[0].verification_provider == "hunter"
    assert {item.source for item in result.contact_discovery.emails[0].sources} == {
        "request",
        "linkedin",
        "facebook",
        "instagram",
    }
    assert result.consolidated_identity is not None
    assert result.consolidated_identity.emails == result.contact_discovery.emails
    assert result.consolidated_identity.phones == result.contact_discovery.phones
    assert result.consolidated_identity.email_guesses == result.contact_discovery.email_guesses
    assert response.headers["cache-control"] == "no-store, private"
    assert response.headers["pragma"] == "no-cache"
    assert [entry["outcome"] for entry in audit_calls] == [
        "requested",
        "success",
        "requested",
        "success",
    ]
    assert set(audit_calls[-1]["field_labels"]) >= {"email", "phone"}  # type: ignore[arg-type]

    logs = caplog.text
    assert "event=contact_discovery_completed" in logs
    assert "email_count=1" in logs
    assert "phone_count=1" in logs
    assert "event=contact_verification_cache" in logs
    assert "outcome=hit" in logs
    assert email_sentinel not in logs
    assert phone_sentinel not in logs


@pytest.mark.parametrize(
    (
        "target",
        "request_email",
        "request_phone",
        "linkedin_result",
        "facebook_result",
        "instagram_result",
        "expected_signalhire",
        "expected_rocketreach",
        "expected_verifications",
        "expected_cti_queries",
        "expected_contact_counts",
    ),
    [
        pytest.param(
            "alice",
            None,
            None,
            {
                "success": True,
                "profile_url": "https://www.linkedin.com/in/alice",
                "email": "public@example.org",
                "phone": "+91 98765 43210",
            },
            {"success": False},
            {"success": False, "posts": []},
            [],
            [],
            ["public@example.org"],
            [["public@example.org", "+919876543210"]],
            (1, 1),
            id="confirmed-linkedin-email-and-phone-skip-enricher",
        ),
        pytest.param(
            "Exact@Example.org",
            None,
            None,
            {"success": False},
            {"success": False},
            {"success": False, "posts": []},
            ["exact@example.org"],
            [],
            ["exact@example.org"],
            [["exact@example.org"]],
            (1, 0),
            id="exact-email-routes-signalhire-only",
        ),
        pytest.param(
            "+1 (202) 555-0123",
            None,
            None,
            {"success": False},
            {"success": False},
            {"success": False, "posts": []},
            ["+12025550123"],
            [],
            [],
            [["+12025550123"]],
            (0, 1),
            id="exact-phone-routes-signalhire-only",
        ),
        pytest.param(
            "98765 43210",
            None,
            None,
            {"success": False},
            {"success": False},
            {"success": False, "posts": []},
            ["+919876543210"],
            [],
            [],
            [["+919876543210"]],
            (0, 1),
            id="indian-national-phone-uses-one-canonical-external-identifier",
        ),
        pytest.param(
            "123",
            None,
            None,
            {"success": False},
            {"success": False},
            {"success": False, "posts": []},
            [],
            [],
            [],
            [],
            (0, 0),
            id="malformed-phone-shaped-input-skips-paid-collectors",
        ),
        pytest.param(
            "192.168.1.1",
            None,
            None,
            {"success": False},
            {"success": False},
            {"success": False, "posts": []},
            [],
            [],
            [],
            [["192.168.1.1"]],
            (0, 0),
            id="ipv4-target-is-not-treated-as-phone-or-username",
        ),
        pytest.param(
            "alice",
            None,
            "+91 98765 43210",
            {
                "success": True,
                "profile_url": "https://www.linkedin.com/in/alice",
            },
            {"success": False},
            {"success": False, "posts": []},
            ["+919876543210"],
            [],
            [],
            [["+919876543210"]],
            (0, 1),
            id="request-phone-prefers-signalhire-over-linkedin",
        ),
        pytest.param(
            "alice",
            None,
            None,
            {
                "success": True,
                "profile_url": "https://linkedin.com/in/Alice.Analyst?trk=public",
                "phone": "2025550123",
            },
            {"success": False},
            {"success": False, "posts": []},
            [],
            ["https://www.linkedin.com/in/Alice.Analyst/"],
            [],
            [["alice"]],
            (0, 1),
            id="confirmed-linkedin-routes-rocketreach-only",
        ),
        pytest.param(
            "alice",
            None,
            None,
            {
                "success": True,
                "profile_url": "https://www.linkedin.com/company/alice",
            },
            {"success": False},
            {"success": False, "posts": []},
            [],
            [],
            [],
            [["alice"]],
            (0, 0),
            id="non-profile-linkedin-url-skips-both",
        ),
        pytest.param(
            "alice",
            None,
            None,
            {"success": False},
            {"success": False},
            {
                "success": True,
                "posts": [],
                "bio": "Public desk bio-only@example.org or +91 98765 43210",
            },
            [],
            [],
            [],
            [["alice"]],
            (1, 1),
            id="bio-only-contacts-display-without-verification-or-cti",
        ),
        pytest.param(
            "@john.doe",
            None,
            None,
            {"success": False},
            {"success": False},
            {"success": False, "posts": []},
            [],
            [],
            [],
            [["john.doe"]],
            (0, 0),
            id="explicit-dotted-username-runs-username-collectors",
        ),
        pytest.param(
            "alice",
            "seed@example.org",
            None,
            {"success": False},
            {"success": True, "phone": "+1 202 555 0123"},
            {
                "success": True,
                "posts": [],
                "business_email": "public@example.org",
            },
            ["seed@example.org"],
            [],
            ["seed@example.org", "public@example.org"],
            [["seed@example.org", "+12025550123", "public@example.org"]],
            (2, 1),
            id="exact-email-is-not-suppressed-by-unrelated-social-contacts",
        ),
        pytest.param(
            "alice",
            None,
            None,
            {
                "success": True,
                "profile_url": "https://www.linkedin.com/in/alice",
            },
            {"success": True, "phone": "+1 202 555 0123"},
            {
                "success": True,
                "posts": [],
                "business_email": "public@example.org",
            },
            [],
            ["https://www.linkedin.com/in/alice/"],
            ["public@example.org"],
            [["public@example.org", "+12025550123"]],
            (1, 1),
            id="linkedin-enrichment-is-not-suppressed-by-other-platform-contacts",
        ),
    ],
)
def test_contact_enrichment_routing_makes_at_most_one_supported_provider_call(
    monkeypatch: pytest.MonkeyPatch,
    target: str,
    request_email: str | None,
    request_phone: str | None,
    linkedin_result: dict[str, object],
    facebook_result: dict[str, object],
    instagram_result: dict[str, object],
    expected_signalhire: list[str],
    expected_rocketreach: list[str],
    expected_verifications: list[str],
    expected_cti_queries: list[list[str]],
    expected_contact_counts: tuple[int, int],
) -> None:
    signalhire_calls: list[str] = []
    rocketreach_calls: list[str] = []
    verifier_calls: list[str] = []
    cti_calls: list[list[str]] = []
    username_collector_calls: list[str] = []

    class FakeCapacity:
        def as_dict(self) -> dict[str, object]:
            return {"state": "available", "configured": True}

    class FakeApifyClient:
        async def check_account_capacity(self) -> FakeCapacity:
            username_collector_calls.append("apify_capacity")
            return FakeCapacity()

    def async_service(
        method: str,
        result: object,
        collector: str | None = None,
    ) -> SimpleNamespace:
        async def run(*_args: object, **_kwargs: object) -> object:
            if collector:
                username_collector_calls.append(collector)
            return result

        return SimpleNamespace(**{method: run})

    monkeypatch.setattr(investigation.settings, "signalhire_api_key", "signalhire-test-key")
    monkeypatch.setattr(investigation.settings, "rocketreach_api_key", "rocketreach-test-key")
    monkeypatch.setattr(investigation, "ApifyActorClient", FakeApifyClient)
    monkeypatch.setattr(
        investigation,
        "InstagramService",
        lambda **_kwargs: async_service(
            "fetch_profile_and_posts",
            instagram_result,
            "instagram",
        ),
    )
    monkeypatch.setattr(
        investigation,
        "TikTokService",
        lambda **_kwargs: async_service(
            "fetch_profile_and_videos",
            {"success": False, "platform": "tiktok"},
            "tiktok",
        ),
    )
    monkeypatch.setattr(
        investigation,
        "TwitterService",
        lambda **_kwargs: async_service(
            "fetch_profile_and_tweets",
            {"success": False, "platform": "twitter"},
            "twitter",
        ),
    )
    monkeypatch.setattr(
        investigation,
        "FacebookService",
        lambda **_kwargs: async_service(
            "fetch_page_or_profile",
            facebook_result,
            "facebook",
        ),
    )
    monkeypatch.setattr(
        investigation,
        "DorkingService",
        lambda: async_service(
            "run_dorks",
            {"status": "completed", "results": [], "queries_run": 0, "results_count": 0},
        ),
    )
    monkeypatch.setattr(
        investigation,
        "WhatsMyNameService",
        lambda: async_service(
            "probe_username",
            {"status": "success", "hits": [], "hits_count": 0, "scanned": 0},
            "whatsmyname",
        ),
    )
    monkeypatch.setattr(
        investigation,
        "WikidataService",
        lambda: async_service(
            "search_and_get_profile",
            {"found": False},
            "wikidata",
        ),
    )

    class FakeSignalHire:
        async def search_candidate(self, identifier: str) -> dict[str, object]:
            signalhire_calls.append(identifier)
            if (
                investigation.classify_input(target) in {"email", "phone"}
                or request_email is not None
                or request_phone is not None
            ):
                return {
                    "success": True,
                    "status": "success",
                    "provider": "signalhire",
                    "configured": True,
                    "full_name": "SignalHire Exact Match",
                    "headline": "Incident Response Analyst",
                    "location": "Lucknow",
                    "emails": [identifier] if "@" in identifier else [],
                    "phones": [identifier] if "@" not in identifier else [],
                    "url": (
                        "https://www.linkedin.com/in/a-different-profile/"
                        if request_phone is not None
                        else None
                    ),
                    "credits_remaining": 42,
                }
            return {
                "success": False,
                "status": "error",
                "emails": [],
                "phones": [],
            }

    class FakeRocketReach:
        async def lookup_by_linkedin_url(self, url: str) -> dict[str, object]:
            rocketreach_calls.append(url)
            return {
                "success": False,
                "status": "error",
                "emails": [],
                "phones": [],
            }

    monkeypatch.setattr(investigation, "SignalHireService", FakeSignalHire)
    monkeypatch.setattr(investigation, "RocketReachService", FakeRocketReach)

    class FakeVerifier:
        @staticmethod
        def process_pattern_guesses(
            _username: str,
            _full_name: str | None,
        ) -> list[dict[str, object]]:
            return []

        @staticmethod
        async def verify_with_hunter(email: str) -> dict[str, object]:
            verifier_calls.append(email)
            return {"email": email, "status": "unknown", "deliverable": None}

    monkeypatch.setattr(investigation, "EmailVerifierService", FakeVerifier)

    class FakeTelegram:
        async def search_cti_breaches(self, queries: list[str]) -> dict[str, object]:
            cti_calls.append(queries)
            return {
                "status": "no_results",
                "results": [],
                "total_records": 0,
                "databases": [],
            }

    monkeypatch.setattr(investigation, "TelegramService", FakeTelegram)
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
    monkeypatch.setattr(
        investigation,
        "AIAnalyzer",
        lambda: async_service(
            "analyze_personality",
            {
                "summary": "Offline routing test",
                "traits": [],
                "interests": [],
                "tone": "neutral",
                "riskFlags": [],
                "primaryCategory": "Unable to Classify",
                "confidence": 0,
                "confidenceLabel": "insufficient",
                "evidence": [],
                "secondaryCategories": [],
                "crossPlatformNote": None,
                "platformCount": 0,
            },
        ),
    )

    async def no_audit(**_kwargs: object) -> None:
        return None

    monkeypatch.setattr(investigation, "_record_contact_investigation_access", no_audit)

    from app.services import linkedin_apify_service

    monkeypatch.setattr(
        linkedin_apify_service,
        "LinkedInApifyService",
        lambda **_kwargs: async_service(
            "get_profile",
            linkedin_result,
            "linkedin",
        ),
    )

    user = AuthenticatedUser(
        username="uppolice",
        roles=("investigator", "breach_pii_viewer"),
        expires_at=datetime.now(UTC),
        csrf_token="offline-csrf",
        session_id="offline-session",
    )
    result = asyncio.run(
        investigation.run_investigation(
            InvestigationRequest(
                username=target,
                email=request_email,
                phone_number=request_phone,
            ),
            Response(),
            user,
            user,
        )
    )

    assert result.status == "completed"
    assert signalhire_calls == expected_signalhire
    assert rocketreach_calls == expected_rocketreach
    assert len(signalhire_calls) + len(rocketreach_calls) <= 1
    target_kind = investigation.classify_input(target)
    if target_kind != "username":
        assert username_collector_calls == []
        assert result.wmn_results is not None
        assert result.wmn_results.get("error_code") == "identifier_not_username"
        assert result.wmn_results.get("hits") == []
        assert "linkedin" not in (result.scraped_data or {})
        assert result.consolidated_identity is not None
        if target_kind in {"email", "phone"}:
            if expected_signalhire:
                assert result.consolidated_identity.likely_name == "SignalHire Exact Match"
                assert result.consolidated_identity.location == "Lucknow"
                assert result.consolidated_identity.profession == "Incident Response Analyst"
                assert result.provider_statuses is not None
                assert result.provider_statuses["signalhire"]["credits_remaining"] == 42
            else:
                assert result.consolidated_identity.likely_name is None
    else:
        assert set(username_collector_calls) == {
            "apify_capacity",
            "instagram",
            "tiktok",
            "twitter",
            "whatsmyname",
            "wikidata",
            "facebook",
            "linkedin",
        }
    if request_phone is not None and linkedin_result.get("success") is True:
        linkedin_dossier = (result.scraped_data or {}).get("linkedin") or {}
        assert linkedin_dossier.get("phone_numbers") == []
    assert verifier_calls == expected_verifications
    assert cti_calls == expected_cti_queries
    assert result.contact_discovery is not None
    assert (
        result.contact_discovery.email_count,
        result.contact_discovery.phone_count,
    ) == expected_contact_counts
