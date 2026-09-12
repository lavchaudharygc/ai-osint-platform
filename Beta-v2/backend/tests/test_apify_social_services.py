"""Offline contract tests for social collectors backed by Apify Actors."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

import pytest

from app.config import settings
from app.services.apify_client import ApifyActorRun, ApifyClientError
from app.services.facebook_service import FacebookService
from app.services.instagram_service import InstagramService
from app.services.tiktok_service import TikTokService
from app.services.twitter_service import TwitterService


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _run(actor_id: str, items: list[dict[str, Any]]) -> ApifyActorRun:
    return ApifyActorRun(
        actor_id=actor_id,
        run_id=f"run-{actor_id.replace('/', '-')}",
        run_status="SUCCEEDED",
        dataset_id=f"dataset-{actor_id.replace('/', '-')}",
        items=items,
        fetched_at="2030-01-01T00:00:00+00:00",
    )


class FakeApifyClient:
    """Small Actor-client fake that records bounded, non-network launches."""

    def __init__(
        self,
        responses: Mapping[str, ApifyActorRun | BaseException],
        *,
        configured: bool = True,
    ) -> None:
        self.responses = dict(responses)
        self.configured = configured
        self.calls: list[tuple[str, dict[str, Any], int]] = []

    def is_configured(self) -> bool:
        return self.configured

    async def run_actor(
        self,
        actor_id: str,
        run_input: dict[str, Any],
        *,
        dataset_limit: int,
    ) -> ApifyActorRun:
        self.calls.append((actor_id, run_input, dataset_limit))
        # Preserve real concurrent scheduling behavior for Facebook's two runs.
        await asyncio.sleep(0)
        response = self.responses[actor_id]
        if isinstance(response, BaseException):
            raise response
        return response


@pytest.mark.anyio
async def test_instagram_uses_shared_actors_and_normalizes_profile_posts_hashtags() -> None:
    profile_actor = settings.apify_instagram_profile_actor_id
    posts_actor = settings.apify_instagram_posts_actor_id
    fake = FakeApifyClient(
        {
            profile_actor: _run(
                profile_actor,
                [
                    {
                        "fullName": "Alice Analyst",
                        "biography": "Public safety #UPPolice",
                        "followersCount": 120,
                        "followsCount": 45,
                        "postsCount": 7,
                        "verified": True,
                        "profilePicUrl": "https://images.example/alice.jpg",
                    }
                ],
            ),
            posts_actor: _run(
                posts_actor,
                [
                    {
                        "id": "ig-1",
                        "shortCode": "ABC123",
                        "caption": "Cyber awareness #CyberSafe #UPPolice",
                        "hashtags": ["#CyberSafe"],
                        "likesCount": 20,
                        "commentsCount": 3,
                    }
                ],
            ),
        }
    )

    result = await InstagramService(client=fake).fetch_profile_and_posts("@alice")  # type: ignore[arg-type]

    assert result["success"] is True
    assert result["username"] == "alice"
    assert result["full_name"] == "Alice Analyst"
    assert result["source"] == "apify"
    assert result["post_hashtags"] == ["cybersafe", "uppolice"]
    assert result["posts"][0]["id"] == "ig-1"
    assert fake.calls == [
        (profile_actor, {"usernames": ["alice"]}, 2),
        (
            posts_actor,
            {
                "directUrls": ["https://www.instagram.com/alice/"],
                "resultsType": "posts",
                "resultsLimit": 30,
                "addParentData": False,
            },
            30,
        ),
    ]


@pytest.mark.anyio
async def test_tiktok_uses_shared_actor_and_returns_run_provenance() -> None:
    actor_id = settings.apify_tiktok_actor_id
    fake = FakeApifyClient(
        {
            actor_id: _run(
                actor_id,
                [
                    {
                        "id": "video-1",
                        "text": "Stay alert #CyberSafe",
                        "playCount": 500,
                        "diggCount": 22,
                        "shareCount": 4,
                        "commentCount": 2,
                        "webVideoUrl": "https://www.tiktok.com/@alice/video/1",
                        "authorMeta": {
                            "name": "alice",
                            "nickName": "Alice Analyst",
                            "signature": "Public safety",
                            "fans": 75,
                            "following": 9,
                            "heart": 900,
                            "video": 12,
                            "verified": False,
                        },
                    }
                ],
            )
        }
    )

    result = await TikTokService(client=fake).fetch_profile_and_videos("@alice/path")  # type: ignore[arg-type]

    assert result["success"] is True
    assert result["username"] == "alice"
    assert result["hashtags"] == ["CyberSafe"]
    assert result["videos"][0]["id"] == "video-1"
    assert result["actor_run"]["run_status"] == "SUCCEEDED"
    assert "items" not in result["actor_run"]
    assert fake.calls == [
        (
            actor_id,
            {
                "profiles": ["alice"],
                "resultsPerPage": 15,
                "profileScrapeSections": ["videos"],
                "profileSorting": "latest",
                "shouldDownloadVideos": False,
                "shouldDownloadAvatars": False,
            },
            15,
        )
    ]


@pytest.mark.anyio
async def test_tiktok_surfaces_safe_apify_403_details() -> None:
    actor_id = settings.apify_tiktok_actor_id
    fake = FakeApifyClient(
        {
            actor_id: ApifyClientError(
                "sensitive provider detail",
                actor_id=actor_id,
                code="access_denied",
                status_code=403,
                provider_error_type="full-permission-actor-not-approved",
                operation="start",
            )
        }
    )

    result = await TikTokService(client=fake).fetch_profile_and_videos("alice")  # type: ignore[arg-type]

    assert result == {
        "success": False,
        "status": "error",
        "platform": "tiktok",
        "username": "alice",
        "provider": "apify",
        "error": "Apify token or Actor permissions do not allow this run",
        "error_code": "access_denied",
        "provider_error_type": "full-permission-actor-not-approved",
        "http_status": 403,
    }
    assert "sensitive provider detail" not in str(result)


@pytest.mark.anyio
async def test_facebook_uses_shared_page_and_post_actors_and_normalizes_results() -> None:
    pages_actor = settings.apify_facebook_pages_actor_id
    posts_actor = settings.apify_facebook_posts_actor_id
    fake = FakeApifyClient(
        {
            pages_actor: _run(
                pages_actor,
                [
                    {
                        "pageName": "alice.unit",
                        "facebookUrl": "https://www.facebook.com/alice.unit",
                        "title": "Alice Unit",
                        "intro": "Official public page",
                        "followers": 300,
                        "likes": 250,
                    }
                ],
            ),
            posts_actor: _run(
                posts_actor,
                [
                    {
                        "postId": "fb-1",
                        "text": "Safety update #CyberSafe",
                        "likes": 10,
                        "comments": 2,
                        "shares": 1,
                    }
                ],
            ),
        }
    )

    result = await FacebookService(client=fake).fetch_page_or_profile("@alice.unit")  # type: ignore[arg-type]

    assert result["success"] is True
    assert result["username"] == "alice.unit"
    assert result["full_name"] == "Alice Unit"
    assert result["posts"][0]["id"] == "fb-1"
    assert result["all_hashtags"] == ["CyberSafe"]
    assert sorted(fake.calls, key=lambda call: call[0]) == sorted(
        [
            (
                pages_actor,
                {"startUrls": [{"url": "https://www.facebook.com/alice.unit"}]},
                2,
            ),
            (
                posts_actor,
                {
                    "startUrls": [{"url": "https://www.facebook.com/alice.unit"}],
                    "resultsLimit": 15,
                },
                15,
            ),
        ],
        key=lambda call: call[0],
    )


@pytest.mark.anyio
async def test_x_actor_returns_real_tweets_and_never_relabels_follower_rows() -> None:
    actor_id = settings.apify_twitter_actor_id
    fake = FakeApifyClient(
        {
            actor_id: _run(
                actor_id,
                [
                    {
                        "id": "tweet-1",
                        "fullText": "First public post #CyberSafe",
                        "createdAt": "2030-01-01T10:00:00.000Z",
                        "likeCount": 11,
                        "retweetCount": 2,
                        "replyCount": 1,
                        "viewCount": 100,
                        "url": "https://x.com/alice/status/tweet-1",
                        "hashtags": [{"text": "UPPolice"}],
                        "user": {
                            "username": "alice",
                            "name": "Alice Analyst",
                            "description": "Public safety analyst",
                            "profileImageUrl": "https://images.example/alice-x.jpg",
                            "followersCount": 321,
                            "followingCount": 42,
                            "tweetsCount": 55,
                        },
                    },
                    {
                        "type": "follower",
                        "name": "Connection that is not a tweet",
                        "screen_name": "connection",
                        "description": "This row has no timeline-post text field",
                    },
                    {
                        "tweetId": "tweet-2",
                        "tweetText": "Second post #UPPolice",
                        "tweetUrl": "https://x.com/alice/status/tweet-2",
                        "likes": 7,
                        "repostCount": 1,
                    },
                    {"error": "actor diagnostic row"},
                ],
            )
        }
    )

    result = await TwitterService(client=fake).fetch_profile_and_tweets("@alice/path")  # type: ignore[arg-type]

    assert result["success"] is True
    assert result["username"] == "alice"
    assert result["full_name"] == "Alice Analyst"
    assert result["bio"] == "Public safety analyst"
    assert result["follower_count"] == 321
    assert result["following_count"] == 42
    assert result["post_count"] == 55
    assert result["hashtags"] == ["cybersafe", "uppolice"]
    assert [tweet["id"] for tweet in result["tweets"]] == ["tweet-1", "tweet-2"]
    assert all("[FOLLOWER]" not in tweet["text"] for tweet in result["tweets"])
    assert result["tweets"][0]["like_count"] == 11
    assert result["tweets"][1]["retweet_count"] == 1
    assert result["source"] == "apify_x_timeline"
    assert "items" not in result["actor_run"]
    assert fake.calls == [
        (
            actor_id,
            {
                "mode": "user-tweets",
                "usernames": ["alice"],
                "maxResults": 20,
            },
            20,
        )
    ]
