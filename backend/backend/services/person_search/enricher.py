"""Bounded, profile-only enrichment for person-search discovery candidates.

The person-search discovery layer returns public profile URL candidates.  This
module enriches a small, explicitly budgeted subset without coupling the new
feature to the existing username-investigation fanout or its content collectors.
Collector success confirms only that an account was collected; it never changes
the candidate's identity status from ``unverified_candidate``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from math import isfinite
import re
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse

from backend.core.config import settings
from backend.services.facebook_apify_service import FacebookApifyService
from backend.services.github_service import GitHubService
from backend.services.instagram_profile_service import InstagramProfileService
from backend.services.investigation_policy import ProviderCallBudget
from backend.services.linkedin_apify_service import LinkedInApifyService
from backend.services.reddit_service import RedditService
from backend.services.telegram_service import TelegramDataService
from backend.services.tiktok_apify_service import TikTokApifyService
from backend.services.twitter_apify_service import TwitterApifyService
from backend.services.youtube_service import YouTubeService


Candidate = dict[str, Any]
Collector = Callable[[Candidate], Awaitable[dict[str, Any]]]


@dataclass(frozen=True, slots=True)
class EnrichmentSpec:
    """One injectable collector plus its worst-case provider-call cost."""

    collector: Collector
    call_units: int = 1
    configured: bool | Callable[[], bool] = True

    def __post_init__(self) -> None:
        if not callable(self.collector):
            raise TypeError("collector must be callable")
        if (
            isinstance(self.call_units, bool)
            or not isinstance(self.call_units, int)
            or self.call_units < 0
        ):
            raise ValueError("call_units must be a non-negative integer")
        if not isinstance(self.configured, bool) and not callable(self.configured):
            raise TypeError("configured must be a boolean or callable")

    def is_configured(self) -> bool:
        try:
            value = self.configured() if callable(self.configured) else self.configured
        except Exception:
            return False
        return bool(value)


@dataclass(frozen=True, slots=True)
class _Outcome:
    index: int
    candidate: Candidate
    category: str
    error: dict[str, Any] | None = None
    warning: str | None = None


class PersonSearchEnricher:
    """Enrich normalized person-search candidates with lightweight collectors."""

    _NOT_CONFIGURED_STATUSES = {"disabled", "not_configured"}
    _NOT_FOUND_STATUSES = {"empty_dataset", "not_found"}
    _FAILURE_STATUSES = {
        "error",
        "failed",
        "fetch_failed",
        "invalid_response",
        "provider_error",
        "quota_exhausted",
        "rate_limited",
        "timeout",
        "unauthorized",
    }
    _COMPLETED_WITH_WARNING_STATUSES = {
        "completed_with_errors",
        "completed_with_warnings",
        "partial",
    }
    _HOSTS: dict[str, tuple[str, ...]] = {
        "instagram": ("instagram.com",),
        "twitter": ("x.com", "twitter.com"),
        "telegram": ("t.me", "telegram.me"),
        "linkedin": ("linkedin.com",),
        "reddit": ("reddit.com",),
        "facebook": ("facebook.com", "fb.com"),
        "tiktok": ("tiktok.com",),
        "github": ("github.com",),
        "youtube": ("youtube.com",),
    }
    _RESERVED_ROOT_PATHS: dict[str, set[str]] = {
        "instagram": {
            "about",
            "accounts",
            "developer",
            "direct",
            "explore",
            "legal",
            "p",
            "privacy",
            "reel",
            "reels",
            "stories",
        },
        "twitter": {
            "compose",
            "explore",
            "hashtag",
            "home",
            "i",
            "intent",
            "messages",
            "search",
            "settings",
        },
        "telegram": {"addstickers", "iv", "joinchat", "s", "share"},
        "github": {
            "about",
            "apps",
            "collections",
            "contact",
            "customer-stories",
            "enterprise",
            "events",
            "explore",
            "features",
            "issues",
            "login",
            "marketplace",
            "new",
            "notifications",
            "orgs",
            "organizations",
            "pricing",
            "pulls",
            "search",
            "security",
            "settings",
            "site",
            "sponsors",
            "topics",
            "trending",
        },
    }
    _USERNAME_PATTERNS: dict[str, re.Pattern[str]] = {
        "instagram": re.compile(r"^[A-Za-z0-9._]{1,30}$"),
        "twitter": re.compile(r"^[A-Za-z0-9_]{1,15}$"),
        "telegram": re.compile(r"^[A-Za-z0-9_]{5,32}$"),
        "reddit": re.compile(r"^[A-Za-z0-9_-]{3,20}$"),
        "tiktok": re.compile(r"^[A-Za-z0-9._]{1,30}$"),
        "github": re.compile(
            r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$"
        ),
    }

    def __init__(
        self,
        *,
        specs: Mapping[str, EnrichmentSpec | Collector] | None = None,
    ) -> None:
        supplied = self._production_specs() if specs is None else specs
        normalized: dict[str, EnrichmentSpec] = {}
        for raw_platform, raw_spec in supplied.items():
            platform = str(raw_platform).strip().casefold()
            if not platform:
                raise ValueError("enrichment spec platform cannot be empty")
            spec = (
                raw_spec
                if isinstance(raw_spec, EnrichmentSpec)
                else EnrichmentSpec(collector=raw_spec)
            )
            normalized[platform] = spec
        self.specs = normalized

    async def enrich(
        self,
        candidates: list[Candidate],
        *,
        budget: ProviderCallBudget,
        max_enrichments: int,
        concurrency: int,
        timeout_seconds: float,
    ) -> tuple[list[Candidate], dict[str, Any]]:
        """Return all candidates, enriching only a bounded and reserved subset."""
        self._validate_limits(
            max_enrichments=max_enrichments,
            concurrency=concurrency,
            timeout_seconds=timeout_seconds,
        )
        if not isinstance(budget, ProviderCallBudget):
            raise TypeError("budget must be a ProviderCallBudget")
        if not isinstance(candidates, list) or any(
            not isinstance(candidate, dict) for candidate in candidates
        ):
            raise TypeError("candidates must be a list of dictionaries")

        enriched = [deepcopy(candidate) for candidate in candidates]
        summary: dict[str, Any] = {
            "attempted": 0,
            "completed": 0,
            "failed": 0,
            "not_configured": 0,
            "skipped": 0,
            "not_found": 0,
            "not_requested": 0,
            "errors": [],
            "warnings": [],
            "max_enrichments": max_enrichments,
            "concurrency": concurrency,
            "timeout_seconds": float(timeout_seconds),
        }

        planned: list[tuple[int, Candidate, EnrichmentSpec]] = []
        for index, candidate in enumerate(enriched):
            candidate["identity_status"] = "unverified_candidate"
            platform = str(candidate.get("platform") or "").strip().casefold()
            candidate["platform"] = platform or candidate.get("platform")
            spec = self.specs.get(platform)
            if spec is None:
                self._mark_skipped(
                    candidate,
                    summary,
                    code="unsupported_platform",
                    message=f"No person-search enricher is configured for {platform or 'this candidate'}.",
                )
                continue

            target_problem = self._target_problem(candidate, platform)
            if target_problem:
                self._mark_skipped(
                    candidate,
                    summary,
                    code="invalid_candidate_target",
                    message=target_problem,
                    call_units=spec.call_units,
                )
                continue

            if len(planned) >= max_enrichments:
                self._mark_not_requested(
                    candidate,
                    summary,
                    message="The request enrichment limit was reached.",
                    call_units=spec.call_units,
                )
                continue

            if not spec.is_configured():
                self._mark_not_configured(
                    candidate,
                    summary,
                    message=f"{platform} profile enrichment is not configured.",
                    call_units=spec.call_units,
                )
                continue

            capability = f"person_search.enrich.{platform}"
            if not budget.try_reserve(capability, spec.call_units):
                self._mark_skipped(
                    candidate,
                    summary,
                    code="provider_call_limit_exceeded",
                    message=(
                        f"{platform} enrichment requires {spec.call_units} provider call "
                        f"unit(s), but only {budget.remaining} remain."
                    ),
                    call_units=spec.call_units,
                )
                continue

            planned.append((index, candidate, spec))

        semaphore = asyncio.Semaphore(concurrency)
        tasks: dict[
            asyncio.Task[_Outcome],
            tuple[int, Candidate, EnrichmentSpec],
        ] = {
            asyncio.create_task(
                self._run_one(
                    index,
                    candidate,
                    spec,
                    semaphore=semaphore,
                )
            ): (index, candidate, spec)
            for index, candidate, spec in planned
        }
        outcomes: list[_Outcome] = []
        if tasks:
            try:
                done, pending = await asyncio.wait(
                    tasks,
                    timeout=float(timeout_seconds),
                )
            except BaseException:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                raise

            for task in done:
                index, candidate, spec = tasks[task]
                if task.cancelled():
                    outcomes.append(
                        self._failed_outcome(
                            index,
                            candidate,
                            code="collector_cancelled",
                            message=(
                                f"{candidate.get('platform') or 'profile'} enrichment "
                                "was cancelled by its collector."
                            ),
                            call_units=spec.call_units,
                        )
                    )
                else:
                    outcomes.append(task.result())

            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            for task in pending:
                index, candidate, spec = tasks[task]
                outcomes.append(
                    self._failed_outcome(
                        index,
                        candidate,
                        code="timeout",
                        message=(
                            f"{candidate.get('platform') or 'profile'} enrichment "
                            "did not finish before the overall enrichment deadline."
                        ),
                        call_units=spec.call_units,
                    )
                )

        outcomes.sort(key=lambda outcome: outcome.index)
        summary["attempted"] = len(planned)
        for outcome in outcomes:
            enriched[outcome.index] = outcome.candidate
            if outcome.category == "completed":
                summary["completed"] += 1
            elif outcome.category == "not_configured":
                summary["not_configured"] += 1
            elif outcome.category == "not_found":
                summary["not_found"] += 1
            else:
                summary["failed"] += 1
            if outcome.error:
                summary["errors"].append(outcome.error)
            if outcome.warning:
                summary["warnings"].append(outcome.warning)

        summary["budget"] = budget.snapshot()
        return enriched, summary

    async def _run_one(
        self,
        index: int,
        candidate: Candidate,
        spec: EnrichmentSpec,
        *,
        semaphore: asyncio.Semaphore,
    ) -> _Outcome:
        platform = str(candidate.get("platform") or "unknown")
        async with semaphore:
            try:
                result = await spec.collector(deepcopy(candidate))
            except Exception as exc:
                return self._failed_outcome(
                    index,
                    candidate,
                    code="collector_exception",
                    message=str(exc)[:300] or exc.__class__.__name__,
                    call_units=spec.call_units,
                    error_type=exc.__class__.__name__,
                )

        if not isinstance(result, dict):
            return self._failed_outcome(
                index,
                candidate,
                code="invalid_response",
                message=f"{platform} collector returned a non-object response.",
                call_units=spec.call_units,
            )

        status = str(result.get("status") or "").strip().casefold()
        reason = self._result_message(result)
        not_configured = (
            result.get("configured") is False
            or status in self._NOT_CONFIGURED_STATUSES
            or self._looks_not_configured(reason)
        )
        if not_configured:
            updated = self._apply_enrichment(
                candidate,
                result,
                enrichment_status="not_configured",
                call_units=spec.call_units,
            )
            warning = self._warning_text(
                candidate,
                message=reason or f"{platform} profile enrichment is not configured.",
            )
            return _Outcome(index, updated, "not_configured", warning=warning)

        if status in self._NOT_FOUND_STATUSES or result.get("exists") is False:
            updated = self._apply_enrichment(
                candidate,
                result,
                enrichment_status="not_found",
                call_units=spec.call_units,
            )
            warning = self._warning_text(
                candidate,
                message=reason or f"{platform} did not return a public profile record.",
            )
            return _Outcome(index, updated, "not_found", warning=warning)

        explicit_success = result.get("success")
        if status in self._FAILURE_STATUSES or explicit_success is False:
            failure_code = (
                status if status in self._FAILURE_STATUSES else "collection_failed"
            )
            return self._failed_outcome(
                index,
                candidate,
                code=failure_code,
                message=reason
                or f"{platform} collector reported an unsuccessful response.",
                call_units=spec.call_units,
                result=result,
            )

        view = self._profile_view(result)
        collected = self._has_profile_record(view)
        succeeded = bool(explicit_success is True and collected) or (
            status in {"completed", *self._COMPLETED_WITH_WARNING_STATUSES}
            and collected
        )
        if succeeded:
            target_problem = self._collector_target_problem(candidate, result)
            if target_problem:
                return self._failed_outcome(
                    index,
                    candidate,
                    code="collector_target_mismatch",
                    message=target_problem,
                    call_units=spec.call_units,
                )
            with_warning = status in self._COMPLETED_WITH_WARNING_STATUSES
            updated = self._apply_enrichment(
                candidate,
                result,
                enrichment_status=(
                    "completed_with_warnings" if with_warning else "completed"
                ),
                call_units=spec.call_units,
            )
            warning = None
            if with_warning:
                warning = self._warning_text(
                    candidate,
                    message=reason or f"{platform} profile enrichment was only partially complete.",
                )
            return _Outcome(index, updated, "completed", warning=warning)

        return self._failed_outcome(
            index,
            candidate,
            code="collection_failed",
            message=reason or f"{platform} collector did not return a usable profile record.",
            call_units=spec.call_units,
            result=result,
        )

    def _failed_outcome(
        self,
        index: int,
        candidate: Candidate,
        *,
        code: str,
        message: str,
        call_units: int,
        error_type: str | None = None,
        result: dict[str, Any] | None = None,
    ) -> _Outcome:
        updated = self._apply_enrichment(
            candidate,
            result or {},
            enrichment_status=code,
            call_units=call_units,
        )
        error = self._issue(candidate, code=code, message=message)
        if error_type:
            error["error_type"] = error_type
        return _Outcome(index, updated, "failed", error=error)

    def _apply_enrichment(
        self,
        candidate: Candidate,
        result: dict[str, Any],
        *,
        enrichment_status: str,
        call_units: int,
    ) -> Candidate:
        updated = deepcopy(candidate)
        view = self._profile_view(result)
        requested_username = self._clean_string(candidate.get("username"))
        requested_profile_url = self._clean_string(candidate.get("profile_url"))
        collector_confirmed = enrichment_status in {
            "completed",
            "completed_with_warnings",
        }
        resolved_username = (
            self._resolved_username(str(candidate.get("platform") or ""), view)
            if collector_confirmed
            else None
        )
        display_name = self._first_string(
            view,
            "full_name",
            "display_name",
            "name",
            "channel_name",
            "title",
            maximum=200,
        )
        bio = self._first_string(
            view,
            "bio",
            "description",
            "biography",
            "public_description",
            "headline",
            maximum=5_000,
        )
        photo_url = self._first_public_url(
            view,
            "profile_pic_hd",
            "profile_pic_url",
            "avatar_url",
            "icon_url",
            "profile_image_url",
            "profilePictureUrl",
        )
        location = self._first_string(
            view,
            "location",
            "location_name",
            maximum=200,
        )
        organization = self._first_string(
            view,
            "organization",
            "current_company",
            "company",
            "workplace",
            maximum=200,
        )
        verified = self._first_boolean(view, "is_verified", "verified")
        collector_source = self._clean_string(
            result.get("source") or result.get("provider")
        )
        if collector_source:
            collector_source = collector_source[:100]

        # Only a target-matched successful collector may contribute identity or
        # photo fields. Failed/not-found responses remain discovery-only.
        collected_fields = (
            ("full_name", display_name),
            ("display_name", display_name),
            ("bio", bio),
            ("photo_url", photo_url),
            ("location", location),
            ("organization", organization),
            ("verified", verified),
            ("collector_source", collector_source),
        )
        for key, value in collected_fields:
            if collector_confirmed and value is not None:
                updated[key] = value
            else:
                updated.setdefault(key, None)

        if resolved_username:
            updated["username"] = resolved_username

        updated["identity_status"] = "unverified_candidate"
        updated["collector_confirmed"] = collector_confirmed
        updated["enriched"] = collector_confirmed
        updated["enrichment_status"] = enrichment_status
        updated["enrichment"] = {
            "status": enrichment_status,
            "provider_status": self._clean_string(result.get("status")),
            "configured": (
                result.get("configured")
                if isinstance(result.get("configured"), bool)
                else None
            ),
            "exists": (
                result.get("exists")
                if isinstance(result.get("exists"), bool)
                else None
            ),
            "collector_source": collector_source,
            "call_units": call_units,
            "requested_username": requested_username,
            "requested_profile_url": requested_profile_url,
            "resolved_username": resolved_username,
        }
        return updated

    @staticmethod
    def _profile_view(result: dict[str, Any]) -> dict[str, Any]:
        view: dict[str, Any] = {}
        for key in ("profile", "channel", "page", "public_evidence"):
            nested = result.get(key)
            if isinstance(nested, dict):
                view.update(
                    {nested_key: value for nested_key, value in nested.items() if value is not None}
                )
        view.update({key: value for key, value in result.items() if value is not None})
        return view

    @classmethod
    def _has_profile_record(cls, view: dict[str, Any]) -> bool:
        return any(
            view.get(key)
            for key in (
                "username",
                "handle",
                "channel_id",
                "full_name",
                "display_name",
                "name",
                "bio",
                "description",
                "profile_url",
                "profile_pic_url",
                "avatar_url",
            )
        )

    @staticmethod
    def _validate_limits(
        *,
        max_enrichments: int,
        concurrency: int,
        timeout_seconds: float,
    ) -> None:
        if (
            isinstance(max_enrichments, bool)
            or not isinstance(max_enrichments, int)
            or max_enrichments < 0
        ):
            raise ValueError("max_enrichments must be a non-negative integer")
        if isinstance(concurrency, bool) or not isinstance(concurrency, int) or concurrency < 1:
            raise ValueError("concurrency must be a positive integer")
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)):
            raise ValueError("timeout_seconds must be a positive number")
        if not isfinite(float(timeout_seconds)) or float(timeout_seconds) <= 0:
            raise ValueError("timeout_seconds must be a positive finite number")

    def _target_problem(self, candidate: Candidate, platform: str) -> str | None:
        username = self._clean_string(candidate.get("username"))
        if not username:
            return "A canonical candidate username is required for enrichment."
        if len(username) > 200 or "://" in username or any(
            character.isspace() or ord(character) < 32 for character in username
        ):
            return "The candidate username is not a canonical platform identifier."
        pattern = self._USERNAME_PATTERNS.get(platform)
        if pattern and pattern.fullmatch(username.lstrip("@")) is None:
            return f"The candidate username is invalid for {platform}."

        profile_url = self._clean_string(candidate.get("profile_url"))
        if profile_url and platform in self._HOSTS:
            return self._profile_url_problem(platform, username, profile_url)
        return None

    def _collector_target_problem(
        self,
        candidate: Candidate,
        result: dict[str, Any],
    ) -> str | None:
        """Require a collector response to identify the requested public account."""
        platform = str(candidate.get("platform") or "").strip().casefold()
        requested = self._clean_string(candidate.get("username"))
        if not requested:
            return "The discovery candidate has no username to confirm."
        expected = requested.lstrip("@").casefold()
        views = self._identity_views(result)

        handle_values: set[str] = set()
        channel_ids: set[str] = set()
        page_ids: set[str] = set()
        profile_urls: list[str] = []
        for view in views:
            for key in ("username", "handle", "login", "screen_name", "userName"):
                value = self._clean_string(view.get(key))
                if value:
                    handle_values.add(value.lstrip("@").casefold())
            channel_id = self._clean_string(view.get("channel_id"))
            if channel_id:
                channel_ids.add(channel_id)
            page_id = self._clean_string(view.get("page_id"))
            if page_id:
                page_ids.add(page_id.casefold())
            for key in (
                "profile_url",
                "profileUrl",
                "linkedinUrl",
                "facebookUrl",
            ):
                value = self._clean_string(view.get(key))
                if value and value not in profile_urls:
                    profile_urls.append(value)

        url_matches = [
            self._profile_url_problem(platform, requested, value) is None
            for value in profile_urls
            if platform in self._HOSTS
        ]
        matching_url = any(url_matches)
        mismatching_url = any(not matched for matched in url_matches)

        if platform == "youtube":
            channel_target = re.fullmatch(r"UC[A-Za-z0-9_-]{22}", requested)
            matched = (
                requested in channel_ids or matching_url
                if channel_target
                else (
                    expected in handle_values
                    or matching_url
                    or self._youtube_legacy_lookup_matches(candidate, result)
                )
            )
            if matched:
                return None
        else:
            comparable = set(handle_values)
            if platform == "facebook" and expected.isdigit():
                comparable.update(page_ids)
            if expected in comparable or matching_url:
                if comparable and any(value != expected for value in comparable):
                    return (
                        f"{platform} collector returned identifiers for a different "
                        "account than the discovery candidate."
                    )
                if mismatching_url:
                    return (
                        f"{platform} collector returned a profile URL for a different "
                        "account than the discovery candidate."
                    )
                return None

        if handle_values or channel_ids or page_ids or profile_urls:
            return (
                f"{platform} collector returned a different account than the "
                "discovery candidate."
            )
        return f"{platform} collector response did not identify the requested account."

    def _youtube_legacy_lookup_matches(
        self,
        candidate: Candidate,
        result: dict[str, Any],
    ) -> bool:
        """Bind an official legacy URL lookup to its resolved modern channel."""
        profile_url = self._clean_string(candidate.get("profile_url"))
        requested = self._clean_string(candidate.get("username"))
        lookup = result.get("lookup")
        target = self._clean_string(result.get("target"))
        channel_id = self._clean_string(result.get("channel_id"))
        if not (
            profile_url
            and requested
            and isinstance(lookup, dict)
            and target
            and channel_id
            and re.fullmatch(r"UC[A-Za-z0-9_-]{22}", channel_id)
        ):
            return False
        try:
            parsed = urlparse(profile_url)
            target_parsed = urlparse(target)
        except ValueError:
            return False
        if (
            parsed.scheme not in {"http", "https"}
            or target_parsed.scheme not in {"http", "https"}
            or (parsed.hostname or "").casefold()
            != (target_parsed.hostname or "").casefold()
            or parsed.path.rstrip("/").casefold()
            != target_parsed.path.rstrip("/").casefold()
        ):
            return False
        segments = [unquote(segment) for segment in parsed.path.split("/") if segment]
        if len(segments) != 2:
            return False
        prefix = segments[0].casefold()
        expected_kind = "username" if prefix == "user" else "handle" if prefix == "c" else None
        return bool(
            expected_kind
            and str(lookup.get("kind") or "").casefold() == expected_kind
            and str(lookup.get("value") or "").lstrip("@").casefold()
            == requested.lstrip("@").casefold()
        )

    @staticmethod
    def _identity_views(result: dict[str, Any]) -> list[dict[str, Any]]:
        views = [result]
        for key in ("profile", "channel", "page", "public_evidence"):
            value = result.get(key)
            if isinstance(value, dict):
                views.append(value)
        for key in ("profiles", "pages", "items"):
            values = result.get(key)
            if isinstance(values, list):
                views.extend(value for value in values if isinstance(value, dict))
        return views

    @classmethod
    def _resolved_username(cls, platform: str, view: dict[str, Any]) -> str | None:
        keys = (
            ("handle", "username", "login", "screen_name", "channel_id")
            if platform.casefold() == "youtube"
            else ("username", "login", "handle", "screen_name", "page_id")
        )
        value = cls._first_string(view, *keys, maximum=200)
        if value:
            return value.lstrip("@")
        return None

    def _profile_url_problem(
        self,
        platform: str,
        username: str,
        profile_url: str,
    ) -> str | None:
        if len(profile_url) > 2_048:
            return "The candidate profile URL is too long."
        try:
            parsed = urlparse(profile_url)
            port = parsed.port
        except ValueError:
            return "The candidate profile URL is invalid."
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return "The candidate profile URL must use public HTTP(S)."
        if parsed.username or parsed.password or port not in {None, 80, 443}:
            return "The candidate profile URL contains unsupported authority data."
        hostname = parsed.hostname.casefold()
        if not any(
            hostname == allowed or hostname.endswith(f".{allowed}")
            for allowed in self._HOSTS[platform]
        ):
            return f"The candidate profile URL is not hosted by {platform}."

        segments = [unquote(segment) for segment in parsed.path.split("/") if segment]
        expected = username.lstrip("@").casefold()
        valid = False
        if platform in {"instagram", "twitter", "telegram", "github"}:
            valid = (
                len(segments) == 1
                and segments[0].lstrip("@").casefold() == expected
                and segments[0].casefold()
                not in self._RESERVED_ROOT_PATHS.get(platform, set())
                and not segments[0].startswith("+")
            )
        elif platform == "linkedin":
            valid = (
                len(segments) == 2
                and segments[0].casefold() == "in"
                and segments[1].casefold() == expected
            )
        elif platform == "reddit":
            valid = (
                len(segments) == 2
                and segments[0].casefold() in {"u", "user"}
                and segments[1].casefold() == expected
            )
        elif platform == "tiktok":
            valid = (
                len(segments) == 1
                and segments[0].startswith("@")
                and segments[0][1:].casefold() == expected
            )
        elif platform == "facebook":
            query_id = (parse_qs(parsed.query).get("id") or [None])[0]
            valid = (
                (len(segments) == 1 and segments[0].casefold() == expected)
                or (
                    len(segments) == 1
                    and segments[0].casefold() == "profile.php"
                    and str(query_id or "").casefold() == expected
                )
                or (
                    len(segments) == 3
                    and segments[0].casefold() == "people"
                    and segments[2].casefold() == expected
                )
            )
        elif platform == "youtube":
            valid = (
                len(segments) == 1
                and segments[0].startswith("@")
                and segments[0][1:].casefold() == expected
            ) or (
                len(segments) == 2
                and segments[0].casefold() in {"c", "user"}
                and segments[1].lstrip("@").casefold() == expected
            ) or (
                len(segments) == 2
                and segments[0].casefold() == "channel"
                and re.fullmatch(r"UC[A-Za-z0-9_-]{22}", username) is not None
                and segments[1] == username
            )
        if not valid:
            return f"The candidate URL is not a canonical {platform} profile URL."
        return None

    @staticmethod
    def _mark_skipped(
        candidate: Candidate,
        summary: dict[str, Any],
        *,
        code: str,
        message: str,
        call_units: int = 0,
    ) -> None:
        candidate["identity_status"] = "unverified_candidate"
        candidate["collector_confirmed"] = False
        candidate["enriched"] = False
        candidate["enrichment_status"] = code
        candidate["enrichment"] = {
            "status": code,
            "reason": message,
            "call_units": call_units,
        }
        summary["skipped"] += 1
        summary["warnings"].append(
            PersonSearchEnricher._warning_text(candidate, message=message)
        )

    @staticmethod
    def _mark_not_requested(
        candidate: Candidate,
        summary: dict[str, Any],
        *,
        message: str,
        call_units: int,
    ) -> None:
        candidate["identity_status"] = "unverified_candidate"
        candidate["collector_confirmed"] = False
        candidate["enriched"] = False
        candidate["enrichment_status"] = "not_requested_due_limit"
        candidate["enrichment"] = {
            "status": "not_requested_due_limit",
            "reason": message,
            "call_units": call_units,
        }
        summary["not_requested"] += 1

    @staticmethod
    def _mark_not_configured(
        candidate: Candidate,
        summary: dict[str, Any],
        *,
        message: str,
        call_units: int,
    ) -> None:
        candidate["identity_status"] = "unverified_candidate"
        candidate["collector_confirmed"] = False
        candidate["enriched"] = False
        candidate["enrichment_status"] = "not_configured"
        candidate["enrichment"] = {
            "status": "not_configured",
            "reason": message,
            "call_units": call_units,
        }
        summary["not_configured"] += 1
        summary["warnings"].append(
            PersonSearchEnricher._warning_text(candidate, message=message)
        )

    @staticmethod
    def _issue(candidate: Candidate, *, code: str, message: str) -> dict[str, Any]:
        return {
            "platform": str(candidate.get("platform") or "unknown"),
            "username": PersonSearchEnricher._clean_string(candidate.get("username")),
            "code": code,
            "message": message[:500],
        }

    @staticmethod
    def _warning_text(candidate: Candidate, *, message: str) -> str:
        platform = str(candidate.get("platform") or "unknown")
        username = PersonSearchEnricher._clean_string(candidate.get("username"))
        target = f"{platform}/{username}" if username else platform
        return f"{target}: {message}"[:1_000]

    @staticmethod
    def _result_message(result: dict[str, Any]) -> str | None:
        for key in ("reason", "message", "error"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:500]
            if isinstance(value, dict):
                nested = value.get("message") or value.get("reason") or value.get("code")
                if nested:
                    return str(nested).strip()[:500]
        errors = result.get("errors") or result.get("provider_errors")
        if isinstance(errors, list) and errors:
            first = errors[0]
            if isinstance(first, dict):
                nested = first.get("message") or first.get("reason") or first.get("code")
                if nested:
                    return str(nested).strip()[:500]
            elif first:
                return str(first).strip()[:500]
        return None

    @staticmethod
    def _looks_not_configured(message: str | None) -> bool:
        if not message:
            return False
        normalized = message.casefold()
        return any(
            marker in normalized
            for marker in (
                "not configured",
                "not set",
                "missing api",
                "missing apify",
                "missing github",
                "missing reddit",
                "missing serpapi",
                "missing youtube",
            )
        )

    @staticmethod
    def _clean_string(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        cleaned = " ".join(value.split()).strip()
        return cleaned or None

    @classmethod
    def _first_string(
        cls,
        values: dict[str, Any],
        *keys: str,
        maximum: int,
    ) -> str | None:
        for key in keys:
            value = cls._clean_string(values.get(key))
            if value:
                return value[:maximum]
        return None

    @classmethod
    def _first_public_url(cls, values: dict[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = cls._clean_string(values.get(key))
            if not value or len(value) > 2_048:
                continue
            parsed = urlparse(value)
            if parsed.scheme in {"http", "https"} and parsed.hostname and not (
                parsed.username or parsed.password
            ):
                return value
        return None

    @staticmethod
    def _first_boolean(values: dict[str, Any], *keys: str) -> bool | None:
        for key in keys:
            value = values.get(key)
            if isinstance(value, bool):
                return value
        return None

    def _production_specs(self) -> dict[str, EnrichmentSpec]:
        return {
            "instagram": EnrichmentSpec(
                self._collect_instagram,
                call_units=1,
                configured=lambda: bool(
                    settings.person_search_allow_shared_provider_credentials
                    and settings.apify_api_token
                ),
            ),
            "twitter": EnrichmentSpec(
                self._collect_twitter,
                call_units=1,
                configured=lambda: bool(
                    settings.person_search_allow_shared_provider_credentials
                    and settings.apify_api_token
                ),
            ),
            "telegram": EnrichmentSpec(
                self._collect_telegram,
                call_units=0,
                configured=lambda: bool(
                    settings.person_search_allow_shared_provider_credentials
                ),
            ),
            # LinkedIn's existing adapter may try its primary Actor plus two
            # bounded same-capability fallbacks.
            "linkedin": EnrichmentSpec(
                self._collect_linkedin,
                call_units=3,
                configured=lambda: bool(
                    settings.person_search_allow_shared_provider_credentials
                    and settings.apify_api_token
                ),
            ),
            # First Reddit OAuth use may require token acquisition plus /about.
            "reddit": EnrichmentSpec(
                self._collect_reddit,
                call_units=2,
                configured=lambda: bool(
                    settings.person_search_allow_shared_provider_credentials
                    and settings.reddit_client_id
                    and settings.reddit_client_secret
                    and settings.reddit_user_agent
                ),
            ),
            "facebook": EnrichmentSpec(
                self._collect_facebook,
                call_units=1,
                configured=lambda: bool(
                    settings.person_search_allow_shared_provider_credentials
                    and settings.apify_api_token
                ),
            ),
            "tiktok": EnrichmentSpec(
                self._collect_tiktok,
                call_units=1,
                configured=lambda: bool(
                    settings.person_search_allow_shared_provider_credentials
                    and settings.apify_api_token
                ),
            ),
            "github": EnrichmentSpec(
                self._collect_github,
                call_units=1,
                configured=lambda: bool(
                    settings.person_search_allow_shared_provider_credentials
                    and settings.github_token
                ),
            ),
            "youtube": EnrichmentSpec(
                self._collect_youtube,
                call_units=1,
                configured=lambda: bool(
                    settings.person_search_allow_shared_provider_credentials
                    and settings.youtube_api_key
                ),
            ),
        }

    @staticmethod
    async def _collect_instagram(candidate: Candidate) -> dict[str, Any]:
        return await InstagramProfileService().fetch_profile(str(candidate["username"]))

    @staticmethod
    async def _collect_twitter(candidate: Candidate) -> dict[str, Any]:
        return await TwitterApifyService().get_profile(
            str(candidate["username"]),
            max_items=1,
        )

    @staticmethod
    async def _collect_telegram(candidate: Candidate) -> dict[str, Any]:
        return await TelegramDataService(use_authorized_fallback=False).get_profile(
            str(candidate["username"])
        )

    @staticmethod
    async def _collect_linkedin(candidate: Candidate) -> dict[str, Any]:
        return await LinkedInApifyService().get_profile(str(candidate["username"]))

    @staticmethod
    async def _collect_reddit(candidate: Candidate) -> dict[str, Any]:
        # Deliberately skip the combined Reddit content service.  Person search
        # needs OAuth profile metadata, not an Apify post run.
        return await RedditService().profile_service.get_profile(str(candidate["username"]))

    @staticmethod
    async def _collect_facebook(candidate: Candidate) -> dict[str, Any]:
        username = str(candidate["username"])
        target = PersonSearchEnricher._clean_string(candidate.get("profile_url"))
        if target is None:
            target = f"https://www.facebook.com/{quote(username, safe='._-')}/"
        result = await FacebookApifyService().scrape_pages([target])
        pages = result.get("pages") if isinstance(result, dict) else None
        page = next((item for item in pages or [] if isinstance(item, dict)), None)
        if page:
            return {
                **result,
                **page,
                "success": True,
                "exists": True,
                "status": "completed",
            }
        return result

    @staticmethod
    async def _collect_tiktok(candidate: Candidate) -> dict[str, Any]:
        return await TikTokApifyService(
            getattr(settings, "apify_tiktok_actor_id", "clockworks/tiktok-scraper")
        ).get_profile(str(candidate["username"]), max_items=1)

    @staticmethod
    async def _collect_github(candidate: Candidate) -> dict[str, Any]:
        return await GitHubService().get_user(str(candidate["username"]))

    @staticmethod
    async def _collect_youtube(candidate: Candidate) -> dict[str, Any]:
        target = (
            PersonSearchEnricher._clean_string(candidate.get("profile_url"))
            or str(candidate["username"])
        )
        return await YouTubeService().get_channel(target, recent_video_limit=0)


__all__ = ["EnrichmentSpec", "PersonSearchEnricher"]
