"""Build bounded, exact-name queries for person-profile discovery."""

from __future__ import annotations

from collections.abc import Iterable
import unicodedata
from typing import Any


class PersonSearchQueryBuilder:
    """Create deterministic queries without generating username guesses."""

    MAX_QUERIES = 20
    MAX_NAME_LENGTH = 200
    MAX_CONTEXT_LENGTH = 200

    PLATFORM_ORDER = (
        "linkedin",
        "github",
        "twitter",
        "instagram",
        "facebook",
        "tiktok",
        "reddit",
        "youtube",
        "telegram",
    )
    PLATFORM_SITES: dict[str, tuple[str, ...]] = {
        "linkedin": ("linkedin.com/in",),
        "github": ("github.com",),
        "twitter": ("x.com", "twitter.com"),
        "instagram": ("instagram.com",),
        "facebook": ("facebook.com",),
        "tiktok": ("tiktok.com/@",),
        "reddit": ("reddit.com/user",),
        "youtube": ("youtube.com",),
        "telegram": ("t.me",),
    }
    PLATFORM_ALIASES = {"x": "twitter"}

    @classmethod
    def build(
        cls,
        full_name: str,
        platforms: Iterable[str] | str | None,
        location: str | None = None,
        organization: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Return an exact-name query followed by bounded grouped site queries.

        When a single query is allowed, the site-scoped query covers every
        requested platform. With two or more slots, the first query is a
        provider-neutral exact-name search and the remaining slots partition
        all requested platforms into deterministic groups.
        """

        name = cls._bounded_text(
            full_name,
            field_name="full_name",
            max_length=cls.MAX_NAME_LENGTH,
            required=True,
        )
        normalized_platforms = cls.normalize_platforms(platforms)
        effective_limit = cls._bounded_limit(limit)
        if effective_limit == 0:
            return []

        location_value = cls._bounded_text(
            location,
            field_name="location",
            max_length=cls.MAX_CONTEXT_LENGTH,
        )
        organization_value = cls._bounded_text(
            organization,
            field_name="organization",
            max_length=cls.MAX_CONTEXT_LENGTH,
        )
        anchors = [cls._quote(name)]
        if location_value:
            anchors.append(cls._quote(location_value))
        if organization_value:
            anchors.append(cls._quote(organization_value))
        anchor_query = " ".join(anchors)

        if not normalized_platforms:
            return [cls._query_record(anchor_query, name, [])]

        records: list[dict[str, Any]] = []
        if effective_limit > 1:
            records.append(cls._query_record(anchor_query, name, []))
            group_count = min(len(normalized_platforms), effective_limit - 1)
        else:
            group_count = 1

        for group in cls._balanced_groups(normalized_platforms, group_count):
            site_terms = [
                f"site:{site}"
                for platform in group
                for site in cls.PLATFORM_SITES[platform]
            ]
            site_filter = f"({' OR '.join(site_terms)})"
            records.append(
                cls._query_record(f"{anchor_query} {site_filter}", name, group)
            )
        return records[:effective_limit]

    @classmethod
    def normalize_platforms(
        cls,
        platforms: Iterable[str] | str | None,
    ) -> list[str]:
        """Validate, de-duplicate and canonically order platform names."""

        if platforms is None:
            return []
        values = [platforms] if isinstance(platforms, str) else list(platforms)
        selected: set[str] = set()
        unsupported: set[str] = set()
        for value in values:
            normalized = str(value or "").strip().casefold()
            normalized = cls.PLATFORM_ALIASES.get(normalized, normalized)
            if normalized in cls.PLATFORM_SITES:
                selected.add(normalized)
            elif normalized:
                unsupported.add(normalized)
        if unsupported:
            raise ValueError(
                "Unsupported person-search platform(s): "
                + ", ".join(sorted(unsupported))
            )
        return [platform for platform in cls.PLATFORM_ORDER if platform in selected]

    @classmethod
    def _query_record(
        cls,
        query: str,
        full_name: str,
        platforms: list[str],
    ) -> dict[str, Any]:
        return {
            "query": query,
            "platform": (
                "general"
                if not platforms
                else platforms[0]
                if len(platforms) == 1
                else "multiple"
            ),
            "platforms": list(platforms),
            "category": (
                "person_search_general"
                if not platforms
                else "person_search_profiles"
            ),
            "match_value": full_name,
            "phase": "person_search",
        }

    @staticmethod
    def _balanced_groups(values: list[str], group_count: int) -> list[list[str]]:
        if not values or group_count <= 0:
            return []
        group_count = min(group_count, len(values))
        base_size, larger_groups = divmod(len(values), group_count)
        groups: list[list[str]] = []
        offset = 0
        for index in range(group_count):
            size = base_size + (1 if index < larger_groups else 0)
            groups.append(values[offset : offset + size])
            offset += size
        return groups

    @classmethod
    def _bounded_text(
        cls,
        value: Any,
        *,
        field_name: str,
        max_length: int,
        required: bool = False,
    ) -> str | None:
        if value is None:
            if required:
                raise ValueError(f"{field_name} is required")
            return None
        cleaned = "".join(
            " " if unicodedata.category(character).startswith("C") else character
            for character in str(value)
        )
        cleaned = " ".join(cleaned.split())[:max_length].strip()
        if not cleaned:
            if required:
                raise ValueError(f"{field_name} cannot be blank")
            return None
        return cleaned

    @staticmethod
    def _quote(value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

    @classmethod
    def _bounded_limit(cls, value: Any) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            raise ValueError("limit must be an integer") from None
        return max(0, min(parsed, cls.MAX_QUERIES))
