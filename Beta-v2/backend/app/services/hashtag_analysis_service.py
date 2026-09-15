"""Deterministic cross-platform hashtag aggregation for public social content."""

from __future__ import annotations

from collections import Counter, defaultdict
import re
import unicodedata
from typing import Any, Iterable

from app.schemas.investigation import (
    HashtagAnalysis,
    HashtagMetric,
    PlatformHashtagSummary,
)


_PLATFORM_CONTENT_FIELDS: dict[str, tuple[str, ...]] = {
    "instagram": ("posts", "recent_posts"),
    "linkedin": ("posts", "recent_posts"),
    "tiktok": ("videos", "recent_posts"),
    "twitter": ("tweets", "recent_posts"),
    "facebook": ("posts", "recent_posts"),
    "youtube": ("videos", "recent_videos"),
    "github": ("recent_activity", "recent_posts", "repositories"),
}
_PLATFORM_AGGREGATE_FIELDS: dict[str, tuple[str, ...]] = {
    "instagram": ("post_hashtags", "hashtags", "all_hashtags", "all_hashtags_used"),
    "linkedin": ("all_hashtags", "hashtags", "all_hashtags_used"),
    "tiktok": ("hashtags", "all_hashtags", "all_hashtags_used"),
    "twitter": ("hashtags", "all_hashtags", "all_hashtags_used"),
    "facebook": ("all_hashtags", "hashtags", "all_hashtags_used"),
    "youtube": ("all_hashtags", "hashtags", "all_hashtags_used"),
    "github": ("all_hashtags", "hashtags"),
}
_PROFILE_TEXT_FIELDS = ("bio", "description")
_CONTENT_TEXT_FIELDS = ("caption", "text", "title", "description")
_CONTENT_TAG_FIELDS = ("hashtags", "tags")
_MAX_TAGS_PER_PLATFORM = 100
_MAX_TOP_TAGS = 50


def _normalize_tag(value: Any) -> str | None:
    """Normalize one explicit hashtag without accepting arbitrary markup."""

    if not isinstance(value, str):
        return None
    candidate = value.strip().lstrip("#").casefold()
    if not candidate or len(candidate) > 100:
        return None
    if not all(_is_tag_character(character) for character in candidate):
        return None
    return candidate


def _is_tag_character(value: str) -> bool:
    return (
        value.isalnum()
        or value in {"_", "-"}
        or unicodedata.category(value).startswith("M")
    )


def _tags_from_text(value: Any) -> set[str]:
    if not isinstance(value, str):
        return set()
    text = value[:10_000]
    tags: set[str] = set()
    cursor = 0
    while cursor < len(text):
        marker = text.find("#", cursor)
        if marker < 0:
            break
        end = marker + 1
        while end < len(text) and end - marker <= 100 and _is_tag_character(text[end]):
            end += 1
        normalized = _normalize_tag(text[marker + 1 : end])
        if normalized:
            tags.add(normalized)
        cursor = max(marker + 1, end)
    return tags


def _tags_from_explicit(value: Any) -> set[str]:
    if isinstance(value, dict):
        value = value.get("text") or value.get("tag") or value.get("name")
    if isinstance(value, str):
        # Some providers return a space-delimited string, while others return
        # one bare tag. Prefer explicit # tokens when they are present.
        extracted = _tags_from_text(value)
        if extracted:
            return extracted
        return {
            normalized
            for token in re.split(r"[\s,;|]+", value)
            if (normalized := _normalize_tag(token))
        }
    if not isinstance(value, list):
        return set()
    tags: set[str] = set()
    for item in value[:500]:
        tags.update(_tags_from_explicit(item))
    return tags


def extract_hashtags_from_text(value: Any) -> list[str]:
    """Return normalized hashtags parsed from one public text value."""

    return sorted(_tags_from_text(value))


def normalize_hashtag_values(value: Any) -> list[str]:
    """Return normalized hashtags from provider strings, lists, or dictionaries."""

    return sorted(_tags_from_explicit(value))


def _tags_from_record(record: dict[str, Any], *, profile: bool = False) -> set[str]:
    tags: set[str] = set()
    text_fields = _PROFILE_TEXT_FIELDS if profile else _CONTENT_TEXT_FIELDS
    for field in text_fields:
        tags.update(_tags_from_text(record.get(field)))
    if not profile:
        for field in _CONTENT_TAG_FIELDS:
            tags.update(_tags_from_explicit(record.get(field)))
    return tags


def _iter_content(profile: dict[str, Any], fields: Iterable[str]) -> Iterable[dict[str, Any]]:
    for field in fields:
        records = profile.get(field)
        if not isinstance(records, list):
            continue
        for record in records[:500]:
            if isinstance(record, dict):
                yield record
        # Remaining names are compatibility aliases for the same content.
        return


class HashtagAnalysisService:
    """Aggregate bounded public hashtag evidence without making network calls."""

    @staticmethod
    def analyze(profiles: dict[str, Any] | None) -> HashtagAnalysis:
        if not isinstance(profiles, dict):
            profiles = {}

        total_counts: Counter[str] = Counter()
        platforms_by_tag: defaultdict[str, set[str]] = defaultdict(set)
        platform_summaries: dict[str, PlatformHashtagSummary] = {}

        for platform, content_fields in _PLATFORM_CONTENT_FIELDS.items():
            profile = profiles.get(platform)
            if not isinstance(profile, dict):
                continue

            counts: Counter[str] = Counter()
            profile_tags = _tags_from_record(profile, profile=True)
            for tag in profile_tags:
                counts[tag] += 1

            source_items_with_hashtags = 1 if profile_tags else 0
            for record in _iter_content(profile, content_fields):
                record_tags = _tags_from_record(record)
                if record_tags:
                    source_items_with_hashtags += 1
                for tag in record_tags:
                    counts[tag] += 1

            # Aggregate fields can contain tags from provider rows omitted by a
            # bounded content response. Add only tags not already represented.
            aggregate_tags: set[str] = set()
            for field in _PLATFORM_AGGREGATE_FIELDS[platform]:
                aggregate_tags.update(_tags_from_explicit(profile.get(field)))
            for tag in aggregate_tags - set(counts):
                counts[tag] = 1

            if not counts:
                continue

            ranked_tags = sorted(counts, key=lambda tag: (-counts[tag], tag))[
                :_MAX_TAGS_PER_PLATFORM
            ]
            bounded_counts = Counter({tag: counts[tag] for tag in ranked_tags})
            for tag, mentions in bounded_counts.items():
                total_counts[tag] += mentions
                platforms_by_tag[tag].add(platform)

            platform_summaries[platform] = PlatformHashtagSummary(
                unique_hashtags=len(bounded_counts),
                total_mentions=sum(bounded_counts.values()),
                source_items_with_hashtags=source_items_with_hashtags,
                hashtags=ranked_tags,
            )

        ranked = sorted(
            total_counts,
            key=lambda tag: (
                -len(platforms_by_tag[tag]),
                -total_counts[tag],
                tag,
            ),
        )[:_MAX_TOP_TAGS]
        metrics = [
            HashtagMetric(
                tag=tag,
                mentions=total_counts[tag],
                platforms=sorted(platforms_by_tag[tag]),
                cross_platform=len(platforms_by_tag[tag]) > 1,
            )
            for tag in ranked
        ]

        return HashtagAnalysis(
            status="completed" if metrics else "no_data",
            total_unique_hashtags=len(total_counts),
            total_mentions=sum(total_counts.values()),
            platforms_with_hashtags=len(platform_summaries),
            top_hashtags=metrics,
            cross_platform_hashtags=[metric for metric in metrics if metric.cross_platform],
            platforms=platform_summaries,
        )
