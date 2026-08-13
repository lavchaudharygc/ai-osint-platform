"""LinkedIn profile/company and public post-search integrations via Apify."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, Literal

from app.config import settings
from app.services.apify_client import ApifyActorClient, ApifyClientError


LinkedInAction = Literal["get-profiles", "get-companies"]
LinkedInQueryMode = Literal["keyword", "name", "url"]


def _profile_slug(value: str) -> str:
    candidate = value.strip()
    if "/in/" in candidate:
        candidate = candidate.split("/in/", 1)[1].split("/", 1)[0].split("?", 1)[0]
    candidate = candidate.strip("/@")
    if not candidate:
        raise ValueError("LinkedIn profile slug cannot be empty")
    return candidate


def _slug_from_url(value: Any) -> str | None:
    if not value:
        return None
    match = re.search(r"linkedin\.com/(?:in|company)/([^/?#]+)", str(value), re.IGNORECASE)
    return match.group(1) if match else None


def normalize_linkedin_item(item: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(item, dict):
        item = {}

    basic_info = item.get("basic_info") or item.get("basicInfo")
    if not isinstance(basic_info, dict):
        basic_info = {}

    stats = item.get("stats")
    if not isinstance(stats, dict):
        stats = {}

    contact_info = item.get("contact_info") or item.get("contactInfo")
    if not isinstance(contact_info, dict):
        contact_info = {}

    first_name = (
        basic_info.get("firstName")
        or basic_info.get("first_name")
        or item.get("firstName")
        or item.get("first_name")
    )
    last_name = (
        basic_info.get("lastName")
        or basic_info.get("last_name")
        or item.get("lastName")
        or item.get("last_name")
    )
    full_name = (
        basic_info.get("fullName")
        or basic_info.get("full_name")
        or basic_info.get("fullname")
        or basic_info.get("name")
        or item.get("fullName")
        or item.get("full_name")
        or item.get("fullname")
        or item.get("name")
        or " ".join(str(v) for v in (first_name, last_name) if v).strip()
    ) or None

    headline = (
        basic_info.get("headline")
        or item.get("headline")
        or item.get("subTitle")
        or item.get("subtitle")
    )

    avatar = (
        basic_info.get("avatar")
        or basic_info.get("profile_picture")
        or basic_info.get("profilePicture")
        or basic_info.get("profilePictureUrl")
        or basic_info.get("profile_picture_url")
        or item.get("avatar")
        or item.get("profilePictureUrl")
        or item.get("profile_picture_url")
        or item.get("profilePicUrl")
        or item.get("profilePicture")
    )

    location = (
        basic_info.get("location")
        or item.get("location")
        or item.get("locationName")
    )

    followers = (
        stats.get("followers")
        or stats.get("followersCount")
        or stats.get("followerCount")
        or item.get("followersCount")
        or item.get("followersCountValue")
        or item.get("followerCount")
        or item.get("followers")
    )

    connections = (
        stats.get("connections")
        or stats.get("connectionsCount")
        or stats.get("connectionCount")
        or item.get("connectionsCount")
        or item.get("connectionsCountValue")
        or item.get("connectionCount")
        or item.get("connections")
    )

    bio = (
        basic_info.get("summary")
        or basic_info.get("about")
        or basic_info.get("bio")
        or item.get("summary")
        or item.get("about")
        or item.get("bio")
    )

    username = (
        basic_info.get("public_identifier")
        or basic_info.get("publicIdentifier")
        or basic_info.get("username")
        or basic_info.get("vanityName")
        or item.get("username")
        or item.get("vanityName")
        or _slug_from_url(item.get("linkedinUrl") or item.get("url"))
    )

    raw_exp = item.get("experience") or basic_info.get("experience")
    experience = raw_exp if isinstance(raw_exp, list) else ([raw_exp] if isinstance(raw_exp, dict) else [])
    current = experience[0] if experience and isinstance(experience[0], dict) else {}

    raw_edu = item.get("education") or item.get("educations") or basic_info.get("education")
    education = raw_edu if isinstance(raw_edu, list) else ([raw_edu] if isinstance(raw_edu, dict) else [])

    email = contact_info.get("email") or item.get("email")
    phone = contact_info.get("phone") or item.get("phone")
    websites = contact_info.get("websites") or item.get("websites") or []

    profile_url = (
        basic_info.get("profile_url")
        or basic_info.get("linkedinUrl")
        or item.get("linkedinUrl")
        or item.get("url")
        or item.get("profile_url")
    )

    provider_status = item.get("status")

    return {
        "username": username,
        "profile_url": profile_url,
        "full_name": full_name,
        "first_name": first_name,
        "last_name": last_name,
        "headline": headline,
        "avatar": avatar,
        "profile_pic_url": avatar,
        "profile_pic_hd": avatar,
        "bio": bio,
        "location": location,
        "followers": followers,
        "follower_count": followers,
        "connections": connections,
        "connections_count": connections,
        "current_role": current.get("title") or current.get("role"),
        "current_company": current.get("companyName") or current.get("company"),
        "experience": experience,
        "education": education,
        "certifications": item.get("certifications") or [],
        "skills": item.get("skills") or basic_info.get("skills") or [],
        "languages": item.get("languages") or [],
        "volunteer": item.get("volunteer") or item.get("volunteering") or [],
        "honors": item.get("honors") or [],
        "organizations": item.get("organizations") or [],
        "projects": item.get("projects") or [],
        "email": email,
        "phone": phone,
        "websites": websites,
        "contact_info": contact_info or {"email": email, "phone": phone, "websites": websites},
        "basic_info": basic_info or {
            "fullName": full_name,
            "headline": headline,
            "avatar": avatar,
            "location": location,
            "summary": bio,
        },
        "stats": stats or {
            "followers": followers,
            "connections": connections,
        },
        "provider_status": provider_status,
        "not_found_reason": item.get("reason"),
        "raw_data": item,
    }


normalizeLinkedInItem = normalize_linkedin_item


async def fetch_linkedin(
    username_or_url: str,
    client: ApifyActorClient | None = None,
    actor: str | None = None,
) -> dict[str, Any]:
    """Fetch LinkedIn profile data via Apify actor (default: apimaestro~linkedin-profile-detail)."""
    apify_client = client or ApifyActorClient()
    if not apify_client.is_configured():
        return {
            "success": False,
            "configured": False,
            "exists": None,
            "platform": "linkedin",
            "status": "not_configured",
            "reason": "APIFY_TOKEN missing",
            "error": "APIFY_TOKEN missing",
            "recent_posts": [],
        }

    slug = _profile_slug(username_or_url)
    profile_url = f"https://www.linkedin.com/in/{slug}/"
    primary_actor = (
        actor
        or getattr(settings, "apify_linkedin_actor", None)
        or getattr(settings, "apify_linkedin_profile_actor_id", "apimaestro/linkedin-profile-detail")
    )
    primary_actor = primary_actor.replace("~", "/")

    actors_to_try = [
        (primary_actor, {"username": slug, "url": profile_url, "profileUrl": profile_url}),
        ("harvestapi/linkedin-profile-scraper", {"queries": [profile_url], "urls": [profile_url]}),
        ("dev_fusion/linkedin-profile-scraper", {"profileUrls": [profile_url], "urls": [profile_url]}),
    ]

    last_exc = None
    for target_actor, run_input in actors_to_try:
        try:
            run = await apify_client.run_actor(
                target_actor,
                run_input,
                dataset_limit=1,
            )
            if run.items:
                item = run.items[0]
                if isinstance(item, dict) and (item.get("error") or "limit" in str(item.get("message", "")).lower() or not (item.get("fullName") or item.get("full_name") or item.get("basic_info") or item.get("basicInfo") or item.get("name") or item.get("headline"))):
                    last_exc = Exception(str(item.get("error") or item.get("message") or "Empty profile dataset"))
                    continue
                normalized = normalize_linkedin_item(item)
                return {
                    "success": True,
                    "configured": True,
                    "exists": True,
                    "platform": "linkedin",
                    "status": "completed",
                    "source": f"apify_linkedin_{target_actor.replace('/', '_').replace('~', '_')}",
                    "actor_id": target_actor,
                    "username": normalized.get("username") or slug,
                    "profile_url": normalized.get("profile_url") or profile_url,
                    **normalized,
                    "recent_posts": [],
                    "post_count": None,
                    "run": run.as_dict(include_items=False),
                    "raw_data": run.items,
                    "scraped_at": datetime.now(UTC).isoformat(),
                }
        except ApifyClientError as exc:
            last_exc = exc
            continue
        except Exception as exc:
            last_exc = exc
            continue

    # Try bulk lookup as final fallback if primary actors returned empty or failed
    try:
        bulk_svc = LinkedInApifyService(client=apify_client)
        result = await bulk_svc.bulk_lookup(
            action="get-profiles",
            keywords=[profile_url],
            query_mode="url",
            limit=1,
        )
        profiles = result.get("profiles") or []
        profile = profiles[0] if profiles else None
        if isinstance(profile, dict) and profile.get("provider_status") != "NOT_FOUND" and (profile.get("full_name") or profile.get("headline") or profile.get("basic_info", {}).get("fullName")):
            return {
                **result,
                **profile,
                "success": True,
                "exists": True,
                "username": profile.get("username") or slug,
                "profile_url": profile.get("profile_url") or profile_url,
                "recent_posts": [],
                "post_count": None,
            }
    except Exception:
        pass

    if last_exc:
        return {
            "success": False,
            "configured": True,
            "exists": None,
            "platform": "linkedin",
            "username": slug,
            "profile_url": profile_url,
            "status": "provider_error",
            "source": "apify",
            "actor_id": primary_actor,
            "error": last_exc.as_dict() if isinstance(last_exc, ApifyClientError) else {"message": str(last_exc)},
            "recent_posts": [],
        }

    return {
        "success": False,
        "configured": True,
        "exists": None,
        "platform": "linkedin",
        "username": slug,
        "profile_url": profile_url,
        "status": "empty_dataset",
        "source": "apify",
        "actor_id": primary_actor,
        "recent_posts": [],
    }


fetchLinkedIn = fetch_linkedin


class LinkedInApifyService:
    """Use API Maestro LinkedIn Profile scraper and post search."""

    PROFILE_MAX_PROVIDER_CALLS = 3

    def __init__(self, client: ApifyActorClient | None = None) -> None:
        self.client = client or ApifyActorClient()
        self.profile_actor_id = (
            getattr(settings, "apify_linkedin_actor", None)
            or getattr(settings, "apify_linkedin_profile_actor_id", "apimaestro/linkedin-profile-detail")
        )
        self.posts_actor_id = getattr(settings, "apify_linkedin_posts_actor_id", "bebity/linkedin-post-search-scraper")

    def is_configured(self) -> bool:
        return self.client.is_configured()

    def provider_call_units(self) -> int:
        """Reserve the primary profile Actor plus both bounded fallbacks."""
        return self.PROFILE_MAX_PROVIDER_CALLS if self.is_configured() else 0

    async def get_profile(self, username: str) -> dict[str, Any]:
        return await fetch_linkedin(username, client=self.client, actor=self.profile_actor_id)

    async def bulk_lookup(
        self,
        *,
        action: LinkedInAction,
        keywords: list[str],
        query_mode: LinkedInQueryMode = "keyword",
        limit: int = 5,
        locations: list[str] | None = None,
    ) -> dict[str, Any]:
        clean_keywords = [value.strip() for value in keywords if value.strip()]
        if not clean_keywords:
            raise ValueError("At least one LinkedIn query is required")
        if action not in {"get-profiles", "get-companies"}:
            raise ValueError("Unsupported LinkedIn bulk action")
        if query_mode not in {"keyword", "name", "url"}:
            raise ValueError("Unsupported LinkedIn query mode")

        # Bebity v10 auto-detects search terms, names, and direct URLs from
        # each keyword. Keep query_mode for API compatibility, but do not send
        # the removed legacy isUrl/isName fields to the Actor.
        run_input = {
            "action": action,
            "keywords": clean_keywords,
            "queries": clean_keywords,
            "urls": clean_keywords,
            "profileUrls": clean_keywords,
            "limit": limit,
            "location": [value.strip() for value in (locations or []) if value.strip()],
        }
        output_key = "profiles" if action == "get-profiles" else "companies"
        if not self.is_configured():
            return self._not_configured(self.profile_actor_id, output_key)

        dataset_limit = min(10_000, max(1, len(clean_keywords) * limit))
        try:
            run = await self.client.run_actor(
                self.profile_actor_id,
                run_input,
                dataset_limit=dataset_limit,
            )
        except ApifyClientError as exc:
            return self._error(exc, self.profile_actor_id, output_key)

        if action == "get-profiles":
            records = [self._normalize_profile(item) for item in run.items]
        else:
            records = [self._normalize_company(item) for item in run.items]
        found_records = [item for item in records if item.get("provider_status") != "NOT_FOUND"]
        return {
            "success": bool(found_records),
            "configured": True,
            "exists": True if found_records else None,
            "platform": "linkedin",
            "status": "completed" if found_records else "empty_dataset",
            "source": "apify_linkedin_bulk_scraper",
            "actor_id": self.profile_actor_id,
            "action": action,
            output_key: records,
            "total": len(records),
            "run": run.as_dict(include_items=False),
            "raw_data": run.items,
            "scraped_at": datetime.now(UTC).isoformat(),
        }

    async def search_posts(
        self,
        *,
        keyword: str,
        sort_type: str = "relevance",
        page_number: int = 1,
        date_filter: str = "",
        limit: int = 50,
        total_posts: int | None = None,
        company_urns: str | None = None,
        author_company_urns: str | None = None,
        author_industry_urns: str | None = None,
        author_job_title: str | None = None,
        member_urns: str | None = None,
    ) -> dict[str, Any]:
        clean_keyword = keyword.strip()
        if not clean_keyword:
            raise ValueError("LinkedIn post-search keyword cannot be empty")
        run_input: dict[str, Any] = {
            "keyword": clean_keyword,
            "sort_type": sort_type,
            "page_number": page_number,
            "date_filter": date_filter,
            "limit": limit,
        }
        optional_values = {
            "total_posts": total_posts,
            "company_urns": company_urns,
            "author_company_urns": author_company_urns,
            "author_industry_urns": author_industry_urns,
            "author_job_title": author_job_title,
            "member_urns": member_urns,
        }
        run_input.update(
            {
                key: value.strip() if isinstance(value, str) else value
                for key, value in optional_values.items()
                if value is not None and (not isinstance(value, str) or value.strip())
            }
        )

        if not self.is_configured():
            return self._not_configured(self.posts_actor_id, "posts")
        dataset_limit = total_posts or limit
        try:
            run = await self.client.run_actor(
                self.posts_actor_id,
                run_input,
                dataset_limit=dataset_limit,
            )
        except ApifyClientError as exc:
            return self._error(exc, self.posts_actor_id, "posts")

        posts = [self._normalize_post(item) for item in run.items]
        hashtags = sorted(
            {
                hashtag
                for post in posts
                for hashtag in post.get("hashtags", [])
                if hashtag
            }
        )
        return {
            "success": True,
            "configured": True,
            "platform": "linkedin",
            "status": "completed",
            "source": "apify_linkedin_posts_search",
            "actor_id": self.posts_actor_id,
            "keyword": clean_keyword,
            "posts": posts,
            "recent_posts": posts,
            "all_hashtags": hashtags,
            "total": len(posts),
            "run": run.as_dict(include_items=False),
            "raw_data": run.items,
            "scraped_at": datetime.now(UTC).isoformat(),
        }

    _normalize_profile = staticmethod(normalize_linkedin_item)

    @staticmethod
    def _normalize_company(item: dict[str, Any]) -> dict[str, Any]:
        headquarter = item.get("headquarter") if isinstance(item.get("headquarter"), dict) else {}
        phone = item.get("phone")
        phone_number = phone.get("number") if isinstance(phone, dict) else phone
        return {
            "username": item.get("vanityName") or LinkedInApifyService._slug_from_url(item.get("linkedinUrl")),
            "company_id": item.get("companyId"),
            "profile_url": item.get("linkedinUrl"),
            "full_name": item.get("name"),
            "name": item.get("name"),
            "bio": item.get("description"),
            "tagline": item.get("tagline"),
            "industry": item.get("industry"),
            "website": item.get("websiteUrl"),
            "phone": phone_number,
            "employee_count": item.get("employeeCount"),
            "employee_count_range": item.get("employeeCountRange"),
            "founded_year": item.get("foundedYear"),
            "specialities": item.get("specialities") or [],
            "location": headquarter,
            "locations": item.get("locations") or [],
            "profile_pic_url": item.get("logoUrl"),
            "cover_image_url": item.get("coverImageUrl"),
            "follower_count": item.get("followersCount"),
            "page_type": item.get("pageType"),
            "is_verified": item.get("verified"),
            "is_active": item.get("active"),
            "job_search_url": item.get("jobSearchUrl"),
            "call_to_action": item.get("callToAction"),
            "hashtags": item.get("hashtags") or [],
            "provider_status": item.get("status"),
            "not_found_reason": item.get("reason"),
            "raw_data": item,
        }

    @staticmethod
    def _normalize_post(item: dict[str, Any]) -> dict[str, Any]:
        author = item.get("author") if isinstance(item.get("author"), dict) else {}
        author_details = (
            item.get("authorDetails") if isinstance(item.get("authorDetails"), dict) else {}
        )
        text = (
            item.get("text")
            or item.get("content")
            or item.get("postText")
            or item.get("commentary")
        )
        hashtags = item.get("hashtags")
        if not isinstance(hashtags, list):
            hashtags = re.findall(r"(?<!\w)#([\w-]+)", str(text or ""))
        reactions = item.get("reactions")
        return {
            "id": item.get("activityId") or item.get("activity_id") or item.get("postId") or item.get("urn"),
            "url": item.get("postUrl") or item.get("linkedinUrl") or item.get("url"),
            "text": text,
            "created_at": item.get("postedAt") or item.get("posted_at") or item.get("publishedAt") or item.get("date"),
            "author": {
                "name": item.get("authorName") or author.get("name") or author_details.get("name"),
                "profile_url": item.get("authorProfileUrl") or author.get("profileUrl") or author_details.get("linkedinUrl"),
                "headline": item.get("authorHeadline") or author.get("headline") or author_details.get("headline"),
                "profile_pic_url": item.get("authorImage") or author.get("profilePicture") or author_details.get("profilePictureUrl"),
            },
            "reaction_count": LinkedInApifyService._first_not_none(
                item.get("reactionsCount"),
                item.get("numLikes"),
                item.get("likeCount"),
                item.get("totalReactionCount"),
            ),
            "comment_count": LinkedInApifyService._first_not_none(
                item.get("commentsCount"),
                item.get("numComments"),
                item.get("commentCount"),
                item.get("totalComments"),
            ),
            "repost_count": LinkedInApifyService._first_not_none(
                item.get("repostsCount"),
                item.get("numShares"),
                item.get("shareCount"),
            ),
            "reactions": reactions if isinstance(reactions, (dict, list)) else None,
            "media": item.get("media") or item.get("images") or item.get("attachments") or [],
            "hashtags": [str(value).lstrip("#") for value in hashtags],
            "raw_data": item,
        }

    @staticmethod
    def _profile_slug(value: str) -> str:
        candidate = value.strip()
        if "/in/" in candidate:
            candidate = candidate.split("/in/", 1)[1].split("/", 1)[0]
        candidate = candidate.strip("/@")
        if not candidate:
            raise ValueError("LinkedIn profile slug cannot be empty")
        return candidate

    @staticmethod
    def _slug_from_url(value: Any) -> str | None:
        if not value:
            return None
        match = re.search(r"linkedin\.com/(?:in|company)/([^/?#]+)", str(value), re.IGNORECASE)
        return match.group(1) if match else None

    @staticmethod
    def _first_not_none(*values: Any) -> Any:
        return next((value for value in values if value is not None), None)

    @staticmethod
    def _not_configured(actor_id: str, output_key: str) -> dict[str, Any]:
        return {
            "success": False,
            "configured": False,
            "exists": None,
            "platform": "linkedin",
            "status": "not_configured",
            "source": "apify",
            "actor_id": actor_id,
            "reason": "missing APIFY_API_TOKEN",
            output_key: [],
            "total": 0,
        }

    @staticmethod
    def _error(
        exc: ApifyClientError,
        actor_id: str,
        output_key: str,
    ) -> dict[str, Any]:
        return {
            "success": False,
            "configured": True,
            "exists": None,
            "platform": "linkedin",
            "status": "provider_error",
            "source": "apify",
            "actor_id": actor_id,
            "error": exc.as_dict(),
            output_key: [],
            "total": 0,
        }
