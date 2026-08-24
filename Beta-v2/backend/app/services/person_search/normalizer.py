"""Normalize search-engine rows into conservative public-profile candidates."""

from __future__ import annotations

from collections.abc import Iterable
import re
import unicodedata
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from app.services.image_proxy_service import hostname_is_allowed


class PersonSearchNormalizer:
    """Accept only canonical profile URL shapes on an approved host allowlist."""

    MAX_URL_LENGTH = 2_048
    PLATFORM_HOSTS: dict[str, frozenset[str]] = {
        "linkedin": frozenset({"linkedin.com", "www.linkedin.com"}),
        "github": frozenset({"github.com", "www.github.com"}),
        "twitter": frozenset(
            {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}
        ),
        "instagram": frozenset({"instagram.com", "www.instagram.com"}),
        "facebook": frozenset(
            {"facebook.com", "www.facebook.com", "m.facebook.com"}
        ),
        "tiktok": frozenset({"tiktok.com", "www.tiktok.com"}),
        "reddit": frozenset(
            {"reddit.com", "www.reddit.com", "old.reddit.com"}
        ),
        "youtube": frozenset(
            {"youtube.com", "www.youtube.com", "m.youtube.com"}
        ),
        "telegram": frozenset(
            {"t.me", "www.t.me", "telegram.me", "www.telegram.me"}
        ),
    }
    HOST_TO_PLATFORM = {
        host: platform
        for platform, hosts in PLATFORM_HOSTS.items()
        for host in hosts
    }
    RESERVED: dict[str, frozenset[str]] = {
        "github": frozenset(
            {
                "about",
                "apps",
                "collections",
                "contact",
                "events",
                "explore",
                "features",
                "issues",
                "join",
                "login",
                "marketplace",
                "new",
                "orgs",
                "pricing",
                "pulls",
                "search",
                "security",
                "settings",
                "site",
                "topics",
                "trending",
            }
        ),
        "twitter": frozenset(
            {
                "about",
                "compose",
                "explore",
                "hashtag",
                "home",
                "i",
                "intent",
                "login",
                "messages",
                "notifications",
                "privacy",
                "search",
                "settings",
                "share",
                "signup",
            }
        ),
        "instagram": frozenset(
            {
                "about",
                "accounts",
                "challenge",
                "developer",
                "direct",
                "directory",
                "explore",
                "p",
                "reel",
                "reels",
                "stories",
                "tv",
                "web",
            }
        ),
        "facebook": frozenset(
            {
                "about",
                "business",
                "events",
                "friends",
                "groups",
                "help",
                "home",
                "login",
                "marketplace",
                "messages",
                "notifications",
                "pages",
                "people",
                "photo",
                "photos",
                "plugins",
                "privacy",
                "reel",
                "search",
                "settings",
                "share",
                "watch",
            }
        ),
        "telegram": frozenset(
            {
                "addstickers",
                "blog",
                "faq",
                "iv",
                "joinchat",
                "login",
                "proxy",
                "s",
                "share",
                "socks",
            }
        ),
    }

    @classmethod
    def normalize_results(
        cls,
        results: Iterable[dict[str, Any]],
        *,
        full_name: str,
        platforms: Iterable[str],
        max_profiles: int,
    ) -> list[dict[str, Any]]:
        """Return bounded, deduplicated candidates in discovery order."""

        requested = {str(platform).strip().casefold() for platform in platforms}
        limit = max(1, min(int(max_profiles), 50))
        candidates: dict[tuple[str, str], dict[str, Any]] = {}
        order: list[tuple[str, str]] = []

        for raw_result in results:
            if not isinstance(raw_result, dict):
                continue
            parsed = cls._parse_profile_url(
                raw_result.get("url")
                or raw_result.get("link")
                or raw_result.get("href")
            )
            if parsed is None:
                continue
            platform, username, profile_url = parsed
            if platform not in requested:
                continue
            incoming = cls._candidate_from_result(
                raw_result,
                full_name=full_name,
                platform=platform,
                username=username,
                profile_url=profile_url,
            )
            key = cls._identity_key(platform, username, profile_url)
            current = candidates.get(key)
            if current is None:
                candidates[key] = incoming
                order.append(key)
            else:
                cls._merge_candidate(current, incoming)

        normalized: list[dict[str, Any]] = []
        for key in order[:limit]:
            candidate = candidates[key]
            candidate.pop("_name_match", None)
            candidate["discovery_rank"] = len(normalized) + 1
            normalized.append(candidate)
        return normalized

    @classmethod
    def _candidate_from_result(
        cls,
        result: dict[str, Any],
        *,
        full_name: str,
        platform: str,
        username: str,
        profile_url: str,
    ) -> dict[str, Any]:
        title = cls._clean_text(result.get("title"), 300)
        snippet = cls._clean_text(
            result.get("snippet") or result.get("description"),
            1_000,
        )
        title_match = bool(title and cls._contains_exact_name(title, full_name))
        snippet_match = bool(
            snippet and cls._contains_exact_name(snippet, full_name)
        )
        match_basis = ["public_profile_url", "exact_name_query"]
        if title_match:
            match_basis.append("exact_name_in_title")
        if snippet_match:
            match_basis.append("exact_name_in_snippet")
        return {
            "platform": platform,
            "profile_url": profile_url,
            "username": username,
            "full_name": full_name if title_match or snippet_match else None,
            "display_name": full_name if title_match else title,
            "title": title,
            "snippet": snippet,
            "photo_url": cls._safe_image_url(
                result.get("thumbnail") or result.get("thumbnail_url")
            ),
            "source": "google_serpapi",
            "discovery_rank": 1,
            "match_basis": match_basis,
            "identity_status": "unverified_candidate",
            "_name_match": title_match or snippet_match,
        }

    @staticmethod
    def _merge_candidate(
        current: dict[str, Any], incoming: dict[str, Any]
    ) -> None:
        if incoming.get("_name_match") and not current.get("_name_match"):
            for key in ("full_name", "display_name", "title"):
                if incoming.get(key):
                    current[key] = incoming[key]
            current["_name_match"] = True
        if len(str(incoming.get("snippet") or "")) > len(
            str(current.get("snippet") or "")
        ):
            current["snippet"] = incoming.get("snippet")
        if not current.get("photo_url") and incoming.get("photo_url"):
            current["photo_url"] = incoming["photo_url"]
        bases = list(current.get("match_basis") or [])
        for basis in incoming.get("match_basis") or []:
            if basis not in bases:
                bases.append(basis)
        current["match_basis"] = bases

    @classmethod
    def _parse_profile_url(cls, value: Any) -> tuple[str, str, str] | None:
        if not isinstance(value, str):
            return None
        candidate = value.strip()
        if not candidate or len(candidate) > cls.MAX_URL_LENGTH:
            return None
        try:
            parsed = urlparse(candidate)
            port = parsed.port
        except ValueError:
            return None
        if (
            parsed.scheme.casefold() not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or port is not None
        ):
            return None
        platform = cls.HOST_TO_PLATFORM.get(parsed.hostname.casefold())
        if platform is None:
            return None
        encoded_path = parsed.path or "/"
        if "\\" in encoded_path or re.search(
            r"%2f|%5c", encoded_path, flags=re.IGNORECASE
        ):
            return None
        path = unquote(encoded_path)
        if "\\" in path or "//" in path:
            return None
        segments = [segment for segment in path.strip("/").split("/") if segment]
        if any(segment in {".", ".."} for segment in segments):
            return None
        parser = getattr(cls, f"_parse_{platform}")
        return parser(segments, parsed.query)

    @classmethod
    def _parse_linkedin(
        cls, segments: list[str], _query: str
    ) -> tuple[str, str, str] | None:
        if len(segments) != 2 or segments[0].casefold() != "in":
            return None
        username = cls._valid_username(segments[1], r"[A-Za-z0-9_-]{1,100}")
        if not username:
            return None
        return "linkedin", username, f"https://www.linkedin.com/in/{username}/"

    @classmethod
    def _parse_github(
        cls, segments: list[str], _query: str
    ) -> tuple[str, str, str] | None:
        if len(segments) != 1:
            return None
        username = cls._valid_username(
            segments[0], r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?"
        )
        if not username or username.casefold() in cls.RESERVED["github"]:
            return None
        return "github", username, f"https://github.com/{username}"

    @classmethod
    def _parse_twitter(
        cls, segments: list[str], _query: str
    ) -> tuple[str, str, str] | None:
        if len(segments) != 1:
            return None
        username = cls._valid_username(segments[0], r"[A-Za-z0-9_]{1,15}")
        if not username or username.casefold() in cls.RESERVED["twitter"]:
            return None
        return "twitter", username, f"https://x.com/{username}"

    @classmethod
    def _parse_instagram(
        cls, segments: list[str], _query: str
    ) -> tuple[str, str, str] | None:
        if len(segments) != 1:
            return None
        username = cls._valid_username(segments[0], r"[A-Za-z0-9._]{1,30}")
        if not username or username.casefold() in cls.RESERVED["instagram"]:
            return None
        return "instagram", username, f"https://www.instagram.com/{username}/"

    @classmethod
    def _parse_facebook(
        cls, segments: list[str], query: str
    ) -> tuple[str, str, str] | None:
        if len(segments) != 1:
            return None
        first = segments[0]
        if first.casefold() == "profile.php":
            identifiers = parse_qs(query, keep_blank_values=False).get("id", [])
            if len(identifiers) != 1 or not re.fullmatch(
                r"[0-9]{3,30}", identifiers[0]
            ):
                return None
            username = identifiers[0]
            return (
                "facebook",
                username,
                f"https://www.facebook.com/profile.php?id={username}",
            )
        if first.casefold().endswith(".php"):
            return None
        username = cls._valid_username(first, r"[A-Za-z0-9.]{3,100}")
        if not username or username.casefold() in cls.RESERVED["facebook"]:
            return None
        return "facebook", username, f"https://www.facebook.com/{username}"

    @classmethod
    def _parse_tiktok(
        cls, segments: list[str], _query: str
    ) -> tuple[str, str, str] | None:
        if len(segments) != 1 or not segments[0].startswith("@"):
            return None
        username = cls._valid_username(segments[0][1:], r"[A-Za-z0-9._]{2,30}")
        if not username:
            return None
        return "tiktok", username, f"https://www.tiktok.com/@{username}"

    @classmethod
    def _parse_reddit(
        cls, segments: list[str], _query: str
    ) -> tuple[str, str, str] | None:
        if len(segments) != 2 or segments[0].casefold() not in {"user", "u"}:
            return None
        username = cls._valid_username(segments[1], r"[A-Za-z0-9_-]{3,20}")
        if not username:
            return None
        return "reddit", username, f"https://www.reddit.com/user/{username}"

    @classmethod
    def _parse_youtube(
        cls, segments: list[str], _query: str
    ) -> tuple[str, str, str] | None:
        if len(segments) == 1 and segments[0].startswith("@"):
            username = cls._valid_username(
                segments[0][1:], r"[A-Za-z0-9._-]{3,100}"
            )
            if username:
                return "youtube", username, f"https://www.youtube.com/@{username}"
            return None
        if len(segments) != 2 or segments[0].casefold() not in {
            "channel",
            "user",
            "c",
        }:
            return None
        namespace = segments[0].casefold()
        pattern = (
            r"UC[A-Za-z0-9_-]{22}"
            if namespace == "channel"
            else r"[A-Za-z0-9._-]{3,100}"
        )
        username = cls._valid_username(segments[1], pattern)
        if not username:
            return None
        return (
            "youtube",
            username,
            f"https://www.youtube.com/{namespace}/{username}",
        )

    @classmethod
    def _parse_telegram(
        cls, segments: list[str], _query: str
    ) -> tuple[str, str, str] | None:
        if len(segments) != 1 or segments[0].startswith("+"):
            return None
        username = cls._valid_username(segments[0], r"[A-Za-z][A-Za-z0-9_]{4,31}")
        if not username or username.casefold() in cls.RESERVED["telegram"]:
            return None
        return "telegram", username, f"https://t.me/{username}"

    @staticmethod
    def _valid_username(value: str, pattern: str) -> str | None:
        return value if value and re.fullmatch(pattern, value) else None

    @classmethod
    def _safe_image_url(cls, value: Any) -> str | None:
        if isinstance(value, dict):
            value = value.get("url") or value.get("source")
        if not isinstance(value, str):
            return None
        candidate = value.strip()
        if not candidate or len(candidate) > cls.MAX_URL_LENGTH:
            return None
        try:
            parsed = urlparse(candidate)
            port = parsed.port
        except ValueError:
            return None
        if (
            parsed.scheme.casefold() != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or (port is not None and port != 443)
            or not hostname_is_allowed(parsed.hostname.casefold())
        ):
            return None
        return candidate

    @staticmethod
    def _clean_text(value: Any, max_length: int) -> str | None:
        if not isinstance(value, (str, int, float)) or isinstance(value, bool):
            return None
        cleaned = "".join(
            " " if unicodedata.category(character).startswith("C") else character
            for character in str(value)
        )
        cleaned = " ".join(cleaned.split())[:max_length].strip()
        return cleaned or None

    @staticmethod
    def _comparison_text(value: str) -> str:
        return " ".join(value.casefold().split())

    @classmethod
    def _contains_exact_name(cls, value: str, full_name: str) -> bool:
        text = cls._comparison_text(value)
        name = cls._comparison_text(full_name)
        return bool(name and re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text))

    @staticmethod
    def _identity_key(
        platform: str, username: str, profile_url: str
    ) -> tuple[str, str]:
        if platform == "youtube" and "/channel/" in profile_url:
            return platform, f"channel:{username}"
        return platform, username.casefold()


__all__ = ["PersonSearchNormalizer"]
