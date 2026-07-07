"""Instagram data extraction service."""

from typing import Any

class InstagramDataService:
    """Instagram data extraction service.
    
    Instaloader local scraping has been disabled to prevent rate limits and 403 Forbidden loops.
    """

    async def get_profile(self, username: str) -> dict[str, Any]:
        """Async wrapper used by FastAPI investigation endpoints."""
        return {
            "success": False,
            "platform": "instagram",
            "username": username,
            "error": "Instaloader local scraping is disabled. Falling back to APIs.",
        }

    def get_full_profile(self, username: str) -> dict[str, Any]:
        """Extract available Instagram profile data and recent public posts."""
        return {
            "success": False,
            "platform": "instagram",
            "username": username,
            "error": "Instaloader local scraping is disabled. Falling back to APIs.",
        }

    @staticmethod
    def _catalog_coverage_notes() -> dict[str, str]:
        return {
            "account_created": "Instagram does not expose exact creation date through public profile scraping.",
            "tagged_photos": "Requires additional scrape and depends on privacy/session access.",
            "comments_made_by_subject": "Hard/publicly limited; may require authorization and separate collection.",
            "story_highlights": "Requires dedicated endpoint/session support; not extracted by current instaloader flow.",
            "reels_igtv_count": "Not exposed as a stable public profile field in current flow.",
            "account_country_region": "May appear in About This Account; not exposed by current instaloader object.",
            "former_usernames": "May appear in About This Account; not exposed by current instaloader object.",
            "active_ads": "Requires Meta ad/about endpoints; not extracted by current public profile flow.",
            "followers_list": "Catalog marks full list as not feasible at scale due login/rate limits.",
            "following_list": "Catalog marks full list as not feasible at scale due login/rate limits.",
            "likes_on_others_posts": "Not publicly available in a reliable way.",
            "post_image_exif_metadata": "Instagram strips EXIF metadata from served media.",
            "direct_message_content": "Private data; requires legal process and is not available via OSINT scraping.",
        }
