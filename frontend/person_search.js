(function (root, factory) {
    const api = factory(root || {});
    if (typeof module === "object" && module.exports) {
        module.exports = api;
    }
    if (root) {
        root.PersonSearchUI = api;
    }
})(typeof window !== "undefined" ? window : globalThis, function (root) {
    "use strict";

    const API_BASE = "http://127.0.0.1:8010";
    const IDENTITY_NOTICE = "Name matches are unverified candidates, not proof that profiles belong to the same person. Corroborate with independent public evidence.";
    const PLATFORM_ORDER = [
        "linkedin",
        "github",
        "twitter",
        "instagram",
        "facebook",
        "tiktok",
        "reddit",
        "youtube",
        "telegram"
    ];
    const PLATFORM_LABELS = {
        linkedin: "LinkedIn",
        github: "GitHub",
        twitter: "Twitter / X",
        instagram: "Instagram",
        facebook: "Facebook",
        tiktok: "TikTok",
        reddit: "Reddit",
        youtube: "YouTube",
        telegram: "Telegram"
    };
    const STATUS_LABELS = {
        completed: "Completed",
        completed_with_warnings: "Completed with warnings",
        partial: "Partial result",
        not_found: "No candidates found",
        empty_dataset: "No candidates found",
        not_configured: "Setup required",
        rate_limited: "Rate limited",
        provider_error: "Provider error",
        budget_exhausted: "Provider budget exhausted",
        failed: "Search failed"
    };
    const ABSOLUTE_LIMITS = {
        profiles: 50,
        queries: 8,
        provider_calls: 20,
        enrichments: 8
    };

    let initialized = false;
    let statusLoaded = false;
    let statusData = null;
    let currentResult = null;
    let busy = false;
    let requestEpoch = 0;
    let activeController = null;

    function escapeHTML(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function safeExternalUrl(value) {
        if (!value) return "";
        try {
            const parsed = new URL(String(value));
            return ["http:", "https:"].includes(parsed.protocol) ? parsed.href : "";
        } catch (_) {
            return "";
        }
    }

    function safeImageSource(value) {
        const source = String(value || "");
        if (/^data:image\/(?:png|jpe?g|gif|webp);base64,/i.test(source)) return source;
        return safeExternalUrl(source);
    }

    function list(value) {
        return Array.isArray(value) ? value : [];
    }

    function record(value) {
        return value && typeof value === "object" && !Array.isArray(value) ? value : {};
    }

    function normalizeHumanText(value, fieldName, required = false) {
        const raw = String(value ?? "");
        if (/[\u0000-\u001f\u007f-\u009f\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]/u.test(raw)) {
            throw new Error(`${fieldName} cannot contain control or invisible characters.`);
        }
        const normalized = raw.replace(/\s+/gu, " ").trim();
        if (required && !normalized) {
            throw new Error(`${fieldName} is required.`);
        }
        return normalized;
    }

    function boundedInteger(value, minimum, maximum, fieldName, optional = false) {
        if ((value === "" || value === null || value === undefined) && optional) return null;
        const parsed = Number(value);
        if (!Number.isInteger(parsed) || parsed < minimum || parsed > maximum) {
            throw new Error(`${fieldName} must be a whole number from ${minimum} to ${maximum}.`);
        }
        return parsed;
    }

    function serverLimit(value, fallback, minimum = 1) {
        const parsed = Number(value);
        if (!Number.isFinite(parsed) || parsed < minimum) return fallback;
        return Math.min(parsed, fallback);
    }

    function buildPersonSearchRequest(values = {}, serverLimits = {}) {
        const limits = {
            profiles: serverLimit(serverLimits.profiles, ABSOLUTE_LIMITS.profiles),
            queries: serverLimit(serverLimits.queries, ABSOLUTE_LIMITS.queries),
            provider_calls: serverLimit(serverLimits.provider_calls, ABSOLUTE_LIMITS.provider_calls),
            enrichments: serverLimit(serverLimits.enrichments, ABSOLUTE_LIMITS.enrichments, 0)
        };
        const fullName = normalizeHumanText(values.full_name, "Full name", true);
        if (fullName.length < 2 || fullName.length > 200) {
            throw new Error("Full name must contain 2 to 200 characters.");
        }

        const location = normalizeHumanText(values.location, "Location");
        const organization = normalizeHumanText(values.organization, "Organization");
        const countryCode = normalizeHumanText(values.country_code, "Country code").toUpperCase();
        if (location.length > 200) throw new Error("Location must contain at most 200 characters.");
        if (organization.length > 200) throw new Error("Organization must contain at most 200 characters.");
        if (countryCode && !/^[A-Z]{2}$/.test(countryCode)) {
            throw new Error("Country code must contain exactly two letters, such as IN or GB.");
        }

        const requested = new Set(list(values.platforms).map(value => String(value || "").trim().toLowerCase()));
        const unsupported = [...requested].filter(value => value && !PLATFORM_ORDER.includes(value));
        if (unsupported.length) {
            throw new Error(`Unsupported platform: ${unsupported.join(", ")}.`);
        }
        const platforms = PLATFORM_ORDER.filter(platform => requested.has(platform));
        if (!platforms.length) {
            throw new Error("Select at least one platform to search.");
        }

        const maxProfiles = boundedInteger(values.max_profiles ?? 20, 1, limits.profiles, "Maximum profiles");
        const queryLimit = boundedInteger(values.query_limit, 1, limits.queries, "Query limit", true);
        const providerCallLimit = boundedInteger(values.provider_call_limit, 1, limits.provider_calls, "Provider call limit", true);
        const enrichProfiles = values.enrich_profiles === true;
        const maxEnrichments = enrichProfiles
            ? boundedInteger(values.max_enrichments ?? 4, 0, limits.enrichments, "Maximum enrichments")
            : null;

        const payload = {
            full_name: fullName,
            platforms,
            max_profiles: maxProfiles,
            enrich_profiles: enrichProfiles
        };
        if (location) payload.location = location;
        if (organization) payload.organization = organization;
        if (countryCode) payload.country_code = countryCode;
        if (queryLimit !== null) payload.query_limit = queryLimit;
        if (providerCallLimit !== null) payload.provider_call_limit = providerCallLimit;
        if (enrichProfiles) payload.max_enrichments = maxEnrichments;
        return payload;
    }

    function shellMarkup() {
        const platforms = PLATFORM_ORDER.map(platform => `
            <label class="person-platform-option">
                <input type="checkbox" value="${platform}" data-person-platform checked>
                <span>${escapeHTML(PLATFORM_LABELS[platform])}</span>
            </label>`).join("");

        return `
            <div class="person-search-layout">
                <section class="glass-card person-search-panel" aria-labelledby="person-search-form-title">
                    <div class="card-header-bar person-search-header">
                        <div>
                            <span class="card-title" id="person-search-form-title">Person Search Parameters</span>
                            <p class="person-search-kicker">Exact-name public profile discovery</p>
                        </div>
                        <span class="person-readiness-badge is-checking" id="person-search-readiness-badge">CHECKING</span>
                    </div>

                    <div class="person-readiness-panel is-checking" id="person-search-readiness" role="status" aria-live="polite">
                        <div class="person-readiness-heading">
                            <span class="person-readiness-dot" aria-hidden="true"></span>
                            <strong id="person-search-readiness-title">Checking person-search service</strong>
                            <button type="button" class="person-text-button" id="person-search-status-refresh">Retry</button>
                        </div>
                        <p id="person-search-readiness-detail">Reading readiness and safe server limits...</p>
                    </div>

                    <form id="person-search-form" novalidate>
                        <div class="form-row">
                            <label for="person-full-name">Full Name <span class="person-required">Required</span></label>
                            <input type="text" id="person-full-name" class="form-control" minlength="2" maxlength="200" autocomplete="off" placeholder="e.g. Ada Lovelace" required>
                        </div>

                        <div class="person-search-field-grid">
                            <div class="form-row">
                                <label for="person-location">Location <span class="person-optional">Optional</span></label>
                                <input type="text" id="person-location" class="form-control" maxlength="200" autocomplete="off" placeholder="City or region">
                            </div>
                            <div class="form-row">
                                <label for="person-country-code">Country <span class="person-optional">Optional</span></label>
                                <input type="text" id="person-country-code" class="form-control mono" minlength="2" maxlength="2" autocomplete="off" placeholder="IN">
                            </div>
                        </div>

                        <div class="form-row">
                            <label for="person-organization">Organization <span class="person-optional">Optional</span></label>
                            <input type="text" id="person-organization" class="form-control" maxlength="200" autocomplete="off" placeholder="Employer, university, or group">
                        </div>

                        <fieldset class="person-platform-fieldset">
                            <legend class="person-fieldset-heading">
                                <span>Platforms</span>
                                <span>
                                    <button type="button" class="person-text-button" id="person-platform-select-all">Select all</button>
                                    <span aria-hidden="true">·</span>
                                    <button type="button" class="person-text-button" id="person-platform-clear">Clear</button>
                                </span>
                            </legend>
                            <div class="person-platform-grid">${platforms}</div>
                        </fieldset>

                        <div class="form-row">
                            <label for="person-max-profiles">Maximum Profile Candidates</label>
                            <input type="number" id="person-max-profiles" class="form-control" min="1" max="50" step="1" value="20">
                        </div>

                        <label class="person-enrichment-toggle" for="person-enrich-profiles">
                            <input type="checkbox" id="person-enrich-profiles">
                            <span class="person-toggle-control" aria-hidden="true"></span>
                            <span>
                                <strong>Enrich discovered profiles</strong>
                                <small id="person-enrichment-help">Off by default. Enabling this authorizes additional provider calls only for discovered candidates.</small>
                            </span>
                        </label>

                        <details class="person-advanced-inputs">
                            <summary>Advanced Search Limits</summary>
                            <div class="person-advanced-body">
                                <p>Optional values may lower, but never raise, server-owned limits.</p>
                                <div class="person-search-field-grid">
                                    <div class="form-row">
                                        <label for="person-query-limit">Query Limit</label>
                                        <input type="number" id="person-query-limit" class="form-control" min="1" max="8" step="1" placeholder="Server default">
                                    </div>
                                    <div class="form-row">
                                        <label for="person-provider-call-limit">Provider Call Limit</label>
                                        <input type="number" id="person-provider-call-limit" class="form-control" min="1" max="20" step="1" placeholder="Server default">
                                    </div>
                                </div>
                                <div class="form-row person-enrichment-limit is-disabled" id="person-enrichment-limit-row">
                                    <label for="person-max-enrichments">Maximum Enrichments</label>
                                    <input type="number" id="person-max-enrichments" class="form-control" min="0" max="8" step="1" value="4" disabled>
                                </div>
                            </div>
                        </details>

                        <div class="person-isolation-note">
                            <strong>Isolated workflow</strong>
                            <span>This search does not alter username investigations, case history, risk scoring, or reports.</span>
                        </div>

                        <button class="btn-scan person-search-submit" id="person-search-submit" type="submit" disabled>
                            Search Public Profiles
                        </button>
                    </form>
                </section>

                <section class="results-workspace person-search-workspace" aria-live="polite">
                    <div class="workspace-empty" id="person-search-empty-state">
                        <span class="workspace-empty-icon person-empty-icon" aria-hidden="true">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="10" cy="8" r="4"></circle><path d="M3 20c.8-4 3.1-6 7-6 2.1 0 3.8.6 5 1.7"></path><circle cx="18" cy="18" r="3"></circle><line x1="20.2" y1="20.2" x2="22" y2="22"></line></svg>
                        </span>
                        <p class="person-empty-title">Person Search Ready</p>
                        <p>Enter an exact full name. Location and organization can narrow same-name results.</p>
                        <span class="person-empty-footnote">Every result remains an unverified identity candidate until independently corroborated.</span>
                    </div>
                    <div class="person-search-alert" id="person-search-alert" hidden></div>
                    <div class="person-search-results" id="person-search-results" hidden></div>
                </section>
            </div>`;
    }

    function element(id, doc = root.document) {
        return doc && typeof doc.getElementById === "function" ? doc.getElementById(id) : null;
    }

    function setHidden(target, hidden) {
        if (!target) return;
        target.hidden = hidden;
        target.style.display = hidden ? "none" : "";
    }

    function setSearchEnabled(enabled, doc = root.document) {
        const submit = element("person-search-submit", doc);
        if (submit) submit.disabled = !enabled || busy;
    }

    function applyServerLimits(limits = {}, doc = root.document) {
        const mappings = [
            ["person-max-profiles", "profiles", 20],
            ["person-query-limit", "queries", null],
            ["person-provider-call-limit", "provider_calls", null],
            ["person-max-enrichments", "enrichments", 4]
        ];
        mappings.forEach(([id, key, fallback]) => {
            const input = element(id, doc);
            const minimum = key === "enrichments" ? 0 : 1;
            const maximum = serverLimit(limits[key], ABSOLUTE_LIMITS[key], minimum);
            if (!input) return;
            input.max = String(maximum);
            if (input.value && Number(input.value) > maximum) input.value = String(maximum);
            if (!input.value && fallback !== null) input.value = String(Math.min(fallback, maximum));
        });
    }

    function updateEnrichmentControl(doc = root.document) {
        const toggle = element("person-enrich-profiles", doc);
        const input = element("person-max-enrichments", doc);
        const row = element("person-enrichment-limit-row", doc);
        const enabled = Boolean(toggle && toggle.checked && !toggle.disabled);
        if (input) input.disabled = !enabled;
        if (row && row.classList) row.classList.toggle("is-disabled", !enabled);
    }

    function applyReadiness(data, doc = root.document) {
        const readiness = element("person-search-readiness", doc);
        const badge = element("person-search-readiness-badge", doc);
        const title = element("person-search-readiness-title", doc);
        const detail = element("person-search-readiness-detail", doc);
        const toggle = element("person-enrich-profiles", doc);
        const help = element("person-enrichment-help", doc);
        const isReady = Boolean(data && data.enabled && data.configured);
        const state = isReady ? "ready" : "setup";

        [readiness, badge].forEach(target => {
            if (!target) return;
            target.className = target === badge
                ? `person-readiness-badge is-${state}`
                : `person-readiness-panel is-${state}`;
        });
        if (badge) badge.innerText = isReady ? "READY" : "SETUP REQUIRED";
        if (title) title.innerText = isReady ? "Person-search discovery is ready" : "Person-search setup is required";

        const required = list(data && data.required_environment);
        if (detail) {
            detail.innerText = isReady
                ? `Discovery: ${String(data.discovery_provider || "SerpAPI").toUpperCase()} (${String(data.discovery_credential_mode || "configured").replace(/_/g, " ")}).`
                : (data && data.enabled === false
                    ? "This feature is disabled by PERSON_SEARCH_ENABLED."
                    : `Configure ${required.join(", ") || "PERSON_SEARCH_SERPAPI_KEY"} in backend/.env, then restart the API.`);
        }

        const limits = record(data && data.limits);
        applyServerLimits(limits, doc);
        const enrichment = record(data && data.enrichment_configured);
        const available = Object.keys(enrichment).filter(platform => enrichment[platform]);
        const enrichmentAllowed = Number(limits.enrichments) !== 0;
        if (toggle) {
            toggle.disabled = !isReady || !available.length || !enrichmentAllowed;
            if (toggle.disabled) toggle.checked = false;
        }
        if (help) {
            help.innerText = !isReady
                ? "Discovery must be configured before optional enrichment can run."
                : (!enrichmentAllowed
                    ? "Profile enrichment is disabled by the server limit; discovery remains available."
                    : available.length
                    ? `Optional collectors ready: ${available.map(platform => PLATFORM_LABELS[platform] || platform).join(", ")}. Additional calls remain off until enabled.`
                    : "Discovery is available, but no isolated enrichment collectors are configured. Results will remain discovery-only.");
        }
        updateEnrichmentControl(doc);
        setSearchEnabled(isReady, doc);
    }

    function applyReadinessFailure(message, doc = root.document) {
        const readiness = element("person-search-readiness", doc);
        const badge = element("person-search-readiness-badge", doc);
        const title = element("person-search-readiness-title", doc);
        const detail = element("person-search-readiness-detail", doc);
        if (readiness) readiness.className = "person-readiness-panel is-offline";
        if (badge) {
            badge.className = "person-readiness-badge is-offline";
            badge.innerText = "OFFLINE";
        }
        if (title) title.innerText = "Person-search status unavailable";
        if (detail) detail.innerText = message || "The backend could not be reached. Start the API and retry.";
        setSearchEnabled(false, doc);
    }

    async function loadStatus(options = {}) {
        const doc = options.document || root.document;
        const fetchImpl = options.fetchImpl || root.fetch;
        const apiBase = options.apiBase || API_BASE;
        if (!doc || typeof fetchImpl !== "function") return null;
        const refresh = element("person-search-status-refresh", doc);
        if (refresh) refresh.disabled = true;
        try {
            const response = await fetchImpl(`${apiBase}/api/v1/person-search/status`, {
                headers: { "Accept": "application/json" }
            });
            if (!response.ok) throw new Error(`Status endpoint returned HTTP ${response.status}.`);
            statusData = await response.json();
            statusLoaded = true;
            applyReadiness(statusData, doc);
            return statusData;
        } catch (error) {
            statusLoaded = false;
            statusData = null;
            applyReadinessFailure(error && error.message, doc);
            return null;
        } finally {
            if (refresh) refresh.disabled = false;
        }
    }

    function readFormValues(doc = root.document) {
        const value = id => {
            const target = element(id, doc);
            return target ? target.value : "";
        };
        const platforms = doc && typeof doc.querySelectorAll === "function"
            ? [...doc.querySelectorAll("[data-person-platform]:checked")].map(input => input.value)
            : [];
        const enrich = element("person-enrich-profiles", doc);
        return {
            full_name: value("person-full-name"),
            location: value("person-location"),
            organization: value("person-organization"),
            country_code: value("person-country-code"),
            platforms,
            max_profiles: value("person-max-profiles"),
            query_limit: value("person-query-limit"),
            provider_call_limit: value("person-provider-call-limit"),
            enrich_profiles: Boolean(enrich && enrich.checked && !enrich.disabled),
            max_enrichments: value("person-max-enrichments")
        };
    }

    function statusKind(status) {
        const value = String(status || "failed").toLowerCase();
        if (["completed"].includes(value)) return "success";
        if (["completed_with_warnings", "partial", "budget_exhausted", "rate_limited"].includes(value)) return "warning";
        if (["empty_dataset", "not_found"].includes(value)) return "empty";
        return "error";
    }

    function initials(value) {
        const words = String(value || "?").trim().split(/\s+/).filter(Boolean);
        return (words.slice(0, 2).map(word => word.charAt(0)).join("") || "?").toUpperCase();
    }

    function metadataChip(label, value) {
        if (value === null || value === undefined || value === "") return "";
        return `<span class="person-meta-chip"><strong>${escapeHTML(label)}</strong>${escapeHTML(value)}</span>`;
    }

    function profileMarkup(profile, index) {
        const item = record(profile);
        const platform = String(item.platform || "unknown").toLowerCase();
        const platformLabel = PLATFORM_LABELS[platform] || platform;
        const name = item.full_name || item.display_name || item.title || item.username || `${platformLabel} candidate`;
        const username = item.username ? `@${String(item.username).replace(/^@/, "")}` : "Username unavailable";
        const description = item.bio || item.snippet || item.title || "No public biography was returned.";
        const profileUrl = safeExternalUrl(item.profile_url);
        const photoUrl = safeImageSource(item.photo_url);
        const matchBasis = list(item.match_basis).slice(0, 6);
        const rank = Number(item.discovery_rank);
        const collectorBadge = item.collector_confirmed
            ? `<span class="person-evidence-badge is-collected" title="The public account was collected successfully; this does not prove same-person identity.">Collector confirmed</span>`
            : `<span class="person-evidence-badge is-discovery">Discovery candidate</span>`;
        const platformBadge = item.verified === true
            ? `<span class="person-evidence-badge is-platform-badge">Platform badge</span>`
            : "";
        const enrichment = item.enriched
            ? `Enriched · ${item.enrichment_status || "completed"}`
            : (item.enrichment_status && item.enrichment_status !== "not_requested"
                ? `Enrichment: ${item.enrichment_status}`
                : "Discovery data only");
        const avatar = `<div class="person-profile-avatar" aria-hidden="true">
            <span>${escapeHTML(initials(name))}</span>
            ${photoUrl ? `<img class="person-avatar-image" src="${escapeHTML(photoUrl)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : ""}
        </div>`;
        const action = profileUrl
            ? `<a class="person-profile-link" href="${escapeHTML(profileUrl)}" target="_blank" rel="noopener noreferrer">Open public profile <span aria-hidden="true">↗</span></a>`
            : `<span class="person-profile-link is-disabled">Profile URL unavailable</span>`;

        return `
            <article class="person-profile-card" data-person-profile-index="${index}">
                <div class="person-profile-card-top">
                    ${avatar}
                    <div class="person-profile-identity">
                        <div class="person-platform-line">
                            <span class="person-platform-badge">${escapeHTML(platformLabel)}</span>
                            <span class="person-rank">Result ${Number.isFinite(rank) ? rank : index + 1}</span>
                        </div>
                        <h4>${escapeHTML(name)}</h4>
                        <span class="person-username mono">${escapeHTML(username)}</span>
                    </div>
                </div>
                <div class="person-evidence-row">
                    <span class="person-evidence-badge is-unverified">Identity unverified</span>
                    ${collectorBadge}
                    ${platformBadge}
                </div>
                <p class="person-profile-description">${escapeHTML(description)}</p>
                <div class="person-profile-meta">
                    ${metadataChip("Location", item.location)}
                    ${metadataChip("Organization", item.organization)}
                    ${metadataChip("Source", item.collector_source || item.source)}
                </div>
                ${matchBasis.length ? `<div class="person-match-basis">${matchBasis.map(value => `<span>${escapeHTML(String(value).replace(/_/g, " "))}</span>`).join("")}</div>` : ""}
                <div class="person-profile-card-footer">
                    <span>${escapeHTML(enrichment)}</span>
                    ${action}
                </div>
            </article>`;
    }

    function usernameMarkup(item) {
        const value = record(item);
        const platform = String(value.platform || "unknown").toLowerCase();
        const url = safeExternalUrl(value.profile_url);
        const label = `@${String(value.username || "unknown").replace(/^@/, "")}`;
        const content = `
            <span class="person-username-platform">${escapeHTML(PLATFORM_LABELS[platform] || platform)}</span>
            <strong class="mono">${escapeHTML(label)}</strong>`;
        return url
            ? `<a class="person-username-card" href="${escapeHTML(url)}" target="_blank" rel="noopener noreferrer">${content}</a>`
            : `<div class="person-username-card">${content}</div>`;
    }

    function photoMarkup(item, index) {
        const value = record(item);
        const source = safeImageSource(value.url);
        if (!source) return "";
        const platform = String(value.platform || "unknown").toLowerCase();
        const profileUrl = safeExternalUrl(value.profile_url);
        const caption = `${PLATFORM_LABELS[platform] || platform}${value.username ? ` · @${String(value.username).replace(/^@/, "")}` : ""}`;
        const figure = `
            <figure class="person-photo-card">
                <div class="person-photo-frame">
                    <span aria-hidden="true">${escapeHTML(initials(value.username || platform))}</span>
                    <img class="person-avatar-image" src="${escapeHTML(source)}" alt="Public profile image candidate ${index + 1}" loading="lazy" referrerpolicy="no-referrer">
                </div>
                <figcaption>${escapeHTML(caption)}</figcaption>
            </figure>`;
        return profileUrl
            ? `<a class="person-photo-link" href="${escapeHTML(profileUrl)}" target="_blank" rel="noopener noreferrer">${figure}</a>`
            : figure;
    }

    function issueMessage(issue) {
        if (typeof issue === "string") return issue;
        const value = record(issue);
        return value.message || value.detail || value.code || "An unspecified provider issue occurred.";
    }

    function formatSearchedAt(value) {
        if (!value) return "Response time unavailable";
        const parsed = new Date(value);
        if (Number.isNaN(parsed.getTime())) return "Response time unavailable";
        return `Response generated ${parsed.toLocaleString()}`;
    }

    function buildResultsMarkup(data = {}) {
        const response = record(data);
        const profiles = list(response.profiles);
        const usernames = list(response.usernames);
        const photos = list(response.photos);
        const counts = record(response.counts);
        const query = record(response.query);
        const warnings = list(response.warnings).map(issueMessage).filter(Boolean);
        const errors = list(response.errors).map(issueMessage).filter(Boolean);
        const identityNotice = response.identity_notice || IDENTITY_NOTICE;
        const status = String(response.status || "failed").toLowerCase();
        const kind = statusKind(status);
        const profileCount = Number.isFinite(Number(counts.profiles)) ? Number(counts.profiles) : profiles.length;
        const usernameCount = Number.isFinite(Number(counts.usernames)) ? Number(counts.usernames) : usernames.length;
        const photoCount = Number.isFinite(Number(counts.photos)) ? Number(counts.photos) : photos.length;
        const enrichedCount = Number.isFinite(Number(counts.enriched_profiles)) ? Number(counts.enriched_profiles) : profiles.filter(item => item && item.enriched).length;
        const qualifiers = [query.location, query.organization, query.country_code].filter(Boolean);
        const budget = record(record(response.execution_metadata).provider_call_budget);
        const budgetText = Number.isFinite(Number(budget.used)) && Number.isFinite(Number(budget.maximum))
            ? `${Number(budget.used)}/${Number(budget.maximum)} provider calls used`
            : "Provider call usage unavailable";
        const requiredEnvironment = list(record(record(response.provider_metadata).discovery).required_environment);

        const issues = [
            ...warnings.map(message => `<li class="is-warning">${escapeHTML(message)}</li>`),
            ...errors.map(message => `<li class="is-error">${escapeHTML(message)}</li>`)
        ].join("");
        const setup = status === "not_configured"
            ? `<div class="person-setup-result">
                <strong>Person Search is not configured</strong>
                <p>Set ${escapeHTML(requiredEnvironment.join(", ") || "PERSON_SEARCH_SERPAPI_KEY")} in <span class="mono">backend/.env</span>, restart the API, and retry service status.</p>
            </div>`
            : "";
        const profileCards = profiles.length
            ? profiles.map(profileMarkup).join("")
            : `<div class="person-section-empty">No accepted public profile candidates were returned for this exact-name search.</div>`;
        const usernameCards = usernames.length
            ? usernames.map(usernameMarkup).join("")
            : `<div class="person-section-empty">No usernames were extracted from accepted profile URLs.</div>`;
        const photoCards = photos.map(photoMarkup).filter(Boolean);
        const photoContent = photoCards.length
            ? photoCards.join("")
            : `<div class="person-section-empty">No usable public profile pictures were returned.</div>`;

        return `
            <div class="person-results-header glass-card">
                <div class="person-results-title-row">
                    <div>
                        <span class="person-results-eyebrow">Exact-name discovery result</span>
                        <h3>${escapeHTML(query.full_name || "Person search")}</h3>
                        <p>${qualifiers.length ? `Narrowed by ${escapeHTML(qualifiers.join(" · "))}` : "Searched across the selected public platforms"}</p>
                    </div>
                    <span class="person-result-status is-${kind}">${escapeHTML(STATUS_LABELS[status] || status.replace(/_/g, " "))}</span>
                </div>
                <div class="person-identity-warning">
                    <span aria-hidden="true">!</span>
                    <p><strong>Identity warning:</strong> ${escapeHTML(identityNotice)}</p>
                </div>
                <div class="person-result-metrics">
                    <div><strong>${profileCount}</strong><span>Profiles</span></div>
                    <div><strong>${usernameCount}</strong><span>Usernames</span></div>
                    <div><strong>${photoCount}</strong><span>Photos</span></div>
                    <div><strong>${enrichedCount}</strong><span>Enriched</span></div>
                </div>
                <div class="person-response-meta">
                    <span>${escapeHTML(formatSearchedAt(response.searched_at))}</span>
                    <span>${escapeHTML(budgetText)}</span>
                </div>
            </div>
            ${setup}
            ${issues ? `<div class="person-result-issues"><strong>Provider notices</strong><ul>${issues}</ul></div>` : ""}
            <section class="person-result-section" aria-labelledby="person-profiles-heading">
                <div class="person-section-heading">
                    <div><span class="person-section-index">01</span><h3 id="person-profiles-heading">Profile candidates</h3></div>
                    <span>${profileCount} found</span>
                </div>
                <div class="person-profile-grid">${profileCards}</div>
            </section>
            <section class="person-result-section" aria-labelledby="person-usernames-heading">
                <div class="person-section-heading">
                    <div><span class="person-section-index">02</span><h3 id="person-usernames-heading">Discovered usernames</h3></div>
                    <span>${usernameCount} mapped</span>
                </div>
                <div class="person-username-grid">${usernameCards}</div>
            </section>
            <section class="person-result-section" aria-labelledby="person-photos-heading">
                <div class="person-section-heading">
                    <div><span class="person-section-index">03</span><h3 id="person-photos-heading">Profile pictures</h3></div>
                    <span>${photoCount} collected</span>
                </div>
                <p class="person-photo-disclaimer">Images are source-linked candidates only. Visual similarity is not identity confirmation.</p>
                <div class="person-photo-grid">${photoContent}</div>
            </section>`;
    }

    function renderResult(data, doc = root.document) {
        const empty = element("person-search-empty-state", doc);
        const alert = element("person-search-alert", doc);
        const results = element("person-search-results", doc);
        if (empty) setHidden(empty, true);
        if (alert) setHidden(alert, true);
        if (results) {
            results.innerHTML = buildResultsMarkup(data);
            setHidden(results, false);
        }
        currentResult = data;
    }

    function showProgress(fullName, doc = root.document) {
        const empty = element("person-search-empty-state", doc);
        const alert = element("person-search-alert", doc);
        const results = element("person-search-results", doc);
        if (empty) setHidden(empty, true);
        if (alert) setHidden(alert, true);
        if (results) {
            results.innerHTML = `
                <div class="person-search-progress glass-card">
                    <span class="person-progress-orbit" aria-hidden="true"></span>
                    <div><strong>Searching public profile indexes</strong><p>Resolving exact-name candidates for ${escapeHTML(fullName)}. This may take a moment.</p></div>
                </div>`;
            setHidden(results, false);
        }
    }

    function showError(message, doc = root.document) {
        const empty = element("person-search-empty-state", doc);
        const results = element("person-search-results", doc);
        const alert = element("person-search-alert", doc);
        if (empty) setHidden(empty, true);
        if (results) setHidden(results, true);
        if (alert) {
            alert.className = "person-search-alert is-error";
            alert.innerHTML = `<strong>Person search could not complete</strong><p>${escapeHTML(message)}</p>`;
            setHidden(alert, false);
        }
    }

    async function extractApiError(response) {
        let payload = null;
        try {
            payload = await response.json();
        } catch (_) {
            payload = null;
        }
        const detail = payload && payload.detail;
        let message = "The person-search endpoint rejected the request.";
        let retryAfter = null;
        if (typeof detail === "string") {
            message = detail;
        } else if (Array.isArray(detail)) {
            message = detail.map(item => item && (item.msg || item.message) || "Validation error").join("; ");
        } else if (detail && typeof detail === "object") {
            message = detail.message || detail.code || message;
            retryAfter = detail.retry_after;
        }
        if (!retryAfter && response.headers && typeof response.headers.get === "function") {
            retryAfter = response.headers.get("Retry-After");
        }
        if (retryAfter) message += ` Retry after ${retryAfter} second${String(retryAfter) === "1" ? "" : "s"}.`;
        return `HTTP ${response.status}: ${message}`;
    }

    function setBusy(value, doc = root.document) {
        busy = Boolean(value);
        const submit = element("person-search-submit", doc);
        if (submit) {
            submit.disabled = busy || !(statusData && statusData.enabled && statusData.configured);
            submit.innerText = busy ? "Searching Public Sources..." : "Search Public Profiles";
        }
    }

    async function submitSearch(options = {}) {
        const doc = options.document || root.document;
        const fetchImpl = options.fetchImpl || root.fetch;
        const apiBase = options.apiBase || API_BASE;
        if (!doc || typeof fetchImpl !== "function" || busy) return null;

        let payload;
        try {
            payload = buildPersonSearchRequest(readFormValues(doc), record(statusData && statusData.limits));
        } catch (error) {
            showError(error.message, doc);
            return null;
        }

        setBusy(true, doc);
        showProgress(payload.full_name, doc);
        const epoch = ++requestEpoch;
        const Controller = root.AbortController || (typeof AbortController !== "undefined" ? AbortController : null);
        const controller = Controller ? new Controller() : null;
        activeController = controller;
        try {
            const response = await fetchImpl(`${apiBase}/api/v1/person-search`, {
                method: "POST",
                headers: {
                    "Accept": "application/json",
                    "Content-Type": "application/json"
                },
                body: JSON.stringify(payload),
                ...(controller ? { signal: controller.signal } : {})
            });
            if (!response.ok) throw new Error(await extractApiError(response));
            const data = await response.json();
            if (epoch !== requestEpoch) return null;
            renderResult(data, doc);
            return data;
        } catch (error) {
            if (epoch !== requestEpoch || (error && error.name === "AbortError")) return null;
            showError(error && error.message ? error.message : "The backend could not be reached.", doc);
            return null;
        } finally {
            if (epoch === requestEpoch) {
                activeController = null;
                setBusy(false, doc);
            }
        }
    }

    function setAllPlatforms(checked, doc = root.document) {
        if (!doc || typeof doc.querySelectorAll !== "function") return;
        doc.querySelectorAll("[data-person-platform]").forEach(input => {
            input.checked = checked;
        });
    }

    function initialize(doc = root.document) {
        if (!doc) return false;
        const view = element("view-person-search", doc);
        if (!view) return false;
        if (!view.querySelector || !view.querySelector("#person-search-form")) {
            view.innerHTML = shellMarkup();
        }
        if (initialized && doc === root.document) return true;

        const form = element("person-search-form", doc);
        const refresh = element("person-search-status-refresh", doc);
        const selectAll = element("person-platform-select-all", doc);
        const clear = element("person-platform-clear", doc);
        const enrich = element("person-enrich-profiles", doc);
        const country = element("person-country-code", doc);
        if (form) form.addEventListener("submit", event => {
            event.preventDefault();
            submitSearch({ document: doc });
        });
        if (refresh) refresh.addEventListener("click", () => loadStatus({ document: doc }));
        if (selectAll) selectAll.addEventListener("click", () => setAllPlatforms(true, doc));
        if (clear) clear.addEventListener("click", () => setAllPlatforms(false, doc));
        if (enrich) enrich.addEventListener("change", () => updateEnrichmentControl(doc));
        if (country) country.addEventListener("input", () => {
            country.value = country.value.toUpperCase().replace(/[^A-Z]/g, "").slice(0, 2);
        });
        const results = element("person-search-results", doc);
        if (results) results.addEventListener("error", event => {
            if (event.target && event.target.classList && event.target.classList.contains("person-avatar-image")) {
                event.target.style.display = "none";
            }
        }, true);

        if (doc === root.document) initialized = true;
        return true;
    }

    function activate(options = {}) {
        const doc = options.document || root.document;
        initialize(doc);
        if (!statusLoaded || options.refresh) {
            return loadStatus({ ...options, document: doc });
        }
        applyReadiness(statusData, doc);
        return Promise.resolve(statusData);
    }

    function reset(doc = root.document) {
        requestEpoch += 1;
        if (activeController && typeof activeController.abort === "function") {
            activeController.abort();
        }
        activeController = null;
        const form = element("person-search-form", doc);
        const empty = element("person-search-empty-state", doc);
        const alert = element("person-search-alert", doc);
        const results = element("person-search-results", doc);
        if (form && typeof form.reset === "function") form.reset();
        setAllPlatforms(true, doc);
        if (element("person-max-profiles", doc)) element("person-max-profiles", doc).value = "20";
        if (element("person-max-enrichments", doc)) element("person-max-enrichments", doc).value = "4";
        updateEnrichmentControl(doc);
        if (empty) setHidden(empty, false);
        if (alert) setHidden(alert, true);
        if (results) {
            results.innerHTML = "";
            setHidden(results, true);
        }
        currentResult = null;
        busy = false;
        setSearchEnabled(Boolean(statusData && statusData.enabled && statusData.configured), doc);
    }

    if (root && typeof root.addEventListener === "function") {
        root.addEventListener("DOMContentLoaded", () => initialize(root.document));
    }

    return {
        ABSOLUTE_LIMITS,
        IDENTITY_NOTICE,
        PLATFORM_ORDER,
        activate,
        applyReadiness,
        buildPersonSearchRequest,
        buildResultsMarkup,
        escapeHTML,
        extractApiError,
        initialize,
        loadStatus,
        readFormValues,
        renderResult,
        reset,
        safeExternalUrl,
        safeImageSource,
        shellMarkup,
        statusKind,
        submitSearch
    };
});
