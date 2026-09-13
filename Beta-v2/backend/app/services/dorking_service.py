"""Bounded SerpAPI-only Google dorking with diverse, de-duplicated results."""

from __future__ import annotations

import ipaddress
import logging
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from app.config import settings


logger = logging.getLogger(__name__)

SERPAPI_SEARCH_URL = "https://serpapi.com/search.json"
_UNSET = object()
_SUPPORTED_KINDS = {"email", "phone", "domain", "name", "username"}
_TRACKING_PARAMETERS = {
    "fbclid",
    "gclid",
    "igshid",
    "mc_cid",
    "mc_eid",
}


def _hostname_matches(hostname: str, domains: tuple[str, ...]) -> bool:
    host = hostname.casefold().removeprefix("www.")
    return any(host == domain or host.endswith(f".{domain}") for domain in domains)


def categorize_dork_hit(url: str, title: str, snippet: str) -> str:
    """Classify one organic result using its real hostname before text clues."""

    hostname = (urlsplit(url).hostname or "").casefold()
    combined = f"{url} {title} {snippet}".casefold()
    if _hostname_matches(hostname, ("github.com", "gitlab.com", "bitbucket.org")):
        return "Code Repositories"
    if _hostname_matches(
        hostname,
        (
            "linkedin.com",
            "twitter.com",
            "x.com",
            "instagram.com",
            "facebook.com",
            "tiktok.com",
            "youtube.com",
            "reddit.com",
            "t.me",
        ),
    ):
        return "Social Profiles"
    if re.search(r"\.(?:pdf|docx?|xlsx?|csv)(?:$|[?#])", url, re.IGNORECASE):
        return "Public Documents"
    if any(token in combined for token in ("dump", "leak", "breach", "confidential")):
        return "Leaked Documents"
    if any(token in combined for token in ("email", "phone", "contact", "address", "tel:")):
        return "Contact Details"
    if any(token in combined for token in ("news", "article", "press release", "report")):
        return "News & Mentions"
    return "Public Records"


def _clean_target(value: Any) -> str:
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    # A searched value is always quoted by the query builder. Removing embedded
    # quotes prevents the value from changing the intended Google operators.
    text = re.sub(r'["“”]+', " ", text)
    return re.sub(r"\s+", " ", text).strip()[:200]


def _infer_input_kind(value: str) -> str:
    if "@" in value and "." in value and " " not in value:
        return "email"
    if value.replace("+", "").replace(" ", "").replace("-", "").isdigit():
        return "phone"
    if value.startswith(("http://", "https://")) or ("." in value and " " not in value):
        return "domain"
    return "name" if " " in value else "username"


def _domain_target(value: str) -> str:
    candidate = value if "://" in value else f"//{value}"
    try:
        hostname = urlsplit(candidate).hostname
    except ValueError:
        hostname = None
    fallback = value.split("/", 1)[0].split(" ", 1)[0]
    return (hostname or fallback).strip().strip(".").casefold()[:253]


def _is_public_hostname(hostname: str) -> bool:
    host = hostname.casefold().rstrip(".")
    if not host or host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        return True


def _normalized_public_url(value: Any) -> tuple[str, str] | None:
    if not isinstance(value, str):
        return None
    raw = value.strip()[:2_048]
    try:
        parsed = urlsplit(raw)
        hostname = parsed.hostname
        if (
            parsed.scheme.casefold() not in {"http", "https"}
            or not hostname
            or parsed.username
            or parsed.password
            or not _is_public_hostname(hostname)
        ):
            return None
        port = parsed.port
    except (TypeError, ValueError):
        return None

    scheme = parsed.scheme.casefold()
    host = hostname.casefold().rstrip(".")
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    netloc = host if not port or default_port else f"{host}:{port}"
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/") or "/"
    query_items = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if key.casefold() not in _TRACKING_PARAMETERS
        and not key.casefold().startswith("utm_")
    ]
    normalized = urlunsplit((scheme, netloc, path, urlencode(query_items, doseq=True), ""))
    key_host = host.removeprefix("www.")
    dedupe_key = urlunsplit((scheme, key_host, path, urlencode(sorted(query_items)), ""))
    return normalized, dedupe_key


class DorkingService:
    """Discover public indexed references without cross-provider fallback."""

    PROVIDER = "serpapi"

    def __init__(
        self,
        *,
        api_key: str | None | object = _UNSET,
        enabled: bool | None = None,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        max_queries: int | None = None,
        results_per_query: int | None = None,
        max_results: int | None = None,
        country_code: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        configured_key = settings.serpapi_key if api_key is _UNSET else api_key
        self.api_key = (
            str(configured_key).strip()
            if isinstance(configured_key, str) and configured_key.strip()
            else None
        )
        self.enabled = bool(settings.dorking_enabled if enabled is None else enabled)
        # Production routing is fixed. The override is solely an explicit seam
        # for an injected MockTransport in offline tests.
        self.base_url = str(SERPAPI_SEARCH_URL if base_url is None else base_url).strip()
        self.timeout_seconds = max(
            2.0,
            min(
                float(settings.dorking_timeout_seconds if timeout_seconds is None else timeout_seconds),
                30.0,
            ),
        )
        self.max_queries = max(
            1,
            min(int(settings.dorking_max_queries if max_queries is None else max_queries), 5),
        )
        self.results_per_query = max(
            1,
            min(
                int(
                    settings.dorking_results_per_query
                    if results_per_query is None
                    else results_per_query
                ),
                10,
            ),
        )
        self.max_results = max(
            1,
            min(int(settings.dorking_max_results if max_results is None else max_results), 50),
        )
        configured_country = (
            settings.dorking_country_code if country_code is None else country_code
        )
        country = str(configured_country or "").strip().casefold()
        self.country_code = country if re.fullmatch(r"[a-z]{2}", country) else "in"
        self.transport = transport

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def build_query_plan(
        self,
        query: str,
        kind: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, str]]:
        """Build balanced, target-bound Google searches for the input type."""

        target = _clean_target(query)
        if not target:
            return []
        input_kind = kind if kind in _SUPPORTED_KINDS else _infer_input_kind(target)
        requested_limit = self.max_queries if limit is None else max(0, int(limit))
        query_limit = min(requested_limit, self.max_queries)
        quoted = f'"{target}"'

        social_sites = (
            "site:instagram.com OR site:facebook.com OR site:tiktok.com OR "
            "site:youtube.com OR site:reddit.com OR site:t.me"
        )
        professional_sites = (
            "site:linkedin.com OR site:github.com OR site:gitlab.com OR "
            "site:x.com OR site:twitter.com"
        )
        document_types = (
            "filetype:pdf OR filetype:doc OR filetype:docx OR "
            "filetype:xls OR filetype:xlsx OR filetype:csv"
        )

        if input_kind == "phone":
            digits = re.sub(r"\D", "", target)
            national = digits[-10:] if len(digits) >= 10 else digits
            variants = list(dict.fromkeys(value for value in (target, digits, national) if value))
            exact_group = "(" + " OR ".join(f'"{value}"' for value in variants) + ")"
            plans = [
                {"name": "Exact phone mentions", "query": exact_group},
                {"name": "Social profiles", "query": f"{exact_group} ({social_sites})"},
                {
                    "name": "Contact and directory references",
                    "query": f"{exact_group} (contact OR phone OR mobile OR whatsapp)",
                },
                {"name": "Public documents", "query": f"{exact_group} ({document_types})"},
                {
                    "name": "Indian directories and discussions",
                    "query": (
                        f"{exact_group} (site:justdial.com OR site:indiamart.com OR "
                        "site:sulekha.com OR site:reddit.com)"
                    ),
                },
            ]
        elif input_kind == "domain":
            domain = _domain_target(target)
            domain_exact = f'"{domain}"'
            plans = [
                {"name": "External domain mentions", "query": domain_exact},
                {"name": "Indexed site pages", "query": f"site:{domain}"},
                {
                    "name": "Code and professional references",
                    "query": f"{domain_exact} ({professional_sites})",
                },
                {
                    "name": "Contact and organization references",
                    "query": f"{domain_exact} (contact OR about OR address OR phone OR email)",
                },
                {"name": "Public documents", "query": f"{domain_exact} ({document_types})"},
            ]
        elif input_kind == "email":
            local_part, _, domain = target.partition("@")
            plans = [
                {"name": "Exact email mentions", "query": quoted},
                {
                    "name": "Professional and code profiles",
                    "query": f"{quoted} ({professional_sites})",
                },
                {"name": "Social and community profiles", "query": f"{quoted} ({social_sites})"},
                {"name": "Public documents", "query": f"{quoted} ({document_types})"},
                {
                    "name": "Account-name and domain correlation",
                    "query": f'"{local_part}" "{domain}" (profile OR author OR contact)',
                },
            ]
        else:
            identity_label = "Exact name mentions" if input_kind == "name" else "Exact username mentions"
            plans = [
                {"name": identity_label, "query": quoted},
                {
                    "name": "Professional and code profiles",
                    "query": f"{quoted} ({professional_sites})",
                },
                {"name": "Social and community profiles", "query": f"{quoted} ({social_sites})"},
                {
                    "name": "Contact and directory references",
                    "query": f"{quoted} (email OR contact OR phone OR address OR profile)",
                },
                {"name": "Public documents", "query": f"{quoted} ({document_types})"},
            ]

        return plans[:query_limit]

    async def run_dorks(
        self,
        query: str,
        limit: int | None = None,
        kind: str | None = None,
        *,
        input_kind: str | None = None,
        query_limit: int | None = None,
    ) -> dict[str, Any]:
        """Execute a bounded query plan and preserve valid partial results."""

        effective_kind = input_kind or kind
        effective_limit = query_limit if query_limit is not None else limit
        cleaned_target = _clean_target(query)
        inferred_kind = (
            effective_kind
            if effective_kind in _SUPPORTED_KINDS
            else _infer_input_kind(cleaned_target)
        )
        plan = self.build_query_plan(query, inferred_kind, effective_limit)

        if not self.enabled:
            self._log_terminal("disabled", inferred_kind, len(plan))
            return self._terminal_response(
                status="disabled",
                plan=plan,
                error_code="disabled",
                error="Google dorking is disabled by server policy.",
            )
        if not self.api_key:
            self._log_terminal("not_configured", inferred_kind, len(plan))
            return self._terminal_response(
                status="not_configured",
                plan=plan,
                error_code="not_configured",
                error="SERPAPI_KEY is required for Google dorking.",
            )
        if not plan:
            self._log_terminal("skipped", inferred_kind, 0)
            limit_is_zero = bool(cleaned_target)
            return self._terminal_response(
                status="skipped",
                plan=[],
                error_code="query_limit_zero" if limit_is_zero else "invalid_input",
                error=(
                    "Google dorking was skipped because the query limit is zero."
                    if limit_is_zero
                    else "A non-empty target is required for Google dorking."
                ),
            )

        summaries = [
            {
                "category": item["name"],
                "query": item["query"],
                "status": "not_run",
                "result_count": 0,
            }
            for item in plan
        ]
        buckets: list[list[dict[str, Any]]] = [[] for _item in plan]
        queries_attempted = 0
        queries_completed = 0
        invalid_results_removed = 0
        failure: dict[str, str] | None = None

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                transport=self.transport,
                follow_redirects=False,
            ) as client:
                for index, item in enumerate(plan):
                    queries_attempted += 1
                    params = {
                        "q": item["query"],
                        "api_key": self.api_key,
                        "engine": "google",
                        "num": self.results_per_query,
                        "hl": "en",
                        "gl": self.country_code,
                        "filter": "0",
                        "safe": "active",
                    }
                    try:
                        response = await client.get(self.base_url, params=params)
                    except httpx.TimeoutException:
                        failure = self._failure("timeout")
                        summaries[index]["status"] = "timeout"
                        self._log_failure("timeout", queries_attempted)
                        break
                    except httpx.HTTPError:
                        failure = self._failure("network_error")
                        summaries[index]["status"] = "network_error"
                        self._log_failure("network_error", queries_attempted)
                        break

                    payload = self._json_payload(response)
                    failure_code = self._response_failure_code(response, payload)
                    if failure_code:
                        failure = self._failure(failure_code)
                        summaries[index]["status"] = failure_code
                        self._log_failure(
                            failure_code,
                            queries_attempted,
                            http_status=response.status_code,
                        )
                        break

                    queries_completed += 1
                    summaries[index]["status"] = "completed"
                    organic = self._organic_results(payload)
                    for fallback_position, organic_item in enumerate(
                        organic[: self.results_per_query],
                        start=1,
                    ):
                        row = self._normalize_result(
                            organic_item,
                            query=item["query"],
                            query_category=item["name"],
                            fallback_position=fallback_position,
                        )
                        if row is None:
                            invalid_results_removed += 1
                            continue
                        buckets[index].append(row)
                    summaries[index]["result_count"] = len(buckets[index])
        except (TypeError, ValueError, httpx.InvalidURL) as exc:
            failure = self._failure("configuration_error")
            self._log_failure(
                "configuration_error",
                queries_attempted,
                error_type=type(exc).__name__,
            )

        merged, raw_count, unique_count, duplicates_removed = self._merge_buckets(buckets)
        results = merged[: self.max_results]
        truncated = max(0, unique_count - len(results))

        if failure:
            status = "partial" if queries_completed else failure["code"]
        else:
            status = "completed" if results else "no_results"

        logger.info(
            "event=dorking_completed provider=serpapi status=%s input_kind=%s "
            "calls_made=%d queries_completed=%d raw_valid_results=%d "
            "unique_results_found=%d results_returned=%d duplicates_removed=%d "
            "invalid_results_removed=%d",
            status,
            inferred_kind,
            queries_attempted,
            queries_completed,
            raw_count,
            unique_count,
            len(results),
            duplicates_removed,
            invalid_results_removed,
        )
        return {
            "status": status,
            "provider": self.PROVIDER,
            "configured": True,
            "attempted_providers": [self.PROVIDER] if queries_attempted else [],
            "queries_planned": len(plan),
            "queries_attempted": queries_attempted,
            "queries_run": queries_completed,
            "queries_failed": 1 if failure else 0,
            "calls_made": queries_attempted,
            "query_limit": self.max_queries,
            "result_limit": self.max_results,
            "results_per_query": self.results_per_query,
            "query_summaries": summaries,
            "raw_results_count": raw_count,
            "invalid_results_removed": invalid_results_removed,
            "duplicates_removed": duplicates_removed,
            "results_truncated": truncated,
            "results_count": len(results),
            "results": results,
            "partial": status == "partial",
            "fallback_used": False,
            "error_code": failure["code"] if failure else None,
            "error": failure["message"] if failure else None,
        }

    def _terminal_response(
        self,
        *,
        status: str,
        plan: list[dict[str, str]],
        error_code: str,
        error: str,
    ) -> dict[str, Any]:
        return {
            "status": status,
            "provider": self.PROVIDER,
            "configured": self.is_configured(),
            "attempted_providers": [],
            "queries_planned": len(plan),
            "queries_attempted": 0,
            "queries_run": 0,
            "queries_failed": 0,
            "calls_made": 0,
            "query_limit": self.max_queries,
            "result_limit": self.max_results,
            "results_per_query": self.results_per_query,
            "query_summaries": [
                {
                    "category": item["name"],
                    "query": item["query"],
                    "status": "not_run",
                    "result_count": 0,
                }
                for item in plan
            ],
            "raw_results_count": 0,
            "invalid_results_removed": 0,
            "duplicates_removed": 0,
            "results_truncated": 0,
            "results_count": 0,
            "results": [],
            "partial": False,
            "fallback_used": False,
            "error_code": error_code,
            "error": error,
        }

    @staticmethod
    def _json_payload(response: httpx.Response) -> dict[str, Any] | None:
        try:
            payload = response.json()
        except ValueError:
            return None
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _organic_results(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
        if not isinstance(payload, dict) or not isinstance(payload.get("organic_results"), list):
            return []
        return [item for item in payload["organic_results"] if isinstance(item, dict)]

    @staticmethod
    def _response_failure_code(
        response: httpx.Response,
        payload: dict[str, Any] | None,
    ) -> str | None:
        if response.status_code == 429:
            return "rate_limited"
        if response.status_code == 402:
            return "quota_exhausted"
        if response.status_code in {401, 403}:
            return "authentication_error"
        if payload is None:
            return "provider_error" if response.is_error else "invalid_response"
        provider_error = str(payload.get("error") or "").casefold()
        if provider_error:
            if any(
                token in provider_error
                for token in ("quota", "credit", "out of searches", "limit reached")
            ):
                return "quota_exhausted"
            if any(
                token in provider_error
                for token in ("api key", "api_key", "authentication", "unauthorized")
            ):
                return "authentication_error"
            if "rate" in provider_error:
                return "rate_limited"
            return "provider_error"
        metadata = payload.get("search_metadata")
        if isinstance(metadata, dict) and str(metadata.get("status") or "").casefold() == "error":
            return "provider_error"
        return "provider_error" if response.is_error else None

    @staticmethod
    def _failure(code: str) -> dict[str, str]:
        messages = {
            "timeout": "The Google search provider timed out.",
            "network_error": "The Google search provider could not be reached.",
            "rate_limited": "The Google search provider rate limited the request.",
            "quota_exhausted": "The Google search provider quota is exhausted.",
            "authentication_error": "The Google search provider rejected its credential.",
            "invalid_response": "The Google search provider returned an invalid response.",
            "configuration_error": "The Google search provider is not configured correctly.",
            "provider_error": "The Google search provider returned an error.",
        }
        return {"code": code, "message": messages.get(code, messages["provider_error"])}

    @staticmethod
    def _log_failure(
        reason: str,
        attempt: int,
        *,
        http_status: int | None = None,
        error_type: str | None = None,
    ) -> None:
        logger.warning(
            "event=dorking_provider_failed provider=serpapi reason=%s attempt=%d "
            "http_status=%s error_type=%s",
            reason,
            attempt,
            http_status if http_status is not None else "none",
            error_type or "none",
        )

    @staticmethod
    def _log_terminal(status: str, input_kind: str, queries_planned: int) -> None:
        logger.info(
            "event=dorking_skipped provider=serpapi status=%s input_kind=%s "
            "queries_planned=%d calls_made=0",
            status,
            input_kind,
            queries_planned,
        )

    @staticmethod
    def _normalize_result(
        item: dict[str, Any],
        *,
        query: str,
        query_category: str,
        fallback_position: int,
    ) -> dict[str, Any] | None:
        normalized_url = _normalized_public_url(item.get("link") or item.get("url"))
        if normalized_url is None:
            return None
        url, dedupe_key = normalized_url
        hostname = urlsplit(url).hostname or ""
        try:
            position = max(1, min(int(item.get("position") or fallback_position), 1_000))
        except (TypeError, ValueError):
            position = fallback_position
        title = str(item.get("title") or hostname)[:300]
        snippet = str(
            item.get("snippet")
            or item.get("description")
            or item.get("text")
            or ""
        )[:1_000]
        return {
            "category": categorize_dork_hit(url, title, snippet),
            "title": title,
            "domain": str(item.get("displayed_link") or hostname)[:300],
            "url": url,
            "snippet": snippet,
            "query": query,
            "query_category": query_category,
            "matched_queries": [query_category],
            "query_categories": [query_category],
            "position": position,
            "date": str(item.get("date") or "")[:100] or None,
            "source": "serpapi",
            "_dedupe_key": dedupe_key,
        }

    @staticmethod
    def _merge_buckets(
        buckets: list[list[dict[str, Any]]],
    ) -> tuple[list[dict[str, Any]], int, int, int]:
        """Round-robin query buckets so one broad query cannot hide diversity."""

        raw_count = sum(len(bucket) for bucket in buckets)
        merged: list[dict[str, Any]] = []
        by_key: dict[str, dict[str, Any]] = {}
        max_bucket = max((len(bucket) for bucket in buckets), default=0)
        for offset in range(max_bucket):
            for bucket in buckets:
                if offset >= len(bucket):
                    continue
                row = dict(bucket[offset])
                key = str(row.pop("_dedupe_key"))
                existing = by_key.get(key)
                if existing is not None:
                    category = str(row.get("query_category") or "")
                    if category and category not in existing["matched_queries"]:
                        existing["matched_queries"].append(category)
                        existing["query_categories"].append(category)
                    continue
                by_key[key] = row
                merged.append(row)
        unique_count = len(merged)
        return merged, raw_count, unique_count, max(0, raw_count - unique_count)


__all__ = ["DorkingService", "SERPAPI_SEARCH_URL", "categorize_dork_hit"]
