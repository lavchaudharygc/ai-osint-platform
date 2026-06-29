"""Hashtag reverse lookup and connection analysis."""

from typing import Any

import httpx

from backend.core.config import settings


class HashtagAnalyzer:
    """Find related accounts from hashtags using Twitter/X recent search when configured."""

    def __init__(self) -> None:
        self.twitter_bearer_token = settings.twitter_bearer_token

    async def analyze_hashtags(self, hashtags: list[str], username: str) -> dict[str, Any]:
        results: dict[str, Any] = {}
        for tag in hashtags[:5]:
            tag_results = await self._search_hashtag_twitter(tag)
            results[tag] = {
                "platform": "twitter",
                "recent_users": tag_results.get("users", []),
                "total_tweets": tag_results.get("count", 0),
                "status": tag_results.get("status", "completed"),
                "error": tag_results.get("error"),
            }
        return {
            "original_username": username,
            "hashtags_analyzed": list(results.keys()),
            "platforms_checked": ["twitter"],
            "findings": results,
            "potential_connections": self._extract_potential_connections(results),
        }

    async def _search_hashtag_twitter(self, hashtag: str) -> dict[str, Any]:
        if not self.twitter_bearer_token:
            return {"status": "not_configured", "error": "TWITTER_BEARER_TOKEN not configured", "users": [], "count": 0}
        url = "https://api.twitter.com/2/tweets/search/recent"
        params = {"query": f"#{hashtag} -is:retweet", "max_results": 10, "tweet.fields": "author_id,created_at"}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(url, headers={"Authorization": f"Bearer {self.twitter_bearer_token}"}, params=params)
            if response.status_code == 200:
                data = response.json()
                users = sorted({tweet.get("author_id") for tweet in data.get("data", []) if tweet.get("author_id")})
                return {"status": "completed", "users": users, "count": data.get("meta", {}).get("result_count", 0)}
            return {"status": "error", "error": f"Twitter API returned {response.status_code}", "users": [], "count": 0}
        except httpx.HTTPError as exc:
            return {"status": "error", "error": str(exc), "users": [], "count": 0}

    def _extract_potential_connections(self, results: dict[str, Any]) -> list[dict[str, Any]]:
        user_frequency: dict[str, dict[str, Any]] = {}
        for tag, data in results.items():
            for user in data.get("recent_users", []):
                user_frequency.setdefault(user, {"count": 0, "hashtags": []})
                user_frequency[user]["count"] += 1
                user_frequency[user]["hashtags"].append(tag)
        return [
            {"user": user, "frequency": data["count"], "hashtags": data["hashtags"]}
            for user, data in user_frequency.items()
            if data["count"] >= 2
        ]
