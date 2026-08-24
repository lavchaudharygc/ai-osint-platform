"""Build bounded, deterministic exact-name profile search queries."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


class PersonSearchQueryBuilder:
    """Create exact-name queries without generating usernames or aliases."""

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

    @classmethod
    def build(
        cls,
        *,
        full_name: str,
        platforms: Iterable[str],
        location: str | None,
        state: str | None,
        organization: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Return a general exact-name query plus balanced site groups."""

        normalized_platforms = cls.normalize_platforms(platforms)
        effective_limit = max(1, min(int(limit), 8))
        anchors = [cls._quote(full_name)]
        for value in (location, state, organization):
            if value and value.casefold() not in {
                anchor.strip('"').casefold() for anchor in anchors
            }:
                anchors.append(cls._quote(value))
        anchor_query = " ".join(anchors)

        if not normalized_platforms:
            return []
        if effective_limit == 1:
            groups = [normalized_platforms]
            include_general = False
        else:
            groups = cls._balanced_groups(
                normalized_platforms,
                min(len(normalized_platforms), effective_limit - 1),
            )
            include_general = True

        records: list[dict[str, Any]] = []
        if include_general:
            records.append(
                {
                    "query": anchor_query,
                    "platforms": [],
                    "category": "person_search_general",
                    "match_value": full_name,
                }
            )
        for group in groups:
            site_terms = [
                f"site:{site}"
                for platform in group
                for site in cls.PLATFORM_SITES[platform]
            ]
            records.append(
                {
                    "query": f"{anchor_query} ({' OR '.join(site_terms)})",
                    "platforms": list(group),
                    "category": "person_search_profiles",
                    "match_value": full_name,
                }
            )
        return records[:effective_limit]

    @classmethod
    def normalize_platforms(cls, platforms: Iterable[str]) -> list[str]:
        """De-duplicate and preserve the stable server platform order."""

        requested = {str(platform).strip().casefold() for platform in platforms}
        return [platform for platform in cls.PLATFORM_ORDER if platform in requested]

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

    @staticmethod
    def _quote(value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'


__all__ = ["PersonSearchQueryBuilder"]
