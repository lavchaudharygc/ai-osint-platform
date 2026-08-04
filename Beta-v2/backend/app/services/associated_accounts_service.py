"""Multi-signal cross-verification for associated accounts in Beta-v2.
Cross-verifies using: WMN probe hits, full name alignment, bio text matching,
external URLs, shared emails, shared domains, Telegram, dorking, SignalHire,
platform references across all scraped profiles.
"""

import re
from typing import Any, Dict, List, Set


def _extract_domains(text: str) -> Set[str]:
    """Extract domain names from text."""
    return set(re.findall(r"(?:https?://)?(?:www\.)?([a-zA-Z0-9-]+\.[a-zA-Z]{2,})", text or ""))


def _extract_emails(text: str) -> Set[str]:
    return set(re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text or ""))


def _normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.lower().strip()) if name else ""


class AssociatedAccountsService:

    @staticmethod
    def verify_account_matches(
        primary_username: str,
        wmn_hits: List[Dict[str, Any]],
        scraped_profiles: Dict[str, Any],
        dorking_results: Dict[str, Any] | None = None,
        telegram_cti: Dict[str, Any] | None = None,
    ) -> List[Dict[str, Any]]:
        """Cross-verify handles across platforms using multi-factor signal correlation.

        Signals scored:
        1. WMN direct HTTP probe match (+40 base)
        2. Full name alignment across confirmed scraped profiles (+30)
        3. Exact username handle match in bio/description (+20)
        4. Shared external domain or URL in bio (+20)
        5. Shared email across profiles (+25)
        6. Explicit cross-platform link in bio (e.g., @handle, t.me/, linkedin.com/) (+20)
        7. Telegram CTI database mention (+15)
        8. Google dorking hit for same URL (+10)
        9. Collector-confirmed scraped profile match (+25 bonus)
        """

        # Build reference signals from primary profile
        primary_name: str = ""
        primary_emails: Set[str] = set()
        primary_domains: Set[str] = set()
        primary_bios: List[str] = []

        for plat, p in scraped_profiles.items():
            if not isinstance(p, dict) or not p.get("success"):
                continue
            name = p.get("full_name") or p.get("name") or ""
            if name and not primary_name:
                primary_name = _normalize_name(name)
            bio = p.get("bio") or p.get("description") or ""
            if bio:
                primary_bios.append(bio.lower())
                primary_domains.update(_extract_domains(bio))
                primary_emails.update(_extract_emails(bio))
            for url in (p.get("external_urls") or []):
                primary_domains.update(_extract_domains(str(url)))
            if p.get("email"):
                primary_emails.add(str(p["email"]).lower())

        # Collect domains from dorking
        dork_urls: Set[str] = set()
        if dorking_results:
            for hit in (dorking_results.get("results") or []):
                if isinstance(hit, dict) and hit.get("url"):
                    dork_urls.add(hit["url"].lower())

        # Collect usernames/emails from telegram CTI breaches
        cti_subjects: Set[str] = set()
        if telegram_cti:
            for res in (telegram_cti.get("results") or []):
                for record in (res.get("data") or []):
                    if isinstance(record, dict):
                        for field in ("username", "email", "phone", "name"):
                            val = str(record.get(field) or "").lower().strip()
                            if val and len(val) > 2:
                                cti_subjects.add(val)

        results: List[Dict[str, Any]] = []

        for hit in wmn_hits:
            site = hit.get("site") or "Unknown"
            url = hit.get("url") or ""
            handle = hit.get("handle") or primary_username.lstrip("@")
            category = hit.get("category") or "general"

            confidence = 40  # Base: WMN HTTP probe confirmed
            reasons: List[str] = ["WMN template HTTP probe: account found"]
            match_status = "PROBE_CONFIRMED"

            # Check for collector-confirmed scrape on this platform
            scraped = scraped_profiles.get(site.lower()) or scraped_profiles.get(site.replace(" ", "").lower())
            if isinstance(scraped, dict) and scraped.get("success"):
                confidence += 25
                reasons.append("Collector-confirmed: platform scraper returned data")
                match_status = "COLLECTOR_CONFIRMED"

                # Name alignment
                scraped_name = _normalize_name(scraped.get("full_name") or scraped.get("name") or "")
                if primary_name and scraped_name and (
                    primary_name in scraped_name or scraped_name in primary_name
                ):
                    confidence += 30
                    reasons.append(f"Full name match: '{scraped_name}'")
                    match_status = "IDENTITY_CONFIRMED"

                # Shared domain in bio
                scraped_bio = scraped.get("bio") or scraped.get("description") or ""
                if primary_domains:
                    scraped_domains = _extract_domains(scraped_bio)
                    shared = primary_domains & scraped_domains
                    if shared:
                        confidence += 20
                        reasons.append(f"Shared domain in bio: {', '.join(list(shared)[:3])}")

                # Shared email
                scraped_emails = _extract_emails(scraped_bio)
                if scraped.get("email"):
                    scraped_emails.add(str(scraped["email"]).lower())
                shared_emails = primary_emails & scraped_emails
                if shared_emails:
                    confidence += 25
                    reasons.append(f"Shared email: {', '.join(list(shared_emails)[:2])}")

            # Cross-platform mention in any primary bio
            handle_lower = handle.lower()
            for bio_text in primary_bios:
                if handle_lower in bio_text or f"@{handle_lower}" in bio_text:
                    confidence += 20
                    reasons.append("Handle mentioned in primary profile bio")
                    break
                # Platform-specific URL mention
                site_lower = site.lower().replace(" ", "")
                if site_lower in bio_text and handle_lower in bio_text:
                    confidence += 20
                    reasons.append(f"Platform '{site}' + handle mentioned in bio")
                    break

            # Dorking confirmation
            if any(url.lower() in dork_url or handle_lower in dork_url for dork_url in dork_urls):
                confidence += 10
                reasons.append("Google dorking result references this URL/handle")

            # Telegram CTI subject match
            if handle_lower in cti_subjects or f"@{handle_lower}" in cti_subjects:
                confidence += 15
                reasons.append("Handle found in Telegram CTI breach database")

            results.append({
                "platform": site,
                "category": category,
                "username": handle,
                "url": url,
                "confidence": min(100, confidence),
                "match_status": match_status,
                "reasons": reasons,
            })

        return sorted(results, key=lambda x: x["confidence"], reverse=True)
