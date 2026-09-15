"""Offline tests for the bounded YouTube Data API v3 collector."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from app.config import Settings
from app.services.youtube_service import YouTubeService


def _channel_payload(*, uploads: str | None = "UU-channel") -> dict[str, Any]:
    related_playlists = {"uploads": uploads} if uploads else {}
    return {
        "items": [
            {
                "id": "UC-channel",
                "snippet": {
                    "title": "Alice Example",
                    "description": "Public channel about #OSINT",
                    "customUrl": "@Alice",
                    "publishedAt": "2020-01-02T03:04:05Z",
                    "country": "IN",
                    "thumbnails": {
                        "default": {"url": "https://images.example/small.jpg"},
                        "high": {"url": "https://images.example/high.jpg"},
                    },
                },
                "statistics": {
                    "subscriberCount": "1200",
                    "hiddenSubscriberCount": False,
                    "viewCount": "55000",
                    "videoCount": "42",
                },
                "contentDetails": {"relatedPlaylists": related_playlists},
            }
        ]
    }


def _playlist_payload() -> dict[str, Any]:
    return {
        "items": [
            {
                "contentDetails": {
                    "videoId": "video-1",
                    "videoPublishedAt": "2026-01-01T00:00:00Z",
                },
                "snippet": {
                    "title": "First #CyberSafe update",
                    "description": "Learn #OSINT safely",
                    "videoOwnerChannelId": "UC-channel",
                    "videoOwnerChannelTitle": "Alice Example",
                    "thumbnails": {
                        "medium": {"url": "https://images.example/video.jpg"}
                    },
                },
            },
            {"snippet": {"title": "Malformed row without a video id"}},
        ]
    }


def _video_payload() -> dict[str, Any]:
    return {
        "items": [
            {
                "id": "video-1",
                "snippet": {
                    "title": "First #CyberSafe update",
                    "description": "Learn #OSINT safely",
                    "publishedAt": "2026-01-01T00:00:00Z",
                    "channelId": "UC-channel",
                    "channelTitle": "Alice Example",
                    "tags": ["PoliceTech", "public-data"],
                    "liveBroadcastContent": "none",
                },
                "contentDetails": {
                    "duration": "PT2M30S",
                    "definition": "hd",
                    "caption": "true",
                },
                "statistics": {
                    "viewCount": "321",
                    "likeCount": "12",
                    "commentCount": "4",
                },
                "status": {"privacyStatus": "public"},
            }
        ]
    }


@pytest.mark.anyio
async def test_missing_key_and_invalid_handle_make_no_http_calls() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        raise AssertionError("disabled and invalid collectors must not call YouTube")

    transport = httpx.MockTransport(handler)
    missing = await YouTubeService(api_key=None, transport=transport).fetch_channel_and_videos(
        "alice"
    )
    invalid = await YouTubeService(api_key="key", transport=transport).fetch_channel_and_videos(
        "https://youtube.com/@alice"
    )

    assert missing["status"] == "disabled"
    assert missing["error_code"] == "youtube_not_configured"
    assert missing["usage"]["calls_made"] == 0
    assert invalid["status"] == "error"
    assert invalid["error_code"] == "invalid_handle"
    assert invalid["usage"]["calls_made"] == 0
    assert requests == []


@pytest.mark.anyio
async def test_no_channel_is_authoritative_no_results_after_one_call() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"items": []})

    result = await YouTubeService(
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    ).fetch_channel_and_videos("@alice")

    assert result["success"] is True
    assert result["status"] == "no_results"
    assert result["found"] is False
    assert result["videos"] == []
    assert result["usage"]["calls_made"] == 1
    assert len(requests) == 1
    assert requests[0].url.path.endswith("/channels")
    assert requests[0].url.params["forHandle"] == "alice"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "channel_payload",
    [
        {},
        {"items": [{}]},
    ],
)
async def test_malformed_channel_response_is_not_evidence(
    channel_payload: dict[str, Any],
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=channel_payload)

    result = await YouTubeService(
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    ).fetch_channel_and_videos("alice")

    assert result["success"] is False
    assert result["found"] is False
    assert result["status"] == "error"
    assert result["error_code"] == "youtube_invalid_response"
    assert result["channel"] is None
    assert result["videos"] == []


@pytest.mark.anyio
async def test_legacy_custom_url_cannot_retarget_for_handle_result() -> None:
    payload = _channel_payload(uploads=None)
    payload["items"][0]["snippet"]["customUrl"] = "@legacy-name"

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    result = await YouTubeService(
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    ).fetch_channel_and_videos("alice")

    assert result["success"] is True
    assert result["username"] == "alice"
    assert result["url"] == "https://www.youtube.com/@alice"
    assert result["profile"]["custom_url"] == "@legacy-name"


@pytest.mark.anyio
async def test_foreign_upload_row_is_rejected_as_partial_invalid_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/channels"):
            return httpx.Response(200, json=_channel_payload())
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "contentDetails": {"videoId": "video-1"},
                        "snippet": {
                            "videoOwnerChannelId": "UC-mallory",
                            "title": "Foreign video",
                        },
                    }
                ]
            },
        )

    result = await YouTubeService(
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    ).fetch_channel_and_videos("alice")

    assert result["success"] is True
    assert result["found"] is True
    assert result["status"] == "partial"
    assert result["error_code"] == "youtube_invalid_response"
    assert result["videos"] == []


@pytest.mark.anyio
async def test_foreign_video_details_cannot_be_attached_to_channel() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/channels"):
            return httpx.Response(200, json=_channel_payload())
        if request.url.path.endswith("/playlistItems"):
            return httpx.Response(200, json=_playlist_payload())
        payload = _video_payload()
        payload["items"][0]["snippet"]["channelId"] = "UC-mallory"
        return httpx.Response(200, json=payload)

    result = await YouTubeService(
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    ).fetch_channel_and_videos("alice")

    assert result["success"] is True
    assert result["status"] == "partial"
    assert result["error_code"] == "youtube_invalid_response"
    assert result["videos"][0]["channel_id"] == "UC-channel"
    assert result["videos"][0].get("view_count") is None


@pytest.mark.anyio
@pytest.mark.parametrize("broken_endpoint", ["playlistItems", "videos"])
async def test_missing_items_in_optional_response_is_partial_not_empty_success(
    broken_endpoint: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        endpoint = request.url.path.rsplit("/", 1)[-1]
        if endpoint == "channels":
            return httpx.Response(200, json=_channel_payload())
        if endpoint == broken_endpoint:
            return httpx.Response(200, json={})
        if endpoint == "playlistItems":
            return httpx.Response(200, json=_playlist_payload())
        raise AssertionError(f"unexpected YouTube endpoint: {endpoint}")

    result = await YouTubeService(
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    ).fetch_channel_and_videos("alice")

    assert result["success"] is True
    assert result["found"] is True
    assert result["status"] == "partial"
    assert result["error_code"] == "youtube_invalid_response"
    assert result["usage"]["calls_made"] == (
        2 if broken_endpoint == "playlistItems" else 3
    )


@pytest.mark.anyio
async def test_collects_channel_and_uploads_with_three_low_cost_calls() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/channels"):
            return httpx.Response(200, json=_channel_payload())
        if request.url.path.endswith("/playlistItems"):
            return httpx.Response(200, json=_playlist_payload())
        if request.url.path.endswith("/videos"):
            return httpx.Response(200, json=_video_payload())
        raise AssertionError(f"unexpected YouTube endpoint: {request.url.path}")

    result = await YouTubeService(
        api_key="test-key",
        video_limit=999,
        max_requests=999,
        transport=httpx.MockTransport(handler),
    ).fetch_channel_and_videos("Alice")

    assert result["success"] is True
    assert result["status"] == "completed"
    assert result["found"] is True
    assert result["provider"] == "youtube_data_api_v3"
    assert result["username"] == "Alice"
    assert result["channel_id"] == "UC-channel"
    assert result["url"] == "https://www.youtube.com/@Alice"
    assert result["subscriber_count"] == 1200
    assert result["profile"]["view_count"] == 55000
    assert result["total"] == 1
    assert result["videos"] == result["recent_posts"]
    assert result["videos"][0]["id"] == "video-1"
    assert result["videos"][0]["duration"] == "PT2M30S"
    assert result["videos"][0]["view_count"] == 321
    assert result["videos"][0]["caption_available"] is True
    assert result["videos"][0]["tags"] == ["PoliceTech", "public-data"]
    assert result["videos"][0]["hashtags"] == ["cybersafe", "osint", "policetech", "public-data"]
    assert result["all_hashtags"] == ["cybersafe", "osint", "policetech", "public-data"]
    assert result["usage"] == {
        "calls_made": 3,
        "call_limit": 3,
        "quota_units_used": 3,
        "quota_unit_limit": 3,
        "estimated_quota_units_used": 3,
        "estimated_quota_unit_limit": 3,
        "videos_returned": 1,
    }

    assert [request.url.path.rsplit("/", 1)[-1] for request in requests] == [
        "channels",
        "playlistItems",
        "videos",
    ]
    assert all(not request.url.path.endswith("/search") for request in requests)
    assert requests[0].url.params["part"] == "snippet,statistics,contentDetails"
    assert requests[1].url.params["playlistId"] == "UU-channel"
    # Constructor inputs may lower but cannot raise server-owned ceilings.
    assert requests[1].url.params["maxResults"] == "10"
    assert requests[2].url.params["id"] == "video-1"
    assert "test-key" not in json.dumps(result)


@pytest.mark.anyio
async def test_channel_without_uploads_playlist_completes_after_one_call() -> None:
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(200, json=_channel_payload(uploads=None))

    result = await YouTubeService(
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    ).fetch_channel_and_videos("alice")

    assert result["status"] == "completed"
    assert result["found"] is True
    assert result["videos"] == []
    assert result["usage"]["calls_made"] == 1
    assert requests == 1


@pytest.mark.anyio
async def test_quota_error_is_safe_and_does_not_expose_provider_message() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={
                "error": {
                    "message": "secret diagnostic mentioning test-key and alice",
                    "errors": [{"reason": "quotaExceeded"}],
                }
            },
        )

    result = await YouTubeService(
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    ).fetch_channel_and_videos("alice")

    serialized = json.dumps(result)
    assert result["success"] is False
    assert result["status"] == "quota_exhausted"
    assert result["error_code"] == "youtube_quota_exhausted"
    assert result["http_status"] == 403
    assert result["usage"]["calls_made"] == 1
    assert "secret diagnostic" not in serialized
    assert "test-key" not in serialized


@pytest.mark.anyio
async def test_later_provider_failure_preserves_collected_channel() -> None:
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        if request.url.path.endswith("/channels"):
            return httpx.Response(200, json=_channel_payload())
        return httpx.Response(
            503,
            json={"error": {"message": "internal provider detail"}},
        )

    result = await YouTubeService(
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    ).fetch_channel_and_videos("alice")

    assert result["success"] is True
    assert result["status"] == "partial"
    assert result["found"] is True
    assert result["channel_id"] == "UC-channel"
    assert result["error_code"] == "youtube_provider_unavailable"
    assert result["videos"] == []
    assert result["usage"]["calls_made"] == 2
    assert requests == 2


@pytest.mark.anyio
async def test_lower_request_ceiling_preserves_basic_playlist_rows() -> None:
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        if request.url.path.endswith("/channels"):
            return httpx.Response(200, json=_channel_payload())
        if request.url.path.endswith("/playlistItems"):
            return httpx.Response(200, json=_playlist_payload())
        raise AssertionError("the locally lowered two-call ceiling must prevent details call")

    result = await YouTubeService(
        api_key="test-key",
        max_requests=2,
        transport=httpx.MockTransport(handler),
    ).fetch_channel_and_videos("alice")

    assert result["status"] == "partial"
    assert result["error_code"] == "youtube_call_limit_reached"
    assert result["videos"][0]["title"] == "First #CyberSafe update"
    assert result["usage"]["calls_made"] == 2
    assert result["usage"]["call_limit"] == 2
    assert requests == 2


def test_youtube_settings_enforce_server_owned_bounds() -> None:
    configured = Settings(
        _env_file=None,
        youtube_api_key="key",
        youtube_max_requests_per_scan=3,
        youtube_videos_limit=20,
    )

    assert configured.youtube_enabled is True
    assert configured.youtube_api_key == "key"
    assert configured.youtube_max_requests_per_scan == 3
    assert configured.youtube_videos_limit == 20

    with pytest.raises(ValidationError):
        Settings(_env_file=None, youtube_max_requests_per_scan=4)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, youtube_videos_limit=21)
