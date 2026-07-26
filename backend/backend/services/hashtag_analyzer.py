"""Offline hashtag summary over evidence already collected by the investigation."""

from typing import Any


class HashtagAnalyzer:
    """Describe observed hashtags without issuing another provider request."""

    async def analyze_hashtags(self, hashtags: list[str], username: str) -> dict[str, Any]:
        observed = list(dict.fromkeys(tag.strip().lstrip("#") for tag in hashtags if tag.strip()))
        results: dict[str, Any] = {
            tag: {
                "platform": "collected_evidence",
                "recent_users": [],
                "total_tweets": 0,
                "status": "local_evidence_only",
                "reason": (
                    "No automatic hashtag search was run; X collection is routed "
                    "only through the selected Apify actor."
                ),
            }
            for tag in observed
        }
        return {
            "original_username": username,
            "hashtags_analyzed": observed,
            "platforms_checked": [],
            "network_calls": 0,
            "findings": results,
            "potential_connections": self._extract_potential_connections(results),
        }

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
