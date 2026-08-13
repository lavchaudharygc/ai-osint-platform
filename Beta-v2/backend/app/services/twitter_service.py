"""Twitter/X scraping service for Beta-v2 using Apify."""

import logging
from typing import Any, Dict, List
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

_APIFY_BASE = "https://api.apify.com/v2"
_TWITTER_ACTORS = [
    ("kaitoeasyapi/premium-x-follower-scraper-following-data", lambda h: {"usernames": [h], "getFollowers": True, "getFollowing": True}),
]


class TwitterService:
    def __init__(self):
        self.apify_token = settings.apify_api_token

    def _apify_configured(self) -> bool:
        return bool(self.apify_token)

    async def _apify_run_sync(self, actor_id: str, payload: dict, timeout: float = 120.0) -> List[Dict[str, Any]]:
        # Convert owner/name format to owner~name for REST API compatibility
        rest_actor_id = actor_id.replace("/", "~")
        url = f"{_APIFY_BASE}/acts/{rest_actor_id}/run-sync-get-dataset-items"
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
                if not items:
                    continue

                # Filter out mock_user warning objects
                real_items = [it for it in items if isinstance(it, dict) and it.get("type") != "mock_user"]
                
                # Group followers and following
                followers = [it for it in real_items if it.get("type") == "follower"]
                following = [it for it in real_items if it.get("type") == "following"]

                name = clean_handle
                screen_name = clean_handle
                description = f"X Profile verified. Discovered {len(followers)} followers and {len(following)} following connections."
                profile_img = "https://abs.twimg.com/sticky/default_profile_images/default_profile_normal.png"

                if real_items:
                    target_info = real_items[0]
                    screen_name = target_info.get("target_username") or clean_handle

                tweets = []
                for it in real_items:
                    conn_type = it.get("type", "").upper()
                    c_name = it.get("name") or "N/A"
                    c_screen = it.get("screen_name") or "N/A"
                    c_desc = it.get("description") or "No description."
                    c_loc = it.get("location")
                    loc_str = f" ({c_loc})" if c_loc else ""
                    
                    tweets.append({
                        "text": f"[{conn_type}] {c_name} (@{c_screen}) · {c_desc}{loc_str}",
                        "created_at": it.get("created_at"),
                        "like_count": it.get("followers_count") or 0,
                        "retweet_count": it.get("friends_count") or 0,
                    })

                return {
                    "success": True,
                    "platform": "twitter",
                    "username": screen_name,
                    "full_name": name,
                    "bio": description,
                    "profile_pic_url": profile_img,
                    "follower_count": len(followers),
                    "following_count": len(following),
                    "post_count": len(real_items),
                    "tweets": tweets[:20],
                    "source": "apify",
                }
            except Exception as e:
                logger.warning("Failed fetching Twitter via %s: %s", actor_id, e)
                last_err = e

        return {"success": False, "error": str(last_err or "No profile found on Apify X scraper")}
