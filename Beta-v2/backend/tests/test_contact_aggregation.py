"""Offline tests for deterministic Target Scan contact aggregation."""

from __future__ import annotations

from app.schemas.investigation import ContactDiscovery
from app.services.contact_aggregation_service import ContactAggregationService


def test_collects_deduplicates_and_attributes_explicit_contacts() -> None:
    discovery = ContactAggregationService.collect(
        target_query="Lead@Example.COM",
        target_kind="email",
        request_email="lead@example.com",
        request_phone="98765 43210",
        linkedin={
            "emails": ["LEAD@example.com", "linkedin@example.org"],
            "phone": "+91 98765 43210",
            "bio": "Public desk: bio-linkedin@example.net",
            "posts": [{"text": "ignored-post@example.net +91 90000 00000"}],
        },
        signalhire={
            "emails": ["signal@example.org"],
            "phones": ["+91 91234 56789"],
        },
        rocketreach={
            "emails": ["linkedin@example.org", "rocket@example.org"],
            "phones": ["+91 98 7654 3210"],
        },
        facebook={
            "email": "facebook@example.org",
            "phone": "+91 99887 76655",
            "description": "Alternate: public-fb@example.net or +91 91234 56789",
            "posts": [{"text": "ignored-facebook-post@example.net"}],
        },
        instagram={
            "business_email": "ig-business@example.org",
            "business_phone_number": "+91 99887 76655",
            "bio": "IG desk ig-bio@example.net",
            "posts": [{"caption": "ignored-instagram-post@example.net"}],
        },
    )

    assert discovery.status == "completed"
    assert [item.email for item in discovery.emails] == [
        "lead@example.com",
        "linkedin@example.org",
        "bio-linkedin@example.net",
        "signal@example.org",
        "rocket@example.org",
        "facebook@example.org",
        "public-fb@example.net",
        "ig-business@example.org",
        "ig-bio@example.net",
    ]
    assert "ignored-post@example.net" not in {item.email for item in discovery.emails}
    assert "ignored-facebook-post@example.net" not in {item.email for item in discovery.emails}
    assert "ignored-instagram-post@example.net" not in {item.email for item in discovery.emails}
    assert discovery.email_count == 9

    lead_sources = discovery.emails[0].sources
    assert [(source.source, source.field) for source in lead_sources] == [
        ("request", "email"),
        ("request", "target_email"),
        ("linkedin", "emails"),
    ]
    bio_source = next(item for item in discovery.emails if item.email == "ig-bio@example.net")
    assert bio_source.sources[0].collection_method == "public_profile_text"
    assert bio_source.sources[0].field == "bio"

    assert [item.e164 for item in discovery.phones] == [
        "+919876543210",
        "+919123456789",
        "+919988776655",
    ]
    assert discovery.phone_count == 3
    first_phone_sources = {(source.source, source.field) for source in discovery.phones[0].sources}
    assert first_phone_sources == {
        ("request", "phone"),
        ("linkedin", "phone"),
        ("rocketreach", "phones"),
    }


def test_guesses_stay_separate_and_verification_preserves_provenance() -> None:
    discovery = ContactAggregationService.collect(
        target_query="alice",
        target_kind="username",
        linkedin={"email": "Alice@Example.com"},
    )
    original_sources = list(discovery.emails[0].sources)

    ContactAggregationService.add_email_guesses(
        discovery,
        [
            {"email": "alice@example.com", "status": "likely"},
            {
                "email": "alice.guess@gmail.com",
                "status": "likely",
                "deliverable": True,
                "reason": "Generated pattern; domain resolves",
            },
            {"email": "not-an-email", "status": "invalid"},
        ],
    )
    ContactAggregationService.apply_email_verifications(
        discovery,
        [
            {
                "email": "ALICE@example.com",
                "status": "verified",
                "deliverable": True,
                "reason": "Hunter.io verification: valid",
                "score": 98,
            }
        ],
    )

    assert [item.email for item in discovery.emails] == ["alice@example.com"]
    assert discovery.emails[0].status == "verified"
    assert discovery.emails[0].verification_provider == "hunter"
    assert discovery.emails[0].sources == original_sources
    assert [item.email for item in discovery.email_guesses] == ["alice.guess@gmail.com"]
    assert discovery.email_guess_count == 1
    assert discovery.email_guesses[0].sources[0].collection_method == "generated_pattern"


def test_empty_and_malformed_values_do_not_create_contacts() -> None:
    discovery = ContactAggregationService.collect(
        target_query="alice",
        target_kind="username",
        linkedin={"emails": ["bad", "two@@example.com"], "phones": ["123", "abc"]},
        instagram={"bio": "No contact information here; post count 12345."},
    )

    assert discovery == ContactDiscovery()


def test_tiktok_and_x_profile_contacts_are_collected_but_content_is_not_mined() -> None:
    discovery = ContactAggregationService.collect(
        target_query="alice",
        target_kind="username",
        tiktok={
            "bio": "Public desk: tiktok@example.org, +91 98765 43210",
            "videos": [{"description": "ignored-video@example.org +91 90000 00000"}],
        },
        twitter={
            "description": "Press: x-profile@example.org",
            "tweets": [{"text": "ignored-tweet@example.org +91 91111 11111"}],
        },
    )

    assert [item.email for item in discovery.emails] == [
        "tiktok@example.org",
        "x-profile@example.org",
    ]
    assert [item.e164 for item in discovery.phones] == ["+919876543210"]
    assert {item.sources[0].source for item in discovery.emails} == {
        "tiktok",
        "twitter",
    }
    serialized = str(discovery.model_dump(mode="json"))
    assert "ignored-video@example.org" not in serialized
    assert "ignored-tweet@example.org" not in serialized
    assert "+919000000000" not in serialized
    assert "+919111111111" not in serialized
