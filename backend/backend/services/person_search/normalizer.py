"""Normalize public search results into unverified profile candidates."""

from __future__ import annotations

from collections.abc import Iterable
import re
import unicodedata
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from .query_builder import PersonSearchQueryBuilder


class PersonSearchNormalizer:
    """Strictly parse profile URLs without treating candidates as identities."""

    MAX_PROFILES = 100
    MAX_DISPLAY_NAME_LENGTH = 200
    MAX_BIO_LENGTH = 500
    MAX_SOURCE_LENGTH = 100
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

    _RESERVED: dict[str, frozenset[str]] = {
        "github": frozenset(
            {
                "about",
                "apps",
                "codespaces",
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
                "notifications",
                "organizations",
                "orgs",
                "pricing",
                "pulls",
                "search",
                "security",
                "settings",
                "site",
                "sponsors",
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
                "tos",
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
                "login",
                "marketplace",
                "pages",
                "people",
                "photo",
                "photos",
                "plugins",
                "privacy",
                "reel",
                "share",
                "story.php",
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
        results: Iterable[dict[str, Any]] | None,
        full_name: str,
        platforms: Iterable[str] | str | None,
        max_profiles: int,
    ) -> list[dict[str, Any]]:
        """Return bounded, deduplicated profile candidates in discovery order."""

        normalized_name = PersonSearchQueryBuilder._bounded_text(
            full_name,
            field_name="full_name",
            max_length=PersonSearchQueryBuilder.MAX_NAME_LENGTH,
            required=True,
        )
        assert normalized_name is not None
        requested = set(PersonSearchQueryBuilder.normalize_platforms(platforms))
        effective_limit = cls._bounded_profile_limit(max_profiles)
        if effective_limit == 0 or results is None:
            return []

        candidates_by_key: dict[tuple[str, str], dict[str, Any]] = {}
        ordered_keys: list[tuple[str, str]] = []
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
            platform, username, canonical_url = parsed
            if requested and platform not in requested:
                continue

            incoming = cls._candidate_from_result(
                raw_result,
                normalized_name,
                platform,
                username,
                canonical_url,
            )
            key = cls.profile_identity_key(platform, username, canonical_url)
            current = candidates_by_key.get(key)
            if current is None:
                candidates_by_key[key] = incoming
                ordered_keys.append(key)
            else:
                cls._merge_candidate(current, incoming)

        normalized: list[dict[str, Any]] = []
        for key in ordered_keys[:effective_limit]:
            candidate = candidates_by_key[key]
            candidate.pop("_display_quality", None)
            candidate["discovery_rank"] = len(normalized) + 1
            normalized.append(candidate)
        return normalized

    @classmethod
    def profile_identity_key(
        cls,
        platform: str,
        username: str,
        profile_url: str | None,
    ) -> tuple[str, str]:
        """Keep YouTube identifier namespaces and case-sensitive IDs distinct."""
        normalized_platform = str(platform or "").strip().casefold()
        clean_username = str(username or "").strip()
        if normalized_platform != "youtube":
            return normalized_platform, clean_username.casefold()

        try:
            parsed = urlparse(str(profile_url or ""))
            segments = [unquote(segment) for segment in parsed.path.split("/") if segment]
        except ValueError:
            segments = []
        if len(segments) == 1 and segments[0].startswith("@"):
            return "youtube", f"handle:{segments[0][1:].casefold()}"
        if len(segments) == 2:
            namespace = segments[0].casefold()
            value = segments[1].lstrip("@")
            if namespace == "channel":
                return "youtube", f"channel:{value}"
            if namespace in {"user", "c"}:
                return "youtube", f"{namespace}:{value.casefold()}"
        if re.fullmatch(r"UC[A-Za-z0-9_-]{22}", clean_username):
            return "youtube", f"channel:{clean_username}"
        return "youtube", f"handle:{clean_username.lstrip('@').casefold()}"

    @classmethod
    def _candidate_from_result(
        cls,
        result: dict[str, Any],
        full_name: str,
        platform: str,
        username: str,
        profile_url: str,
    ) -> dict[str, Any]:
        title = cls._clean_text(result.get("title"), cls.MAX_DISPLAY_NAME_LENGTH)
        explicit_name = cls._first_text(
            result,
            ("display_name", "full_name", "name"),
            cls.MAX_DISPLAY_NAME_LENGTH,
        )
        if explicit_name:
            display_name = explicit_name
            display_quality = 3
        elif title and cls._contains_exact_name(title, full_name):
            display_name = full_name
            display_quality = 2
        else:
            display_name = title
            display_quality = 1 if title else 0

        bio = cls._first_text(
            result,
            ("snippet", "description"),
            cls.MAX_BIO_LENGTH,
        )
        source = cls._clean_text(result.get("source"), cls.MAX_SOURCE_LENGTH)
        source = source or "search_result"
        discovery_query = cls._clean_text(result.get("query"), 2_000)
        match_basis = ["profile_url"]
        if explicit_name and cls._same_name(explicit_name, full_name):
            match_basis.append("exact_display_name")
        if title and cls._contains_exact_name(title, full_name):
            match_basis.append("exact_name_in_title")
        if bio and cls._contains_exact_name(bio, full_name):
            match_basis.append("exact_name_in_snippet")
        match_value = cls._clean_text(
            result.get("match_value"),
            PersonSearchQueryBuilder.MAX_NAME_LENGTH,
        )
        if match_value and cls._same_name(match_value, full_name):
            match_basis.append("exact_name_query")

        return {
            "platform": platform,
            "username": username,
            "profile_url": profile_url,
            "full_name": full_name
            if display_name and cls._contains_exact_name(display_name, full_name)
            else None,
            "display_name": display_name,
            "title": title,
            "bio": bio,
            "snippet": bio,
            "photo_url": cls._search_thumbnail(result),
            "source": source,
            "discovery_query": discovery_query,
            "identity_status": "unverified_candidate",
            "match_basis": match_basis,
            "discovery_rank": 0,
            "enrichment_status": "not_requested",
            "discovery": {
                "position": result.get("position")
                if isinstance(result.get("position"), int)
                else None,
                "query_category": cls._clean_text(
                    result.get("query_category"),
                    100,
                ),
                "search_thumbnail_unverified": bool(
                    cls._search_thumbnail(result)
                ),
            },
            "_display_quality": display_quality,
        }

    @classmethod
    def _merge_candidate(
        cls,
        current: dict[str, Any],
        incoming: dict[str, Any],
    ) -> None:
        current_quality = int(current.get("_display_quality") or 0)
        incoming_quality = int(incoming.get("_display_quality") or 0)
        current_name = str(current.get("display_name") or "")
        incoming_name = str(incoming.get("display_name") or "")
        if incoming_quality > current_quality or (
            incoming_quality == current_quality
            and len(incoming_name) > len(current_name)
        ):
            current["display_name"] = incoming.get("display_name")
            current["_display_quality"] = incoming_quality

        current_bio = str(current.get("bio") or "")
        incoming_bio = str(incoming.get("bio") or "")
        if len(incoming_bio) > len(current_bio):
            current["bio"] = incoming.get("bio")
        if not current.get("photo_url") and incoming.get("photo_url"):
            current["photo_url"] = incoming["photo_url"]
        if not current.get("full_name") and incoming.get("full_name"):
            current["full_name"] = incoming["full_name"]
        if not current.get("title") and incoming.get("title"):
            current["title"] = incoming["title"]
        if not current.get("snippet") and incoming.get("snippet"):
            current["snippet"] = incoming["snippet"]
        if not current.get("discovery_query") and incoming.get("discovery_query"):
            current["discovery_query"] = incoming["discovery_query"]
        if current.get("source") == "search_result" and incoming.get("source"):
            current["source"] = incoming["source"]

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
        if (
            "\\" in encoded_path
            or re.search(r"%2f|%5c", encoded_path, flags=re.IGNORECASE)
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
        cls,
        segments: list[str],
        _: str,
    ) -> tuple[str, str, str] | None:
        if len(segments) != 2 or segments[0].casefold() != "in":
            return None
        username = cls._valid_username(segments[1], r"[A-Za-z0-9_-]{1,100}")
        if not username:
            return None
        return "linkedin", username, f"https://www.linkedin.com/in/{username}/"

    @classmethod
    def _parse_github(
        cls,
        segments: list[str],
        _: str,
    ) -> tuple[str, str, str] | None:
        if len(segments) != 1:
            return None
        username = cls._valid_username(segments[0], r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?")
        if not username or username.casefold() in cls._RESERVED["github"]:
            return None
        return "github", username, f"https://github.com/{username}"

    @classmethod
    def _parse_twitter(
        cls,
        segments: list[str],
        _: str,
    ) -> tuple[str, str, str] | None:
        if len(segments) != 1:
            return None
        username = cls._valid_username(segments[0], r"[A-Za-z0-9_]{1,15}")
        if not username or username.casefold() in cls._RESERVED["twitter"]:
            return None
        return "twitter", username, f"https://x.com/{username}"

    @classmethod
    def _parse_instagram(
        cls,
        segments: list[str],
        _: str,
    ) -> tuple[str, str, str] | None:
        if len(segments) != 1:
            return None
        username = cls._valid_username(segments[0], r"[A-Za-z0-9._]{1,30}")
        if not username or username.casefold() in cls._RESERVED["instagram"]:
            return None
        return "instagram", username, f"https://www.instagram.com/{username}/"

    @classmethod
    def _parse_facebook(
        cls,
        segments: list[str],
        query: str,
    ) -> tuple[str, str, str] | None:
        if len(segments) != 1:
            return None
        first = segments[0]
        if first.casefold() == "profile.php":
            identifiers = parse_qs(query, keep_blank_values=False).get("id", [])
            if len(identifiers) != 1 or not re.fullmatch(r"[0-9]{3,30}", identifiers[0]):
                return None
            username = identifiers[0]
            return (
                "facebook",
                username,
                f"https://www.facebook.com/profile.php?id={username}",
            )
        username = cls._valid_username(first, r"[A-Za-z0-9.]{3,100}")
        if not username or username.casefold() in cls._RESERVED["facebook"]:
            return None
        return "facebook", username, f"https://www.facebook.com/{username}"

    @classmethod
    def _parse_tiktok(
        cls,
        segments: list[str],
        _: str,
    ) -> tuple[str, str, str] | None:
        if len(segments) != 1 or not segments[0].startswith("@"):
            return None
        username = cls._valid_username(segments[0][1:], r"[A-Za-z0-9._]{2,30}")
        if not username:
            return None
        return "tiktok", username, f"https://www.tiktok.com/@{username}"

    @classmethod
    def _parse_reddit(
        cls,
        segments: list[str],
        _: str,
    ) -> tuple[str, str, str] | None:
        if len(segments) != 2 or segments[0].casefold() not in {"user", "u"}:
            return None
        username = cls._valid_username(segments[1], r"[A-Za-z0-9_-]{3,20}")
        if not username:
            return None
        return "reddit", username, f"https://www.reddit.com/user/{username}"

    @classmethod
    def _parse_youtube(
        cls,
        segments: list[str],
        _: str,
    ) -> tuple[str, str, str] | None:
        if len(segments) == 1 and segments[0].startswith("@"):
            username = cls._valid_username(
                segments[0][1:],
                r"[A-Za-z0-9._-]{3,100}",
            )
            if username:
                return "youtube", username, f"https://www.youtube.com/@{username}"
            return None
        if len(segments) != 2 or segments[0].casefold() not in {"channel", "user", "c"}:
            return None
        path_type = segments[0].casefold()
        pattern = (
            r"UC[A-Za-z0-9_-]{22}"
            if path_type == "channel"
            else r"[A-Za-z0-9._-]{3,100}"
        )
        username = cls._valid_username(segments[1], pattern)
        if not username:
            return None
        return (
            "youtube",
            username,
            f"https://www.youtube.com/{path_type}/{username}",
        )

    @classmethod
    def _parse_telegram(
        cls,
        segments: list[str],
        _: str,
    ) -> tuple[str, str, str] | None:
        if len(segments) != 1 or segments[0].startswith("+"):
            return None
        username = cls._valid_username(segments[0], r"[A-Za-z][A-Za-z0-9_]{4,31}")
        if not username or username.casefold() in cls._RESERVED["telegram"]:
            return None
        return "telegram", username, f"https://t.me/{username}"

    @staticmethod
    def _valid_username(value: str, pattern: str) -> str | None:
        if not value or not re.fullmatch(pattern, value):
            return None
        return value

    @classmethod
    def _search_thumbnail(cls, result: dict[str, Any]) -> str | None:
        value = result.get("thumbnail")
        if isinstance(value, dict):
            value = value.get("url") or value.get("source")
        if not value:
            value = result.get("thumbnail_url")
        if not isinstance(value, str):
            return None
        candidate = value.strip()
        if not candidate or len(candidate) > cls.MAX_URL_LENGTH:
            return None
        try:
            parsed = urlparse(candidate)
        except ValueError:
            return None
        if (
            parsed.scheme.casefold() not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            return None
        return candidate

    @classmethod
    def _first_text(
        cls,
        value: dict[str, Any],
        keys: tuple[str, ...],
        max_length: int,
    ) -> str | None:
        for key in keys:
            normalized = cls._clean_text(value.get(key), max_length)
            if normalized:
                return normalized
        return None

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

    @classmethod
    def _same_name(cls, value: str, full_name: str) -> bool:
        return cls._comparison_text(value) == cls._comparison_text(full_name)

    @classmethod
    def _contains_exact_name(cls, value: str, full_name: str) -> bool:
        text = cls._comparison_text(value)
        name = cls._comparison_text(full_name)
        if not name:
            return False
        return re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text) is not None

    @staticmethod
    def _comparison_text(value: str) -> str:
        return " ".join(str(value).casefold().split())

    @classmethod
    def _bounded_profile_limit(cls, value: Any) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            raise ValueError("max_profiles must be an integer") from None
        return max(0, min(parsed, cls.MAX_PROFILES))
