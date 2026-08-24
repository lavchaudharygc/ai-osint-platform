/**
 * Isolated exact-name public-profile search for the Beta-v2 SOC frontend.
 *
 * The module is deliberately UMD-shaped so its validation, rendering, and
 * lifecycle behavior can be exercised by the dependency-free CJS test suite.
 */
(function (root, factory) {
    const api = factory(root || {});
    if (typeof module === "object" && module.exports) {
        module.exports = api;
    }
    if (root) {
        root.PeopleSearchUI = api;
        root.openPeopleSearch = api.open;
        root.clearPeopleSearchState = api.clear;
        root.deactivatePeopleSearch = api.deactivate;
    }
})(typeof window !== "undefined" ? window : globalThis, function (root) {
    "use strict";

    const PEOPLE_API_BASE = typeof API_BASE !== "undefined"
        ? API_BASE
        : (root.API_BASE || (root.location?.hostname
            ? `${root.location.protocol}//${root.location.hostname}:8010`
            : "http://127.0.0.1:8010"));
    const STATUS_ENDPOINT = "/api/v1/person-search/status";
    const SEARCH_ENDPOINT = "/api/v1/person-search";
    const ABSOLUTE_PROFILE_LIMIT = 50;
    const INITIAL_GROUP_SIZE = 5;
    const IDENTITY_NOTICE = "These results are unverified public-data leads. A matching name, image, or username does not prove that accounts belong to the same person.";
    const PLATFORM_ORDER = [
        "instagram",
        "twitter",
        "facebook",
        "linkedin",
        "tiktok",
        "reddit",
        "github",
        "youtube",
        "telegram",
    ];
    const PLATFORM_LABELS = {
        instagram: "Instagram",
        twitter: "Twitter / X",
        facebook: "Facebook",
        linkedin: "LinkedIn",
        tiktok: "TikTok",
        reddit: "Reddit",
        github: "GitHub",
        youtube: "YouTube",
        telegram: "Telegram",
        other: "Other Platforms",
    };

    let statusData = null;
    let statusLoaded = false;
    let currentResult = null;
    let busy = false;
    let requestEpoch = 0;
    let statusEpoch = 0;
    let activeController = null;
    let statusController = null;
    const expandedGroups = new Set();
    const initializedDocuments = typeof WeakSet === "function" ? new WeakSet() : null;

    function escapeHTML(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function list(value) {
        return Array.isArray(value) ? value : [];
    }

    function record(value) {
        return value && typeof value === "object" && !Array.isArray(value) ? value : {};
    }

    function element(id, doc = root.document) {
        return doc && typeof doc.getElementById === "function" ? doc.getElementById(id) : null;
    }

    function scrollBehavior() {
        return root.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches
            ? "auto"
            : "smooth";
    }

    function normalizeHumanText(value, fieldName, required = false) {
        const raw = String(value ?? "");
        if (/\p{C}/u.test(raw)) {
            throw new Error(`${fieldName} cannot contain control or invisible characters.`);
        }
        const normalized = raw.replace(/\s+/gu, " ").trim();
        if (required && !normalized) throw new Error(`${fieldName} is required.`);
        return normalized;
    }

    function boundedInteger(value, minimum, maximum, fieldName) {
        const parsed = Number(value);
        if (!Number.isInteger(parsed) || parsed < minimum || parsed > maximum) {
            throw new Error(`${fieldName} must be a whole number from ${minimum} to ${maximum}.`);
        }
        return parsed;
    }

    function hostnameIsClearlyNonPublic(value) {
        const hostname = String(value || "").toLowerCase().replace(/^\[|\]$/g, "");
        if (!hostname
            || hostname === "localhost"
            || hostname.endsWith(".localhost")
            || hostname.endsWith(".local")
            || hostname.endsWith(".internal")
            || hostname.endsWith(".home.arpa")
            || hostname.endsWith(".test")
            || hostname.endsWith(".invalid")
            || hostname.endsWith(".example")) return true;
        if (hostname.includes(":")) {
            return hostname === "::"
                || hostname === "::1"
                || hostname.startsWith("::ffff:")
                || /^(?:fc|fd|fe[89ab]|ff)/i.test(hostname);
        }
        if (!/^\d+(?:\.\d+){3}$/.test(hostname)) return !hostname.includes(".");
        const octets = hostname.split(".").map(Number);
        if (octets.some(octet => !Number.isInteger(octet) || octet < 0 || octet > 255)) return true;
        const [a, b] = octets;
        return a === 0 || a === 10 || a === 127 || a >= 224
            || (a === 100 && b >= 64 && b <= 127)
            || (a === 169 && b === 254)
            || (a === 172 && b >= 16 && b <= 31)
            || (a === 192 && (b === 0 || b === 168))
            || (a === 198 && (b === 18 || b === 19 || b === 51))
            || (a === 203 && b === 0);
    }

    function safeAbsolutePublicHttpURL(value) {
        try {
            const parsed = new URL(String(value || ""));
            if (!["http:", "https:"].includes(parsed.protocol)) return "";
            if (parsed.username || parsed.password || hostnameIsClearlyNonPublic(parsed.hostname)) return "";
            return parsed.href;
        } catch (_error) {
            return "";
        }
    }

    function proxiedImageURL(value, apiBase = PEOPLE_API_BASE) {
        const source = safeAbsolutePublicHttpURL(value);
        if (!source) return "";
        try {
            const base = new URL(String(apiBase || ""));
            if (!["http:", "https:"].includes(base.protocol) || base.username || base.password) return "";
            const endpoint = new URL("/api/v1/investigation/proxy_image", base);
            endpoint.searchParams.set("url", source);
            return endpoint.href;
        } catch (_error) {
            return "";
        }
    }

    function platformKey(value) {
        const normalized = String(value || "other").trim().toLowerCase();
        if (["x", "twitter/x", "twitter / x"].includes(normalized)) return "twitter";
        const safe = normalized.replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
        return safe || "other";
    }

    function platformLabel(value) {
        const key = platformKey(value);
        if (PLATFORM_LABELS[key]) return PLATFORM_LABELS[key];
        return key.split("-").filter(Boolean).map(part => part.charAt(0).toUpperCase() + part.slice(1)).join(" ") || "Other Platform";
    }

    function buildPeopleSearchRequest(values = {}, limits = {}) {
        const fullName = normalizeHumanText(values.full_name, "Exact full name", true);
        if (fullName.length < 2 || fullName.length > 200) {
            throw new Error("Exact full name must contain 2 to 200 characters.");
        }

        const location = normalizeHumanText(values.location, "State / location");
        const organization = normalizeHumanText(values.organization, "Organization");
        const countryCode = normalizeHumanText(values.country_code, "Country").toUpperCase();
        if (location.length > 200) throw new Error("State / location must contain at most 200 characters.");
        if (organization.length > 200) throw new Error("Organization must contain at most 200 characters.");
        if (countryCode && !/^[A-Z]{2}$/.test(countryCode)) {
            throw new Error("Country must use a two-letter code, such as IN or GB.");
        }

        const requested = new Set(list(values.platforms).map(platformKey));
        const unsupported = [...requested].filter(platform => !PLATFORM_ORDER.includes(platform));
        if (unsupported.length) throw new Error(`Unsupported platform: ${unsupported.join(", ")}.`);
        const platforms = PLATFORM_ORDER.filter(platform => requested.has(platform));
        if (!platforms.length) throw new Error("Select at least one platform to search.");

        const serverMaximum = Number(limits.profiles ?? limits.max_profiles ?? ABSOLUTE_PROFILE_LIMIT);
        const maximum = Number.isFinite(serverMaximum)
            ? Math.max(1, Math.min(ABSOLUTE_PROFILE_LIMIT, Math.trunc(serverMaximum)))
            : ABSOLUTE_PROFILE_LIMIT;
        const maxProfiles = boundedInteger(values.max_profiles ?? 20, 1, maximum, "Candidate limit");

        const payload = {
            full_name: fullName,
            platforms,
            max_profiles: maxProfiles,
        };
        if (location) payload.location = location;
        if (organization) payload.organization = organization;
        if (countryCode) payload.country_code = countryCode;
        return payload;
    }

    function profileList(data) {
        const response = record(data);
        let profiles = list(response.profiles || response.profile_candidates || response.candidates);
        if (profiles.length) return profiles;
        const grouped = record(response.grouped_profiles || response.platforms);
        profiles = [];
        Object.entries(grouped).forEach(([platform, values]) => {
            list(values).forEach(value => profiles.push({ platform, ...record(value) }));
        });
        return profiles;
    }

    function groupProfiles(data) {
        const groups = {};
        profileList(data).forEach(profile => {
            const item = record(profile);
            const key = platformKey(item.platform || item.source || item.network);
            if (!groups[key]) groups[key] = [];
            groups[key].push(item);
        });
        return groups;
    }

    function profileName(profile) {
        const item = record(profile);
        return item.full_name || item.display_name || item.name || item.title || item.username || `${platformLabel(item.platform)} candidate`;
    }

    function profileUsername(profile) {
        const value = String(record(profile).username || record(profile).handle || "").replace(/^@/, "");
        return value ? `@${value}` : "Username unavailable";
    }

    function profileURL(profile) {
        const item = record(profile);
        return safeAbsolutePublicHttpURL(item.profile_url || item.url || item.link || item.external_url);
    }

    function profileImage(profile) {
        const item = record(profile);
        return item.image_url
            || item.photo_url
            || item.profile_image_url
            || item.profile_pic_url
            || item.avatar_url
            || item.thumbnail_url
            || item.image;
    }

    function initials(value) {
        const words = String(value || "?").trim().split(/\s+/).filter(Boolean);
        return (words.slice(0, 2).map(word => word.charAt(0)).join("") || "?").toUpperCase();
    }

    function metadataChip(label, value) {
        if (value === null || value === undefined || value === "") return "";
        return `<span class="people-profile-meta-chip"><strong>${escapeHTML(label)}</strong>${escapeHTML(value)}</span>`;
    }

    function profileCardMarkup(profile, apiBase = PEOPLE_API_BASE, profileIndex = null) {
        const item = record(profile);
        const name = profileName(item);
        const username = profileUsername(item);
        const platform = platformLabel(item.platform || item.source || item.network);
        const publicURL = profileURL(item);
        const imageURL = proxiedImageURL(profileImage(item), apiBase);
        const description = item.description || item.bio || item.snippet || item.summary || "No public description was returned for this candidate.";
        const matchBasis = list(item.match_basis || item.reasons).slice(0, 5);
        const avatar = imageURL
            ? `<img src="${escapeHTML(imageURL)}" alt="" loading="lazy" crossorigin="use-credentials" referrerpolicy="no-referrer" data-people-proxied-image>`
            : `<span>${escapeHTML(initials(name))}</span>`;
        const action = publicURL
            ? `<a class="people-profile-link" href="${escapeHTML(publicURL)}" target="_blank" rel="noopener noreferrer" aria-label="${escapeHTML(`Open ${platform} profile for ${name}`)}">Open public profile <span aria-hidden="true">↗</span></a>`
            : `<span class="people-profile-link is-disabled">Profile URL unavailable</span>`;
        const indexAttribute = Number.isInteger(profileIndex)
            ? ` data-people-profile-index="${profileIndex}"`
            : "";
        return `
            <article class="people-profile-card"${indexAttribute}>
                <div class="people-profile-card-top">
                    <div class="people-profile-avatar" aria-hidden="true">${avatar}</div>
                    <div class="people-profile-identity">
                        <span class="people-platform-badge">${escapeHTML(platform)}</span>
                        <h4>${escapeHTML(name)}</h4>
                        <span class="people-profile-username mono">${escapeHTML(username)}</span>
                    </div>
                </div>
                <div class="people-profile-evidence-row">
                    <span class="people-evidence-badge is-unverified">Identity unverified</span>
                    ${item.collector_confirmed ? `<span class="people-evidence-badge is-collected">Profile collected</span>` : `<span class="people-evidence-badge">Discovery lead</span>`}
                </div>
                <p class="people-profile-description">${escapeHTML(description)}</p>
                <div class="people-profile-meta">
                    ${metadataChip("Location", item.location)}
                    ${metadataChip("Organization", item.organization || item.company)}
                </div>
                ${matchBasis.length ? `<div class="people-match-basis">${matchBasis.map(value => `<span>${escapeHTML(String(value).replace(/_/g, " "))}</span>`).join("")}</div>` : ""}
                <div class="people-profile-card-footer">${action}</div>
            </article>`;
    }

    function collectImages(data) {
        const response = record(data);
        const candidates = [...list(response.photos || response.images)];
        profileList(response).forEach(profile => {
            const image = profileImage(profile);
            if (image) {
                candidates.push({
                    url: image,
                    platform: record(profile).platform,
                    username: record(profile).username,
                    full_name: profileName(profile),
                    profile_url: profileURL(profile),
                });
            }
        });
        const seen = new Set();
        return candidates.filter(candidate => {
            const item = typeof candidate === "string" ? { url: candidate } : record(candidate);
            const safe = safeAbsolutePublicHttpURL(item.url || item.image_url || item.photo_url || item.src);
            if (!safe || seen.has(safe)) return false;
            seen.add(safe);
            return true;
        }).slice(0, 30);
    }

    function imageCardMarkup(candidate, index, apiBase = PEOPLE_API_BASE) {
        const item = typeof candidate === "string" ? { url: candidate } : record(candidate);
        const source = item.url || item.image_url || item.photo_url || item.src;
        const imageURL = proxiedImageURL(source, apiBase);
        if (!imageURL) return "";
        const platform = platformLabel(item.platform || item.source || "other");
        const caption = item.full_name || item.name || item.username || `${platform} image candidate ${index + 1}`;
        const publicURL = safeAbsolutePublicHttpURL(item.profile_url || item.source_url || item.link);
        return `
            <figure class="people-image-card">
                <div class="people-image-frame">
                    <img src="${escapeHTML(imageURL)}" alt="Public profile image candidate ${index + 1}" loading="lazy" crossorigin="use-credentials" referrerpolicy="no-referrer" data-people-proxied-image>
                </div>
                <figcaption>
                    <span class="people-platform-badge">${escapeHTML(platform)}</span>
                    <strong>${escapeHTML(caption)}</strong>
                    ${publicURL ? `<a href="${escapeHTML(publicURL)}" target="_blank" rel="noopener noreferrer" aria-label="${escapeHTML(`View source for ${caption} on ${platform}`)}">View source ↗</a>` : ""}
                </figcaption>
            </figure>`;
    }

    function groupSort(left, right) {
        const leftIndex = PLATFORM_ORDER.indexOf(left);
        const rightIndex = PLATFORM_ORDER.indexOf(right);
        if (leftIndex !== -1 || rightIndex !== -1) {
            return (leftIndex === -1 ? PLATFORM_ORDER.length : leftIndex)
                - (rightIndex === -1 ? PLATFORM_ORDER.length : rightIndex);
        }
        return left.localeCompare(right);
    }

    function buildResultsMarkup(data = {}, expanded = expandedGroups, apiBase = PEOPLE_API_BASE) {
        const response = record(data);
        const groups = groupProfiles(response);
        const groupKeys = Object.keys(groups).sort(groupSort);
        const images = collectImages(response);
        const expandedSet = expanded instanceof Set ? expanded : new Set(list(expanded));
        const query = record(response.query);
        const counts = record(response.counts);
        const profilesCount = Number.isFinite(Number(counts.profiles)) ? Number(counts.profiles) : profileList(response).length;
        const imageCount = Number.isFinite(Number(counts.photos)) ? Number(counts.photos) : images.length;
        const statusKey = String(response.status || "completed").trim().toLowerCase();
        const status = statusKey.replace(/_/g, " ").toUpperCase();
        const statusTone = statusKey === "completed"
            ? "is-success"
            : statusKey === "partial"
                ? "is-warning"
                : statusKey === "no_results"
                    ? "is-neutral"
                    : "is-error";
        const searchedName = query.full_name || response.full_name || response.target || "People search";
        const warnings = [...list(response.warnings), ...list(response.errors)]
            .map(value => typeof value === "string" ? value : (record(value).message || record(value).detail || record(value).code))
            .filter(Boolean);

        const imageCards = images.map((item, index) => imageCardMarkup(item, index, apiBase)).filter(Boolean).join("");
        const profileGroups = groupKeys.map(key => {
            const profiles = groups[key];
            const expandedNow = expandedSet.has(key);
            const visible = expandedNow ? profiles : profiles.slice(0, INITIAL_GROUP_SIZE);
            const remaining = Math.max(0, profiles.length - INITIAL_GROUP_SIZE);
            const toggle = profiles.length > INITIAL_GROUP_SIZE
                ? `<button type="button" class="people-show-more" data-people-toggle-group="${escapeHTML(key)}" aria-controls="people-profile-grid-${escapeHTML(key)}" aria-expanded="${expandedNow}">${expandedNow ? "Show less" : `Show more profiles (${remaining} more)`}</button>`
                : "";
            return `
                <section class="soc-card people-profile-group" data-people-profile-group="${escapeHTML(key)}">
                    <div class="people-result-section-heading">
                        <div>
                            <span class="people-result-section-index mono">${String(groupKeys.indexOf(key) + 2).padStart(2, "0")}</span>
                            <h3>${escapeHTML(platformLabel(key))} Profiles</h3>
                        </div>
                        <span class="mono">${profiles.length} CANDIDATE${profiles.length === 1 ? "" : "S"}</span>
                    </div>
                    <div class="people-profile-grid" id="people-profile-grid-${escapeHTML(key)}">${visible.map((profile, index) => profileCardMarkup(profile, apiBase, index)).join("")}</div>
                    ${toggle}
                </section>`;
        }).join("");

        return `
            <section class="soc-card people-results-summary">
                <div class="people-results-title-row">
                    <div>
                        <span class="email-module-kicker mono">PUBLIC PROFILE SEARCH RESULT</span>
                        <h2>${escapeHTML(searchedName)}</h2>
                        <p>${profilesCount} profile candidate${profilesCount === 1 ? "" : "s"} and ${imageCount} image candidate${imageCount === 1 ? "" : "s"} returned.</p>
                    </div>
                    <span class="people-result-status ${statusTone} mono">${escapeHTML(status)}</span>
                </div>
                <div class="people-identity-warning">
                    <span aria-hidden="true">!</span>
                    <p><strong>Unverified lead notice:</strong> ${escapeHTML(response.identity_notice || IDENTITY_NOTICE)}</p>
                </div>
                ${warnings.length ? `<div class="people-result-warnings"><strong>Provider notices</strong><ul>${warnings.map(message => `<li>${escapeHTML(message)}</li>`).join("")}</ul></div>` : ""}
            </section>

            <section class="soc-card people-images-section">
                <div class="people-result-section-heading">
                    <div><span class="people-result-section-index mono">01</span><h3>Images</h3></div>
                    <span class="mono">${images.length} COLLECTED</span>
                </div>
                <p class="people-section-disclaimer">Images are source-linked candidates only. Visual similarity is not identity confirmation.</p>
                <div class="people-image-grid">${imageCards || `<div class="people-empty-state">No safe public profile images were returned.</div>`}</div>
            </section>

            ${profileGroups || `<section class="soc-card people-empty-state">No accepted public profile candidates were returned for this exact-name search.</section>`}`;
    }

    function readFormValues(doc = root.document) {
        const value = id => String(element(id, doc)?.value || "");
        const platformInputs = doc && typeof doc.querySelectorAll === "function"
            ? [...doc.querySelectorAll("[data-people-platform]:checked")]
            : [];
        return {
            full_name: value("people-full-name"),
            location: value("people-location"),
            organization: value("people-organization"),
            country_code: value("people-country-code"),
            max_profiles: value("people-candidate-limit"),
            platforms: platformInputs.map(input => input.value),
        };
    }

    function showError(message, doc = root.document) {
        const target = element("people-search-error", doc);
        if (!target) return;
        target.textContent = String(message || "");
        target.style.display = message ? "block" : "none";
    }

    function setSearchEnabled(enabled, doc = root.document) {
        const submit = element("people-search-submit", doc);
        if (submit) submit.disabled = !enabled || busy;
    }

    function setReadiness(kind, title, detail, doc = root.document) {
        const panel = element("people-search-readiness", doc);
        const titleNode = element("people-search-readiness-title", doc);
        const detailNode = element("people-search-readiness-detail", doc);
        if (panel) panel.className = `people-search-readiness is-${kind}`;
        if (titleNode) titleNode.textContent = title;
        if (detailNode) detailNode.textContent = detail;
    }

    function applyReadiness(data = {}, doc = root.document) {
        statusData = record(data);
        statusLoaded = true;
        const enabled = statusData.enabled !== false;
        const configured = statusData.configured !== false;
        const ready = enabled && configured;
        const limits = record(statusData.limits);
        const maximum = Number(limits.profiles ?? limits.max_profiles);
        const limitInput = element("people-candidate-limit", doc);
        if (limitInput && Number.isFinite(maximum)) {
            limitInput.max = String(Math.max(1, Math.min(ABSOLUTE_PROFILE_LIMIT, Math.trunc(maximum))));
            if (Number(limitInput.value) > Number(limitInput.max)) limitInput.value = limitInput.max;
        }
        if (ready) {
            setReadiness("ready", "People Search ready", "The isolated public-profile discovery service is available.", doc);
        } else if (!enabled) {
            setReadiness("unavailable", "People Search disabled", "The backend has disabled this workflow.", doc);
        } else {
            setReadiness("unavailable", "People Search setup required", "The dedicated search provider is not configured on the backend.", doc);
        }
        setSearchEnabled(ready, doc);
        return ready;
    }

    function resolveFetch(options = {}) {
        if (typeof options.fetchImpl === "function") return options.fetchImpl;
        if (root.SocAuth && typeof root.SocAuth.fetch === "function") return root.SocAuth.fetch.bind(root.SocAuth);
        return typeof root.fetch === "function" ? root.fetch.bind(root) : null;
    }

    function makeController() {
        const Controller = root.AbortController || (typeof AbortController !== "undefined" ? AbortController : null);
        return Controller ? new Controller() : null;
    }

    async function extractApiError(response) {
        let detail = null;
        try {
            const payload = await response.json();
            detail = payload?.detail;
        } catch (_error) {
            detail = null;
        }
        if (typeof detail === "string") return `HTTP ${response.status}: ${detail}`;
        if (Array.isArray(detail)) {
            return `HTTP ${response.status}: ${detail.map(item => item?.msg || item?.message || "Validation error").join("; ")}`;
        }
        if (detail && typeof detail === "object") {
            const message = detail.message || detail.code || "People Search request failed.";
            return `HTTP ${response.status}: ${message}${detail.retry_after ? ` Retry after ${detail.retry_after} seconds.` : ""}`;
        }
        return `HTTP ${response.status}: People Search request failed.`;
    }

    async function loadStatus(options = {}) {
        const doc = options.document || root.document;
        const fetchImpl = resolveFetch(options);
        const apiBase = options.apiBase || PEOPLE_API_BASE;
        if (!doc || !fetchImpl) return null;
        const serial = ++statusEpoch;
        if (statusController) statusController.abort("superseded");
        const controller = makeController();
        statusController = controller;
        const refresh = element("people-search-status-refresh", doc);
        if (refresh) refresh.disabled = true;
        setSearchEnabled(false, doc);
        setReadiness("checking", "Checking search service", "Reading provider readiness and safe server limits...", doc);
        try {
            const response = await fetchImpl(`${apiBase}${STATUS_ENDPOINT}`, {
                method: "GET",
                headers: { "Accept": "application/json" },
                ...(controller ? { signal: controller.signal } : {}),
            });
            if (serial !== statusEpoch || controller?.signal.aborted) return null;
            if (!response.ok) throw new Error(await extractApiError(response));
            const data = await response.json();
            if (serial !== statusEpoch || controller?.signal.aborted) return null;
            applyReadiness(data, doc);
            return data;
        } catch (error) {
            if (serial !== statusEpoch || controller?.signal.aborted || error?.name === "AbortError") return null;
            statusLoaded = false;
            statusData = null;
            setReadiness("unavailable", "People Search unavailable", error?.message || "The backend could not be reached.", doc);
            setSearchEnabled(false, doc);
            return null;
        } finally {
            if (serial === statusEpoch) {
                statusController = null;
                if (refresh) refresh.disabled = false;
            }
        }
    }

    function setBusy(value, doc = root.document) {
        busy = Boolean(value);
        const submit = element("people-search-submit", doc);
        const cancel = element("people-search-cancel", doc);
        const loading = element("people-search-loading", doc);
        const state = element("people-search-form-state", doc);
        if (submit) {
            submit.disabled = busy || !(statusData && statusData.enabled !== false && statusData.configured !== false);
            submit.textContent = busy ? "Searching Public Sources..." : "Search Public Profiles";
        }
        if (cancel) cancel.style.display = busy ? "inline-flex" : "none";
        if (loading) loading.style.display = busy ? "flex" : "none";
        if (state) state.textContent = busy ? "SEARCH IN PROGRESS" : "READY";
    }

    function announceResult(message, doc = root.document) {
        const target = element("people-search-result-announcement", doc);
        if (target) target.textContent = String(message || "");
    }

    function renderResult(data, doc = root.document, apiBase = PEOPLE_API_BASE, shouldAnnounce = true) {
        const target = element("people-search-results", doc);
        if (!target) return;
        currentResult = record(data);
        target.innerHTML = buildResultsMarkup(currentResult, expandedGroups, apiBase);
        target.style.display = "block";
        if (shouldAnnounce) {
            const resultCounts = record(currentResult.counts);
            const profileCount = Number.isFinite(Number(resultCounts.profiles))
                ? Number(resultCounts.profiles)
                : profileList(currentResult).length;
            announceResult(`People Search returned ${profileCount} profile candidate${profileCount === 1 ? "" : "s"}.`, doc);
        }
        if (typeof target.querySelectorAll === "function") {
            target.querySelectorAll("img[data-people-proxied-image]").forEach(image => {
                image.addEventListener("error", () => {
                    image.style.display = "none";
                    image.parentElement?.classList?.add("is-unavailable");
                }, { once: true });
            });
        }
    }

    function toggleGroup(group, doc = root.document, apiBase = PEOPLE_API_BASE) {
        const key = platformKey(group);
        const wasExpanded = expandedGroups.has(key);
        if (wasExpanded) expandedGroups.delete(key);
        else expandedGroups.add(key);
        if (currentResult) renderResult(currentResult, doc, apiBase, false);
        const resultsRoot = element("people-search-results", doc);
        const groupRoot = resultsRoot
            ?.querySelector?.(`[data-people-profile-group="${key}"]`);
        const replacementToggle = groupRoot
            ?.querySelector?.(`[data-people-toggle-group="${key}"]`);
        const focusTarget = wasExpanded
            ? replacementToggle
            : groupRoot?.querySelector?.(
                `[data-people-profile-index="${INITIAL_GROUP_SIZE}"] .people-profile-link:not(.is-disabled)`,
            ) || replacementToggle;
        focusTarget?.focus?.();
        const groupCount = list(groupProfiles(currentResult)[key]).length;
        const additionalCount = Math.max(0, groupCount - INITIAL_GROUP_SIZE);
        announceResult(
            wasExpanded
                ? `${platformLabel(key)} collapsed to the first ${Math.min(INITIAL_GROUP_SIZE, groupCount)} profiles.`
                : `${additionalCount} additional ${platformLabel(key)} profile${additionalCount === 1 ? "" : "s"} shown.`,
            doc,
        );
        return !wasExpanded;
    }

    async function submitSearch(options = {}) {
        const doc = options.document || root.document;
        const fetchImpl = resolveFetch(options);
        const apiBase = options.apiBase || PEOPLE_API_BASE;
        if (!doc || !fetchImpl || busy) return null;

        let payload;
        try {
            payload = buildPeopleSearchRequest(readFormValues(doc), record(statusData).limits || {});
        } catch (error) {
            showError(error.message, doc);
            return null;
        }

        showError("", doc);
        const serial = ++requestEpoch;
        if (activeController) activeController.abort("superseded");
        const controller = makeController();
        activeController = controller;
        setBusy(true, doc);
        try {
            const response = await fetchImpl(`${apiBase}${SEARCH_ENDPOINT}`, {
                method: "POST",
                headers: { "Accept": "application/json", "Content-Type": "application/json" },
                body: JSON.stringify(payload),
                ...(controller ? { signal: controller.signal } : {}),
            });
            if (serial !== requestEpoch || controller?.signal.aborted) return null;
            if (!response.ok) throw new Error(await extractApiError(response));
            const data = await response.json();
            if (serial !== requestEpoch || controller?.signal.aborted) return null;
            expandedGroups.clear();
            renderResult(data, doc, apiBase);
            element("people-search-results", doc)?.scrollIntoView?.({ behavior: scrollBehavior(), block: "start" });
            return data;
        } catch (error) {
            if (serial !== requestEpoch || controller?.signal.aborted || error?.name === "AbortError") return null;
            showError(error?.message || "People Search could not reach the backend.", doc);
            return null;
        } finally {
            if (serial === requestEpoch) {
                activeController = null;
                setBusy(false, doc);
            }
        }
    }

    function setAllPlatforms(checked, doc = root.document) {
        if (!doc || typeof doc.querySelectorAll !== "function") return;
        doc.querySelectorAll("[data-people-platform]").forEach(input => {
            input.checked = Boolean(checked);
        });
    }

    function cancelActiveSearch(doc = root.document, reason = "analyst_cancelled") {
        requestEpoch += 1;
        if (activeController) activeController.abort(reason);
        activeController = null;
        setBusy(false, doc);
    }

    function deactivate(doc = root.document) {
        cancelActiveSearch(doc, "view_changed");
    }

    function clear(doc = root.document) {
        cancelActiveSearch(doc, "session_cleared");
        statusEpoch += 1;
        if (statusController) statusController.abort("session_cleared");
        statusController = null;
        statusData = null;
        statusLoaded = false;
        currentResult = null;
        expandedGroups.clear();
        const form = element("people-search-form", doc);
        if (form?.reset) form.reset();
        setAllPlatforms(true, doc);
        const limit = element("people-candidate-limit", doc);
        if (limit) limit.value = "20";
        const results = element("people-search-results", doc);
        if (results) {
            results.innerHTML = "";
            results.style.display = "none";
        }
        announceResult("", doc);
        const view = element("people-search-view", doc);
        if (view) view.style.display = "none";
        element("nav-people-search", doc)?.classList?.remove("is-active");
        showError("", doc);
        setSearchEnabled(false, doc);
        setReadiness("checking", "Checking search service", "Open People Search to refresh provider readiness.", doc);
    }

    function activateFallbackView(doc = root.document) {
        ["hero-search-view", "email-investigation-view", "phone-investigation-view", "results-workspace"]
            .forEach(id => {
                const node = element(id, doc);
                if (node) node.style.display = "none";
            });
        const view = element("people-search-view", doc);
        if (view) view.style.display = "block";
        ["nav-username-investigation", "nav-email-investigation", "nav-phone-investigation"]
            .forEach(id => element(id, doc)?.classList?.remove("is-active"));
        element("nav-people-search", doc)?.classList?.add("is-active");
        const exportButton = element("nav-lea-export", doc);
        if (exportButton) exportButton.style.display = "none";
    }

    function open(options = {}) {
        const doc = options.document || root.document;
        initialize(doc);
        if (typeof root.activateDashboardView === "function" && doc === root.document) {
            root.activateDashboardView("people");
        } else {
            activateFallbackView(doc);
        }
        showError("", doc);
        root.scrollTo?.({ top: 0, behavior: scrollBehavior() });
        root.setTimeout?.(() => element("people-full-name", doc)?.focus?.(), 100);
        if (options.loadStatus === false) return Promise.resolve(statusData);
        if (!statusLoaded || options.refresh) return loadStatus({ ...options, document: doc });
        applyReadiness(statusData, doc);
        return Promise.resolve(statusData);
    }

    function initialize(doc = root.document) {
        if (!doc) return false;
        if (initializedDocuments?.has(doc)) return true;
        const form = element("people-search-form", doc);
        if (!form) return false;
        form.addEventListener?.("submit", event => {
            event.preventDefault();
            submitSearch({ document: doc });
        });
        element("people-search-status-refresh", doc)?.addEventListener?.("click", () => loadStatus({ document: doc }));
        element("people-platform-select-all", doc)?.addEventListener?.("click", () => setAllPlatforms(true, doc));
        element("people-platform-clear", doc)?.addEventListener?.("click", () => setAllPlatforms(false, doc));
        element("people-search-cancel", doc)?.addEventListener?.("click", () => cancelActiveSearch(doc));
        const country = element("people-country-code", doc);
        country?.addEventListener?.("input", () => {
            country.value = String(country.value || "").toUpperCase().replace(/[^A-Z]/g, "").slice(0, 2);
        });
        element("people-search-results", doc)?.addEventListener?.("click", event => {
            const button = event.target?.closest?.("[data-people-toggle-group]");
            if (button) toggleGroup(button.getAttribute("data-people-toggle-group"), doc);
        });
        initializedDocuments?.add(doc);
        return true;
    }

    function stateSnapshot() {
        return {
            busy,
            requestEpoch,
            statusEpoch,
            statusLoaded,
            hasActiveRequest: Boolean(activeController),
            hasStatusRequest: Boolean(statusController),
            hasResult: Boolean(currentResult),
            expandedGroups: [...expandedGroups],
        };
    }

    if (root && typeof root.addEventListener === "function") {
        root.addEventListener("DOMContentLoaded", () => initialize(root.document));
        root.addEventListener("soc:unauthenticated", () => clear(root.document));
    }

    return {
        ABSOLUTE_PROFILE_LIMIT,
        IDENTITY_NOTICE,
        INITIAL_GROUP_SIZE,
        PLATFORM_ORDER,
        applyReadiness,
        buildPeopleSearchRequest,
        buildResultsMarkup,
        clear,
        collectImages,
        deactivate,
        escapeHTML,
        extractApiError,
        groupProfiles,
        initialize,
        loadStatus,
        open,
        platformKey,
        profileCardMarkup,
        proxiedImageURL,
        readFormValues,
        renderResult,
        safeAbsolutePublicHttpURL,
        setAllPlatforms,
        stateSnapshot,
        submitSearch,
        toggleGroup,
    };
});
