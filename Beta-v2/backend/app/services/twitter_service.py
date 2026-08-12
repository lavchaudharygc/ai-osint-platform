"""Twitter/X scraping service for Beta-v2 using Apify."""

import logging
from typing import Any, Dict, List
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

_APIFY_BASE = "https://api.apify.com/v2"
_TWITTER_ACTORS = [
    ("apidojo/twitter-scraper-lite", lambda h: {"twitterHandles": [h], "maxItems": 1, "mode": "profile"}),
    ("epctex/twitter-profile-scraper", lambda h: {"startUrls": [f"https://x.com/{h}"], "maxItems": 1}),
]


class TwitterService:
    def __init__(self):
        self.apify_token = settings.apify_api_token

    def _apify_configured(self) -> bool:
        return bool(self.apify_token)

    async def _apify_run_sync(self, actor_id: str, payload: dict, timeout: float = 120.0) -> List[Dict[str, Any]]:
        url = f"{_APIFY_BASE}/acts/{actor_id}/run-sync-get-dataset-items"
        headers = {"Authorization": f"Bearer {self.apify_token}"}
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(url, headers=headers, json=payload)
        if r.status_code not in (200, 201):
            logger.warning("Apify Twitter actor %s returned HTTP %d", actor_id, r.status_code)
            return []
        items = r.json()
        return items if isinstance(items, list) else []

    async def fetch_profile_and_tweets(self, username: str) -> Dict[str, Any]:
        """Fetch X (Twitter) profile data and recent tweets."""
        if not self._apify_configured():
            return {"success": False, "error": "Apify token not configured"}

        clean_handle = username.lstrip("@").strip()
        last_err = None

        for actor_id, payload_fn in _TWITTER_ACTORS:
            try:
                payload = payload_fn(clean_handle)
                items = await self._apify_run_sync(actor_id, payload)
                if items and isinstance(items[0], dict):
                    item = items[0]
                    name = item.get("name") or item.get("userName") or item.get("screen_name") or clean_handle
                    screen_name = item.get("screen_name") or item.get("twitterHandle") or item.get("username") or clean_handle
                    description = item.get("description") or item.get("biography") or ""
                    profile_img = item.get("profile_image_url_https") or item.get("profilePicture") or item.get("avatar")
                    followers = item.get("followers_count") or item.get("followers") or 0
                    following = item.get("friends_count") or item.get("following") or 0
                    statuses_count = item.get("statuses_count") or item.get("tweetsCount") or 0
                    
                    tweets = []
                    for tweet_item in items:
                        if isinstance(tweet_item, dict) and (tweet_item.get("full_text") or tweet_item.get("text")):
                            tweets.append({
                                "text": tweet_item.get("full_text") or tweet_item.get("text"),
                                "created_at": tweet_item.get("created_at") or tweet_item.get("createdAt"),
                                "like_count": tweet_item.get("favorite_count") or tweet_item.get("likesCount") or 0,
                                "retweet_count": tweet_item.get("retweet_count") or tweet_item.get("retweetsCount") or 0,
                            })

                    return {
                        "success": True,
                        "platform": "twitter",
                        "username": screen_name,
                        "full_name": name,
                        "bio": description,
                        "profile_pic_url": profile_img,
                        "follower_count": followers,
                        "following_count": following,
                        "post_count": statuses_count,
                        "tweets": tweets[:10],
                        "source": "apify",
                    }
            except Exception as e:
                logger.warning("Failed fetching Twitter via %s: %s", actor_id, e)
                last_err = e

        return {"success": False, "error": str(last_err or "No profile found on Apify X scraper")}
