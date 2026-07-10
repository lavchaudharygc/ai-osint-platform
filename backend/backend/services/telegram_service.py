"""Telegram public profile lookup service.

The service intentionally reads only metadata exposed by public t.me pages. It
does not use Telegram bots, MTProto, private groups, contacts, or sessions.
"""

from __future__ import annotations

from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse
import re

import httpx


class _TelegramPublicPageParser(HTMLParser):
    """Extract Telegram page metadata and visible public profile fields."""

    FIELD_CLASSES = {
        "tgme_page_title": "page_title",
        "tgme_page_extra": "page_extra",
        "tgme_page_description": "page_description",
    }
    VOID_TAGS = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.links: dict[str, str] = {}
        self._field_stack: list[str | None] = []
        self._field_text: dict[str, list[str]] = {}

    @property
    def fields(self) -> dict[str, str]:
        return {key: self._clean_text(" ".join(parts)) for key, parts in self._field_text.items()}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_name = tag.lower()
        attr_map = {key.lower(): value or "" for key, value in attrs}

        if tag_name == "meta":
            meta_key = attr_map.get("property") or attr_map.get("name")
            content = attr_map.get("content")
            if meta_key and content:
                self.meta[meta_key.lower()] = self._clean_text(content)
            return

        if tag_name == "link":
            rel_values = {value.lower() for value in attr_map.get("rel", "").split()}
            href = attr_map.get("href")
            if href:
                if "canonical" in rel_values:
                    self.links["canonical"] = href
                if "image_src" in rel_values:
                    self.links["image_src"] = href
            return

        if tag_name in self.VOID_TAGS:
            return

        field = self._field_from_classes(attr_map.get("class", ""))
        if field is None and self._field_stack:
            field = self._field_stack[-1]
        self._field_stack.append(field)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() not in self.VOID_TAGS and self._field_stack:
            self._field_stack.pop()

    def handle_data(self, data: str) -> None:
        if not self._field_stack:
            return
        field = self._field_stack[-1]
        if field and data.strip():
            self._field_text.setdefault(field, []).append(data)

    @classmethod
    def _field_from_classes(cls, classes: str) -> str | None:
        for class_name in classes.split():
            field = cls.FIELD_CLASSES.get(class_name)
            if field:
                return field
        return None

    @staticmethod
    def _clean_text(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()


class TelegramDataService:
    """Telegram user/channel lookup using public t.me metadata."""

    BASE_URL = "https://t.me"
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    )
    USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{5,32}$")

    async def get_profile(self, username: str) -> dict[str, Any]:
        normalized_username = self.normalize_username(username)
        scraped_at = datetime.now(UTC).isoformat()

        if not normalized_username:
            return self._base_response(
                username=str(username or "").strip(),
                scraped_at=scraped_at,
                success=False,
                exists=False,
                status="invalid_username",
                error=(
                    "Telegram usernames must be 5-32 characters and contain "
                    "letters, numbers, or underscores."
                ),
            )

        profile_url = f"{self.BASE_URL}/{normalized_username}"
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
                response = await client.get(profile_url, headers={"User-Agent": self.USER_AGENT})
        except httpx.TimeoutException:
            return self._base_response(
                username=normalized_username,
                profile_url=profile_url,
                scraped_at=scraped_at,
                success=False,
                exists=None,
                status="timeout",
                error="Timed out while fetching the public Telegram page.",
            )
        except httpx.HTTPError as exc:
            return self._base_response(
                username=normalized_username,
                profile_url=profile_url,
                scraped_at=scraped_at,
                success=False,
                exists=None,
                status="fetch_failed",
                error=str(exc),
            )

        if response.status_code in {404, 410}:
            return self._not_found_response(normalized_username, profile_url, scraped_at)
        if response.status_code == 429:
            return self._base_response(
                username=normalized_username,
                profile_url=profile_url,
                scraped_at=scraped_at,
                success=False,
                exists=None,
                status="rate_limited",
                error="Telegram returned HTTP 429 for the public page request.",
            )
        if response.status_code >= 400:
            return self._base_response(
                username=normalized_username,
                profile_url=profile_url,
                scraped_at=scraped_at,
                success=False,
                exists=None,
                status="http_error",
                http_status=response.status_code,
                error=f"Telegram returned HTTP {response.status_code}.",
            )

        return self._normalize_public_page(
            username=normalized_username,
            profile_url=profile_url,
            html=response.text,
            scraped_at=scraped_at,
            final_url=str(response.url),
            http_status=response.status_code,
        )

    @classmethod
    def normalize_username(cls, value: str) -> str | None:
        """Return a valid Telegram username from a handle or public URL."""
        raw_value = str(value or "").strip()
        if not raw_value:
            return None

        candidate = raw_value.lstrip("@")
        if "://" in candidate or candidate.lower().startswith(("t.me/", "telegram.me/")):
            parsed = urlparse(candidate if "://" in candidate else f"https://{candidate}")
            path_parts = [part for part in parsed.path.split("/") if part]
            if path_parts and path_parts[0].lower() == "s":
                path_parts = path_parts[1:]
            candidate = path_parts[0] if path_parts else ""

        candidate = candidate.split("?", 1)[0].split("#", 1)[0].strip().lstrip("@")
        if not cls.USERNAME_PATTERN.fullmatch(candidate):
            return None
        return candidate

    def _normalize_public_page(
        self,
        *,
        username: str,
        profile_url: str,
        html: str,
        scraped_at: str | None = None,
        final_url: str | None = None,
        http_status: int | None = None,
    ) -> dict[str, Any]:
        scraped_at = scraped_at or datetime.now(UTC).isoformat()
        if self._looks_not_found(html):
            return self._not_found_response(username, profile_url, scraped_at, http_status=http_status)

        parser = _TelegramPublicPageParser()
        parser.feed(html)
        fields = parser.fields
        meta = parser.meta

        full_name = self._public_text(fields.get("page_title")) or self._clean_og_title(meta.get("og:title"))
        page_extra = self._public_text(fields.get("page_extra"))
        raw_description = (
            self._public_text(fields.get("page_description"))
            or self._public_text(meta.get("og:description"))
            or self._public_text(meta.get("description"))
        )
        bio = None if self._is_telegram_boilerplate(raw_description, username) else raw_description
        profile_image = self._public_profile_image(
            self._public_url(meta.get("og:image"))
            or self._public_url(meta.get("twitter:image"))
            or self._public_url(parser.links.get("image_src"))
        )
        canonical_url = self._public_url(parser.links.get("canonical")) or profile_url

        if not self._has_public_profile_evidence(
            username=username,
            full_name=full_name,
            bio=bio,
            profile_image=profile_image,
            page_extra=page_extra,
            html=html,
        ):
            return self._not_found_response(username, profile_url, scraped_at, http_status=http_status)

        entity_type = self._infer_entity_type(page_extra, html)
        count_data = self._extract_count_data(page_extra)

        return {
            **self._base_response(
                username=username,
                profile_url=canonical_url,
                scraped_at=scraped_at,
                success=True,
                exists=True,
                status="found",
                http_status=http_status,
            ),
            "source": "t.me_public_page",
            "collection_method": "public_html_metadata",
            "entity_type": entity_type,
            "full_name": full_name,
            "display_name": full_name,
            "bio": bio,
            "description": bio,
            "profile_pic_url": profile_image,
            "profile_photo_url": profile_image,
            "page_extra": page_extra,
            "subscriber_count": count_data.get("subscriber_count"),
            "member_count": count_data.get("member_count"),
            "is_verified": self._is_verified(full_name, html),
            "final_url": final_url or canonical_url,
            "limitations": self._limitations(),
            "raw_data": {
                "meta": meta,
                "visible_fields": fields,
            },
        }

    def _not_found_response(
        self,
        username: str,
        profile_url: str,
        scraped_at: str,
        **extra: Any,
    ) -> dict[str, Any]:
        return self._base_response(
            username=username,
            profile_url=profile_url,
            scraped_at=scraped_at,
            success=False,
            exists=False,
            status="not_found_or_not_public",
            source="t.me_public_page",
            limitations=self._limitations(),
            **extra,
        )

    @staticmethod
    def _base_response(
        *,
        username: str,
        scraped_at: str,
        success: bool,
        exists: bool | None,
        status: str,
        profile_url: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        response: dict[str, Any] = {
            "success": success,
            "platform": "telegram",
            "username": username.lstrip("@"),
            "profile_url": profile_url or f"https://t.me/{username.lstrip('@')}",
            "exists": exists,
            "status": status,
            "scraped_at": scraped_at,
        }
        response.update({key: value for key, value in extra.items() if value is not None})
        return response

    @staticmethod
    def _public_text(value: str | None) -> str | None:
        if value is None:
            return None
        text = re.sub(r"\s+", " ", str(value)).strip()
        return text or None

    @staticmethod
    def _public_url(value: str | None) -> str | None:
        if not value:
            return None
        url = str(value).strip()
        return url if url.startswith(("http://", "https://")) else None

    @staticmethod
    def _public_profile_image(value: str | None) -> str | None:
        url = TelegramDataService._public_url(value)
        if not url:
            return None
        if url.rstrip("/").endswith("/img/t_logo_2x.png"):
            return None
        return url

    @staticmethod
    def _has_public_profile_evidence(
        *,
        username: str,
        full_name: str | None,
        bio: str | None,
        profile_image: str | None,
        page_extra: str | None,
        html: str,
    ) -> bool:
        """Require more than Telegram's generic HTTP-200 contact page."""
        if bio or profile_image or page_extra:
            return True
        if TelegramDataService._is_verified(full_name, html):
            return True
        if not full_name:
            return False

        normalized_title = full_name.strip().lstrip("@").casefold()
        normalized_username = username.strip().lstrip("@").casefold()
        if normalized_title == normalized_username:
            return False
        if normalized_title in {
            f"telegram: contact @{normalized_username}",
            f"telegram: view @{normalized_username}",
        }:
            return False
        return True

    @staticmethod
    def _clean_og_title(value: str | None) -> str | None:
        title = TelegramDataService._public_text(value)
        if not title:
            return None
        title = re.sub(r"^Telegram:\s*(?:Contact|View)\s+@", "", title, flags=re.IGNORECASE)
        return title.strip() or None

    @staticmethod
    def _looks_not_found(html: str) -> bool:
        lower_html = html.lower()
        not_found_markers = (
            "username not found",
            "user not found",
            "channel is inaccessible",
            "this channel is inaccessible",
            "invite link is invalid",
        )
        return any(marker in lower_html for marker in not_found_markers)

    @staticmethod
    def _is_telegram_boilerplate(description: str | None, username: str) -> bool:
        if not description:
            return False
        lower_description = description.lower()
        username_token = f"@{username.lower()}"
        boilerplate_markers = (
            "if you have telegram",
            "you can contact",
            "you can view and join",
            "right away",
        )
        has_boilerplate_shape = (
            "if you have telegram" in lower_description
            and "right away" in lower_description
            and ("you can contact" in lower_description or "you can view and join" in lower_description)
        )
        return has_boilerplate_shape or (
            username_token in lower_description
            and any(marker in lower_description for marker in boilerplate_markers)
        )

    @staticmethod
    def _infer_entity_type(page_extra: str | None, html: str) -> str:
        extra = (page_extra or "").lower()
        html_lower = html.lower()
        if "subscribers" in extra:
            return "channel"
        if "members" in extra:
            return "group"
        if "bot" in extra or ("tgme_page_context_link" in html_lower and "send message" in html_lower):
            return "bot_or_user"
        if "last seen" in extra or "online" in extra:
            return "user"
        return "profile_or_channel"

    @staticmethod
    def _extract_count_data(page_extra: str | None) -> dict[str, int | None]:
        if not page_extra:
            return {"subscriber_count": None, "member_count": None}
        lower_extra = page_extra.lower()
        count_match = re.search(r"([\d\s,.]+)\s+(subscribers?|members?)", lower_extra)
        if not count_match:
            return {"subscriber_count": None, "member_count": None}
        count = TelegramDataService._parse_human_count(count_match.group(1))
        if "subscriber" in count_match.group(2):
            return {"subscriber_count": count, "member_count": None}
        return {"subscriber_count": None, "member_count": count}

    @staticmethod
    def _parse_human_count(value: str) -> int | None:
        digits = re.sub(r"\D", "", value)
        return int(digits) if digits else None

    @staticmethod
    def _is_verified(full_name: str | None, html: str) -> bool:
        return bool(full_name and "\u2714" in full_name) or "verified-icon" in html.lower()

    @staticmethod
    def _limitations() -> list[str]:
        return [
            "Only public t.me profile/channel metadata was fetched.",
            "Private profiles, private groups, contacts, phone numbers, and message history are not accessed.",
            "Telegram may omit bio, photo, status, or counters depending on account privacy and page type.",
        ]
