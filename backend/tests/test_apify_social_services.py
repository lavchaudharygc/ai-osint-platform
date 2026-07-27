import unittest
from typing import Any

from backend.services.apify_client import ApifyActorRun, ApifyClientError
from backend.services.facebook_apify_service import FacebookApifyService
from backend.services.linkedin_apify_service import LinkedInApifyService
from backend.services.reddit_apify_service import RedditApifyService
from backend.services.twitter_apify_service import TwitterApifyService


TWITTER_PROFILE_ACTOR = "apidojo/twitter-profile-scraper"
TWITTER_TWEET_ACTOR = "apidojo/tweet-scraper"
REDDIT_ACTOR = "automation-lab/reddit-scraper"
LINKEDIN_BULK_ACTOR = "bebity/linkedin-premium-actor"
LINKEDIN_POSTS_ACTOR = "apimaestro/linkedin-posts-search-scraper-no-cookies"
FACEBOOK_PAGES_ACTOR = "apify/facebook-pages-scraper"
FACEBOOK_POSTS_ACTOR = "apify/facebook-posts-scraper"


class RecordingActorClient:
    def __init__(
        self,
        responses: list[list[dict[str, Any]]] | None = None,
        *,
        configured: bool = True,
    ) -> None:
        self.responses = list(responses or [])
        self.configured = configured
        self.calls: list[dict[str, Any]] = []

    def is_configured(self) -> bool:
        return self.configured

    async def run_actor(
        self,
        actor_id: str,
        run_input: dict[str, Any],
        *,
        dataset_limit: int,
    ) -> ApifyActorRun:
        self.calls.append(
            {
                "actor_id": actor_id,
                "run_input": run_input,
                "dataset_limit": dataset_limit,
            }
        )
        items = self.responses.pop(0) if self.responses else []
        return ApifyActorRun(
            actor_id=actor_id,
            run_id=f"run-{len(self.calls)}",
            run_status="SUCCEEDED",
            dataset_id=f"dataset-{len(self.calls)}",
            items=items,
            started_at="2026-07-11T10:00:00.000Z",
            finished_at="2026-07-11T10:00:01.000Z",
            fetched_at="2026-07-11T10:00:01+00:00",
        )


class FailingActorClient(RecordingActorClient):
    async def run_actor(
        self,
        actor_id: str,
        run_input: dict[str, Any],
        *,
        dataset_limit: int,
    ) -> ApifyActorRun:
        self.calls.append(
            {
                "actor_id": actor_id,
                "run_input": run_input,
                "dataset_limit": dataset_limit,
            }
        )
        raise ApifyClientError(
            "Actor access is forbidden",
            actor_id=actor_id,
            code="start_failed",
            status_code=403,
            run_id="failed-run",
            run_status="FAILED",
        )


def twitter_service(client: RecordingActorClient) -> TwitterApifyService:
    service = TwitterApifyService(client=client)  # type: ignore[arg-type]
    service.profile_actor_id = TWITTER_PROFILE_ACTOR
    service.tweet_actor_id = TWITTER_TWEET_ACTOR
    return service


def reddit_service(client: RecordingActorClient) -> RedditApifyService:
    service = RedditApifyService(client=client)  # type: ignore[arg-type]
    service.actor_id = REDDIT_ACTOR
    return service


def linkedin_service(client: RecordingActorClient) -> LinkedInApifyService:
    service = LinkedInApifyService(client=client)  # type: ignore[arg-type]
    service.profile_actor_id = LINKEDIN_BULK_ACTOR
    service.posts_actor_id = LINKEDIN_POSTS_ACTOR
    return service


def facebook_service(client: RecordingActorClient) -> FacebookApifyService:
    service = FacebookApifyService(client=client)  # type: ignore[arg-type]
    service.pages_actor_id = FACEBOOK_PAGES_ACTOR
    service.posts_actor_id = FACEBOOK_POSTS_ACTOR
    return service


class TwitterApifyServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_profile_actor_input_and_tweet_reply_normalization(self) -> None:
        profile_author = {
            "id": "user-1",
            "userName": "TargetUser",
            "name": "Target User",
            "description": "Public researcher",
            "profilePicture": "https://cdn.test/avatar-small.jpg",
            "followers": 101,
            "following": 22,
            "statusesCount": 303,
            "isVerified": False,
            "isBlueVerified": True,
            "about": {
                "avatarUrl": "https://cdn.test/avatar-large.jpg",
                "accountBasedIn": "India",
                "accountCreatedAt": "2020-01-01T00:00:00.000Z",
                "usernameChangeCount": 2,
            },
        }
        tweet = {
            "type": "tweet",
            "id": "tweet-1",
            "twitterUrl": "https://x.com/TargetUser/status/tweet-1",
            "fullText": "Research #OSINT with @Analyst",
            "author": profile_author,
            "entities": {
                "hashtags": [{"text": "OSINT"}],
                "user_mentions": [{"screen_name": "Analyst"}],
                "urls": [{"expanded_url": "https://example.test/report"}],
            },
            "likeCount": 10,
        }
        reply = {
            "type": "reply",
            "id": "reply-1",
            "conversationId": "tweet-1",
            "fullText": "Useful #Research",
            "author": {"id": "user-2", "userName": "OtherUser"},
            "entities": {"hashtags": ["#Research"]},
        }
        unrelated = {
            "type": "tweet",
            "id": "unrelated",
            "author": {"userName": "OtherUser"},
        }
        client = RecordingActorClient([[tweet, reply, unrelated]])
        service = twitter_service(client)

        result = await service.get_profile(
            " @TargetUser ",
            max_items=25,
            get_replies=True,
            min_reply_count=4,
            get_about_data=True,
        )

        self.assertEqual(
            client.calls,
            [
                {
                    "actor_id": TWITTER_PROFILE_ACTOR,
                    "run_input": {
                        "twitterHandles": ["TargetUser"],
                        "profileUrls": ["https://x.com/TargetUser", "https://twitter.com/TargetUser"],
                        "urls": ["https://x.com/TargetUser"],
                        "maxItems": 25,
                        "maxPosts": 25,
                        "getReplies": True,
                        "minReplyCount": 4,
                        "getAboutData": True,
                        "includeNativeRetweets": False,
                        "onlyImages": False,
                    },
                    "dataset_limit": 25,
                },
            ],
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["username"], "TargetUser")
        self.assertEqual(result["profile_pic_hd"], "https://cdn.test/avatar-large.jpg")
        self.assertEqual(result["account_based_in"], "India")
        self.assertEqual(result["total_tweets_fetched"], 1)
        self.assertEqual(result["total_replies_fetched"], 1)
        self.assertEqual(result["discarded_related_items"], 1)
        self.assertEqual(result["all_hashtags"], ["OSINT", "Research"])
        self.assertEqual(result["tweets"][0]["mentions"], ["Analyst"])
        self.assertEqual(
            result["tweets"][0]["external_urls"],
            ["https://example.test/report"],
        )
        self.assertTrue(result["replies"][0]["is_reply"])

    async def test_profile_actor_flattened_normalization(self) -> None:
        tweet = {
            "text": "Success is uncertain, but entertainment is guaranteed! ✨",
            "author.name": "Elon Musk",
            "author.userName": "elonmusk",
            "likeCount": 1238034,
            "retweetCount": 118985,
            "replyCount": 33850,
            "viewCount": 114596489,
            "createdAt": "Thu Jan 16 23:53:03 +0000 2025",
            "url": "https://x.com/elonmusk/status/1880040599761596689",
            "id": "1880040599761596689"
        }
        client = RecordingActorClient([[tweet]])
        service = twitter_service(client)

        result = await service.get_profile("elonmusk")
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.calls[0]["actor_id"], TWITTER_PROFILE_ACTOR)
        self.assertTrue(result["success"])
        self.assertEqual(result["username"], "elonmusk")
        self.assertEqual(result["full_name"], "Elon Musk")
        self.assertEqual(result["tweets"][0]["like_count"], 1238034)

    async def test_empty_profile_result_does_not_trigger_an_actor_fallback(self) -> None:
        client = RecordingActorClient([[]])
        service = twitter_service(client)

        result = await service.get_profile("missing-user", max_items=8)

        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.calls[0]["actor_id"], TWITTER_PROFILE_ACTOR)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "empty_dataset")
        self.assertEqual(result["actor_id"], TWITTER_PROFILE_ACTOR)

    async def test_tweet_v2_search_actor_input_and_normalization(self) -> None:
        client = RecordingActorClient(
            [[{"id": "tweet-2", "text": "Hello", "author": {"username": "alice"}}]]
        )
        service = twitter_service(client)

        result = await service.search(
            search_terms=[" threat intel ", ""],
            twitter_handles=[" @alice "],
            start_urls=[" https://x.com/alice/status/1 ", ""],
            conversation_ids=[" 12345 "],
            max_items=7,
            tweet_language="en",
            sort="Top",
            author="@bob",
            in_reply_to="@carol",
            mentioning="@dave",
            include_search_terms=False,
        )

        self.assertEqual(
            client.calls,
            [
                {
                    "actor_id": TWITTER_TWEET_ACTOR,
                    "run_input": {
                        "searchTerms": ["threat intel"],
                        "twitterHandles": ["alice"],
                        "startUrls": ["https://x.com/alice/status/1"],
                        "conversationIds": ["12345"],
                        "maxItems": 7,
                        "sort": "Top",
                        "includeSearchTerms": False,
                        "tweetLanguage": "en",
                        "author": "bob",
                        "inReplyTo": "carol",
                        "mentioning": "dave",
                    },
                    "dataset_limit": 7,
                }
            ],
        )
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["tweets"][0]["id"], "tweet-2")
        self.assertEqual(result["tweets"][0]["author"]["username"], "alice")

    async def test_profile_defaults_are_cost_safe_and_profile_only_output_is_supported(self) -> None:
        profile = {
            "type": "profile",
            "status": "available",
            "username": "alice",
            "name": "Alice Analyst",
            "bio": "Public research account",
            "avatar_url": "https://cdn.test/alice.jpg",
            "followers": 0,
            "following": 12,
            "tweets_count": 34,
            "created_at": "2020-01-01T00:00:00Z",
        }
        client = RecordingActorClient([[profile]])
        service = twitter_service(client)

        result = await service.get_profile("@alice")

        self.assertEqual(
            client.calls,
            [
                {
                    "actor_id": TWITTER_PROFILE_ACTOR,
                    "run_input": {
                        "twitterHandles": ["alice"],
                        "profileUrls": ["https://x.com/alice", "https://twitter.com/alice"],
                        "urls": ["https://x.com/alice"],
                        "maxItems": 5,
                        "maxPosts": 5,
                        "getReplies": False,
                        "getAboutData": False,
                        "includeNativeRetweets": False,
                        "onlyImages": False,
                    },
                    "dataset_limit": 5,
                }
            ],
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["username"], "alice")
        self.assertEqual(result["follower_count"], 0)
        self.assertEqual(result["tweets"], [])
        self.assertEqual(result["run"]["run_id"], "run-1")
        self.assertFalse(result["collection_options"]["get_replies"])
        self.assertFalse(result["collection_options"]["get_about_data"])

    async def test_explicit_paid_features_are_preserved_with_a_hard_item_cap(self) -> None:
        client = RecordingActorClient([[]])
        service = twitter_service(client)

        result = await service.get_profile(
            "alice",
            max_items=1000,
            get_replies=True,
            min_reply_count=25,
            get_about_data=True,
        )

        call = client.calls[0]
        self.assertEqual(call["dataset_limit"], 40)
        self.assertEqual(call["run_input"]["maxItems"], 40)
        self.assertTrue(call["run_input"]["getReplies"])
        self.assertEqual(call["run_input"]["minReplyCount"], 25)
        self.assertTrue(call["run_input"]["getAboutData"])
        self.assertEqual(result["collection_options"]["requested_max_items"], 1000)
        self.assertEqual(result["collection_options"]["max_items"], 40)

    async def test_actor_error_dataset_item_is_not_treated_as_a_profile(self) -> None:
        client = RecordingActorClient(
            [[{"type": "error", "status": "failed", "error": {"message": "Access denied"}}]]
        )
        service = twitter_service(client)

        result = await service.get_profile("alice")

        self.assertEqual(len(client.calls), 1)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "provider_error")
        self.assertEqual(result["reason"], "Access denied")
        self.assertEqual(result["reason_detail"]["code"], "actor_output_error")
        self.assertEqual(result["run"]["run_id"], "run-1")
        self.assertEqual(result["actor_diagnostics"][0]["code"], "failed")

    async def test_actor_not_found_dataset_item_is_structured(self) -> None:
        client = RecordingActorClient(
            [[{"status": "not_found", "username": "missing", "message": "User not found"}]]
        )
        service = twitter_service(client)

        result = await service.get_profile("missing")

        self.assertFalse(result["success"])
        self.assertFalse(result["exists"])
        self.assertEqual(result["status"], "not_found")
        self.assertEqual(result["reason_detail"]["code"], "target_not_found")
        self.assertEqual(result["run"]["run_status"], "SUCCEEDED")

    async def test_actor_demo_placeholders_report_plan_restriction(self) -> None:
        client = RecordingActorClient([[{"demo": True}, {"demo": True}]])
        service = twitter_service(client)

        result = await service.get_profile("alice")

        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "provider_error")
        self.assertEqual(result["reason_detail"]["code"], "provider_plan_required")
        self.assertEqual(
            result["actor_diagnostics"][0]["classification"],
            "provider_plan_restricted",
        )
        self.assertIn("paid access", result["reason"])

    async def test_tweet_actor_demo_placeholders_report_plan_restriction(self) -> None:
        client = RecordingActorClient([[{"demo": True}]])
        service = twitter_service(client)

        result = await service.search(search_terms=["from:alice"])

        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "provider_error")
        self.assertEqual(result["reason_detail"]["code"], "provider_plan_required")

    async def test_actor_run_exception_preserves_run_metadata_without_fallback(self) -> None:
        client = FailingActorClient()
        service = twitter_service(client)

        result = await service.get_profile("alice")

        self.assertEqual(len(client.calls), 1)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "provider_error")
        self.assertEqual(result["reason_detail"]["status_code"], 403)
        self.assertEqual(result["run"]["run_id"], "failed-run")
        self.assertEqual(result["run"]["run_status"], "FAILED")

    async def test_empty_search_has_reason_run_metadata_and_safe_defaults(self) -> None:
        client = RecordingActorClient([[]])
        service = twitter_service(client)

        result = await service.search(search_terms=["from:alice"])

        self.assertEqual(client.calls[0]["run_input"]["maxItems"], 10)
        self.assertFalse(client.calls[0]["run_input"]["includeSearchTerms"])
        self.assertEqual(client.calls[0]["dataset_limit"], 10)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "empty_dataset")
        self.assertEqual(result["reason_detail"]["code"], "empty_dataset")
        self.assertEqual(result["run"]["run_id"], "run-1")


class RedditApifyServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_automation_lab_input_dataset_bound_and_normalization(self) -> None:
        post = {
            "type": "post",
            "id": "post-1",
            "title": "Public #OSINT update",
            "selfText": "Details",
            "author": "researcher",
            "subreddit": "osint",
            "score": 42,
            "upvoteRatio": 0.9,
            "numComments": 3,
            "permalink": "https://reddit.com/r/osint/comments/post-1",
            "warnings": ["votes may be hidden"],
        }
        comment = {
            "type": "comment",
            "id": "comment-1",
            "postId": "post-1",
            "body": "Public reply",
            "depth": 1,
            "warnings": "votes may be hidden",
        }
        diagnostic = {"type": "target-status", "target": "r/osint", "status": "ok"}
        extra = {"type": "summary", "processed": 2}
        client = RecordingActorClient([[post, comment, diagnostic, extra]])
        service = reddit_service(client)

        result = await service.collect(
            urls=[" https://www.reddit.com/r/osint/ ", ""],
            search_query=" breach report ",
            search_subreddit="r/cybersecurity",
            sort="new",
            time_filter="month",
            max_posts_per_source=2,
            include_comments=True,
            max_comments_per_post=3,
            comment_depth=2,
            filter_keywords=[" leak ", ""],
            filter_keyword_mode="all",
            deduplicate_posts=False,
        )

        self.assertEqual(
            client.calls,
            [
                {
                    "actor_id": REDDIT_ACTOR,
                    "run_input": {
                        "urls": ["https://www.reddit.com/r/osint/"],
                        "sort": "new",
                        "timeFilter": "month",
                        "maxPostsPerSource": 2,
                        "includeComments": True,
                        "maxCommentsPerPost": 3,
                        "commentDepth": 2,
                        "filterKeywords": ["leak"],
                        "filterKeywordMode": "all",
                        "deduplicatePosts": False,
                        "outputFormat": "default",
                        "searchQuery": "breach report",
                        "searchSubreddit": "cybersecurity",
                    },
                    # One direct URL plus one search query, each bounded to two
                    # posts and up to three comments per post.
                    "dataset_limit": 16,
                }
            ],
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["active_subreddits"], ["osint"])
        self.assertEqual(result["all_hashtags"], ["OSINT"])
        self.assertEqual(result["posts"][0]["upvote_ratio"], 0.9)
        self.assertEqual(result["comments"][0]["post_id"], "post-1")
        self.assertEqual(result["diagnostics"], [diagnostic])
        self.assertEqual(result["other_output_records"], [extra])
        self.assertEqual(result["warnings"], ["votes may be hidden"])


class LinkedInApifyServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_bebity_profile_and_company_bulk_inputs_and_normalization(self) -> None:
        profile = {
            "status": "OK",
            "linkedinUrl": "https://www.linkedin.com/in/alice/",
            "firstName": "Alice",
            "lastName": "Analyst",
            "headline": "Threat Researcher",
            "experience": [{"title": "Lead", "companyName": "Example Labs"}],
        }
        company = {
            "status": "OK",
            "linkedinUrl": "https://www.linkedin.com/company/example-labs/",
            "name": "Example Labs",
            "phone": {"number": "+1-555-0100"},
            "headquarter": {"city": "Pune"},
            "employeeCount": 50,
        }
        client = RecordingActorClient([[profile], [company]])
        service = linkedin_service(client)

        profiles_result = await service.bulk_lookup(
            action="get-profiles",
            keywords=[" https://www.linkedin.com/in/alice/ ", " Alice Analyst "],
            query_mode="url",
            limit=2,
            locations=[" India ", ""],
        )
        companies_result = await service.bulk_lookup(
            action="get-companies",
            keywords=[" Example Labs "],
            query_mode="name",
            limit=3,
        )

        self.assertEqual(
            client.calls,
            [
                {
                    "actor_id": LINKEDIN_BULK_ACTOR,
                    "run_input": {
                        "action": "get-profiles",
                        "keywords": [
                            "https://www.linkedin.com/in/alice/",
                            "Alice Analyst",
                        ],
                        "queries": [
                            "https://www.linkedin.com/in/alice/",
                            "Alice Analyst",
                        ],
                        "urls": [
                            "https://www.linkedin.com/in/alice/",
                            "Alice Analyst",
                        ],
                        "profileUrls": [
                            "https://www.linkedin.com/in/alice/",
                            "Alice Analyst",
                        ],
                        "limit": 2,
                        "location": ["India"],
                    },
                    "dataset_limit": 4,
                },
                {
                    "actor_id": LINKEDIN_BULK_ACTOR,
                    "run_input": {
                        "action": "get-companies",
                        "keywords": ["Example Labs"],
                        "queries": ["Example Labs"],
                        "urls": ["Example Labs"],
                        "profileUrls": ["Example Labs"],
                        "limit": 3,
                        "location": [],
                    },
                    "dataset_limit": 3,
                },
            ],
        )
        normalized_profile = profiles_result["profiles"][0]
        self.assertEqual(normalized_profile["username"], "alice")
        self.assertEqual(normalized_profile["full_name"], "Alice Analyst")
        self.assertEqual(normalized_profile["current_role"], "Lead")
        self.assertEqual(normalized_profile["current_company"], "Example Labs")
        normalized_company = companies_result["companies"][0]
        self.assertEqual(normalized_company["username"], "example-labs")
        self.assertEqual(normalized_company["phone"], "+1-555-0100")
        self.assertEqual(normalized_company["location"], {"city": "Pune"})

    async def test_api_maestro_post_search_input_and_normalization(self) -> None:
        post = {
            "activityId": "activity-1",
            "postUrl": "https://linkedin.com/feed/update/activity-1",
            "commentary": "A public #OSINT #Research update",
            "postedAt": "2026-07-10T00:00:00Z",
            "authorDetails": {
                "name": "Alice Analyst",
                "linkedinUrl": "https://linkedin.com/in/alice",
                "headline": "Researcher",
            },
            "totalReactionCount": 12,
            "totalComments": 2,
            "images": ["https://cdn.test/post.jpg"],
        }
        client = RecordingActorClient([[post]])
        service = linkedin_service(client)

        result = await service.search_posts(
            keyword=" threat intelligence ",
            sort_type="date_posted",
            page_number=2,
            date_filter="past-week",
            limit=20,
            total_posts=6,
            company_urns=" urn:li:fsd_company:1 ",
            author_company_urns=" urn:li:fsd_company:2 ",
            author_industry_urns=" urn:li:industry:96 ",
            author_job_title=" Security Analyst ",
            member_urns=" urn:li:fsd_profile:abc ",
        )

        self.assertEqual(
            client.calls,
            [
                {
                    "actor_id": LINKEDIN_POSTS_ACTOR,
                    "run_input": {
                        "keyword": "threat intelligence",
                        "sort_type": "date_posted",
                        "page_number": 2,
                        "date_filter": "past-week",
                        "limit": 20,
                        "total_posts": 6,
                        "company_urns": "urn:li:fsd_company:1",
                        "author_company_urns": "urn:li:fsd_company:2",
                        "author_industry_urns": "urn:li:industry:96",
                        "author_job_title": "Security Analyst",
                        "member_urns": "urn:li:fsd_profile:abc",
                    },
                    "dataset_limit": 6,
                }
            ],
        )
        self.assertEqual(result["all_hashtags"], ["OSINT", "Research"])
        self.assertEqual(result["posts"][0]["id"], "activity-1")
        self.assertEqual(result["posts"][0]["reaction_count"], 12)
        self.assertEqual(result["posts"][0]["author"]["name"], "Alice Analyst")


class FacebookApifyServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_official_pages_and_posts_actor_inputs_and_normalization(self) -> None:
        page = {
            "pageName": "targetpage",
            "facebookUrl": "https://www.facebook.com/targetpage",
            "title": "Target Page",
            "intro": "Public page",
            "profilePictureUrl": "https://cdn.test/profile.jpg",
            "followers": 1000,
            "likes": 900,
            "pageId": "page-1",
        }
        post = {
            "postId": "post-1",
            "url": "https://facebook.com/targetpage/posts/post-1",
            "inputUrl": "https://facebook.com/targetpage",
            "pageName": "Target Page",
            "text": "Public #OSINT post!",
            "user": {
                "id": "page-1",
                "name": "Target Page",
                "profileUrl": "https://facebook.com/targetpage",
            },
            "likes": 10,
            "comments": 2,
            "shares": 1,
            "reactionLoveCount": 3,
            "textReferences": [
                {"external_url": "https://example.test/report"},
                {"url": "https://example.test/source"},
            ],
        }
        client = RecordingActorClient([[page], [post]])
        service = facebook_service(client)

        pages_result = await service.scrape_pages([" targetpage "])
        posts_result = await service.scrape_posts(
            ["https://facebook.com/targetpage"],
            results_limit=3,
            caption_text=True,
            only_posts_newer_than=" 2026-07-01 ",
            only_posts_older_than=" 2026-07-11 ",
        )

        self.assertEqual(
            client.calls,
            [
                {
                    "actor_id": FACEBOOK_PAGES_ACTOR,
                    "run_input": {
                        "startUrls": [
                            {"url": "https://www.facebook.com/targetpage"}
                        ]
                    },
                    "dataset_limit": 1,
                },
                {
                    "actor_id": FACEBOOK_POSTS_ACTOR,
                    "run_input": {
                        "startUrls": [
                            {"url": "https://facebook.com/targetpage"}
                        ],
                        "resultsLimit": 3,
                        "captionText": True,
                        "onlyPostsNewerThan": "2026-07-01",
                        "onlyPostsOlderThan": "2026-07-11",
                    },
                    "dataset_limit": 3,
                },
            ],
        )
        self.assertEqual(pages_result["pages"][0]["full_name"], "Target Page")
        self.assertEqual(pages_result["pages"][0]["follower_count"], 1000)
        normalized_post = posts_result["posts"][0]
        self.assertEqual(normalized_post["id"], "post-1")
        self.assertEqual(normalized_post["reaction_breakdown"]["love"], 3)
        self.assertEqual(
            normalized_post["external_urls"],
            ["https://example.test/report", "https://example.test/source"],
        )
        self.assertEqual(posts_result["all_hashtags"], ["OSINT"])


class MissingApifyTokenTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_social_services_return_structured_not_configured_results(self) -> None:
        client = RecordingActorClient(configured=False)

        twitter_result = await twitter_service(client).get_profile("@alice")
        reddit_result = await reddit_service(client).collect(
            urls=["https://reddit.com/user/alice/"]
        )
        linkedin_result = await linkedin_service(client).bulk_lookup(
            action="get-profiles",
            keywords=["alice"],
        )
        pages_result = await facebook_service(client).scrape_pages(["targetpage"])
        posts_result = await facebook_service(client).scrape_posts(["targetpage"])

        expected = (
            (twitter_result, TWITTER_PROFILE_ACTOR, "tweets"),
            (reddit_result, REDDIT_ACTOR, "posts"),
            (linkedin_result, LINKEDIN_BULK_ACTOR, "profiles"),
            (pages_result, FACEBOOK_PAGES_ACTOR, "pages"),
            (posts_result, FACEBOOK_POSTS_ACTOR, "posts"),
        )
        for result, actor_id, output_key in expected:
            with self.subTest(actor_id=actor_id):
                self.assertFalse(result["success"])
                self.assertFalse(result["configured"])
                self.assertEqual(result["status"], "not_configured")
                self.assertEqual(result["actor_id"], actor_id)
                self.assertEqual(result["reason"], "missing APIFY_API_TOKEN")
                self.assertEqual(result[output_key], [])

        self.assertEqual(client.calls, [])


if __name__ == "__main__":
    unittest.main()
