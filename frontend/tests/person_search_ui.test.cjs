const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const PersonSearchUI = require("../person_search.js");
const frontendRoot = path.resolve(__dirname, "..");

function fakeElement(overrides = {}) {
    const classes = new Set();
    return Object.assign({
        checked: false,
        className: "",
        disabled: false,
        hidden: false,
        innerHTML: "",
        innerText: "",
        max: "",
        style: {},
        value: "",
        addEventListener() {},
        classList: {
            add(value) { classes.add(value); },
            remove(value) { classes.delete(value); },
            contains(value) { return classes.has(value); },
            toggle(value, force) {
                if (force === true) classes.add(value);
                else if (force === false) classes.delete(value);
                else if (classes.has(value)) classes.delete(value);
                else classes.add(value);
            }
        }
    }, overrides);
}

function personDocument(overrides = {}) {
    const platforms = PersonSearchUI.PLATFORM_ORDER.map(value => fakeElement({ value, checked: true }));
    const elements = {
        "person-full-name": fakeElement({ value: "Ada Lovelace" }),
        "person-location": fakeElement({ value: "London" }),
        "person-organization": fakeElement({ value: "Analytical Engine Society" }),
        "person-country-code": fakeElement({ value: "gb" }),
        "person-max-profiles": fakeElement({ value: "20" }),
        "person-query-limit": fakeElement({ value: "" }),
        "person-provider-call-limit": fakeElement({ value: "" }),
        "person-enrich-profiles": fakeElement({ checked: false }),
        "person-max-enrichments": fakeElement({ value: "4", disabled: true }),
        "person-enrichment-limit-row": fakeElement(),
        "person-enrichment-help": fakeElement(),
        "person-search-submit": fakeElement({ disabled: true }),
        "person-search-status-refresh": fakeElement(),
        "person-search-readiness": fakeElement(),
        "person-search-readiness-badge": fakeElement(),
        "person-search-readiness-title": fakeElement(),
        "person-search-readiness-detail": fakeElement(),
        "person-search-empty-state": fakeElement(),
        "person-search-alert": fakeElement(),
        "person-search-results": fakeElement(),
        ...overrides
    };
    return {
        elements,
        platforms,
        getElementById(id) { return elements[id] || null; },
        querySelectorAll(selector) {
            if (selector === "[data-person-platform]") return platforms;
            if (selector === "[data-person-platform]:checked") return platforms.filter(item => item.checked);
            return [];
        }
    };
}

function readiness(overrides = {}) {
    return {
        enabled: true,
        configured: true,
        discovery_provider: "serpapi",
        discovery_credential_mode: "dedicated",
        required_environment: [],
        limits: {
            profiles: 20,
            queries: 5,
            provider_calls: 12,
            enrichments: 4
        },
        enrichment_configured: {
            github: true,
            youtube: false
        },
        ...overrides
    };
}

test("both dashboard entry points expose an isolated Person Search screen", () => {
    for (const filename of ["index.html", "mock_test.html"]) {
        const html = fs.readFileSync(path.join(frontendRoot, filename), "utf8");
        assert.match(html, /id="tab-btn-person-search"/);
        assert.match(html, /switchTab\('person-search'\)/);
        assert.match(html, /id="view-person-search"/);
        assert.match(html, /styles\.css\?v=20260728-person-ui/);
        assert.match(html, /person_search\.js\?v=20260728-person-ui/);
    }

    const shell = PersonSearchUI.shellMarkup();
    assert.match(shell, /id="person-search-form"/);
    assert.match(shell, /id="person-full-name"/);
    assert.match(shell, /id="person-location"/);
    assert.match(shell, /id="person-organization"/);
    assert.match(shell, /id="person-country-code"/);
    assert.match(shell, /data-person-platform checked/g);
    assert.match(shell, /id="person-enrich-profiles"/);
    assert.doesNotMatch(shell, /id="person-enrich-profiles"[^>]*checked/);
    assert.match(shell, /does not alter username investigations, case history, risk scoring, or reports/i);
});

test("person request builder normalizes values and keeps discovery isolated by default", () => {
    const payload = PersonSearchUI.buildPersonSearchRequest({
        full_name: "  Ada   Lovelace  ",
        location: "  London ",
        organization: " Analytical   Engine Society ",
        country_code: "gb",
        platforms: ["youtube", "github", "github", "linkedin"],
        max_profiles: "12",
        query_limit: "3",
        provider_call_limit: "7",
        enrich_profiles: false,
        max_enrichments: "4"
    });

    assert.deepEqual(payload, {
        full_name: "Ada Lovelace",
        location: "London",
        organization: "Analytical Engine Society",
        country_code: "GB",
        platforms: ["linkedin", "github", "youtube"],
        max_profiles: 12,
        query_limit: 3,
        provider_call_limit: 7,
        enrich_profiles: false
    });
    assert.equal(Object.hasOwn(payload, "max_enrichments"), false);
    assert.equal(Object.hasOwn(payload, "username"), false);
    assert.equal(Object.hasOwn(payload, "case_id"), false);

    const discoveryOnlyAtZeroEnrichment = PersonSearchUI.buildPersonSearchRequest({
        full_name: "Ada Lovelace",
        platforms: ["github"],
        max_profiles: 5,
        enrich_profiles: false,
        max_enrichments: 4
    }, { enrichments: 0 });
    assert.equal(discoveryOnlyAtZeroEnrichment.enrich_profiles, false);
});

test("person request builder includes explicitly authorized enrichment and enforces bounds", () => {
    const payload = PersonSearchUI.buildPersonSearchRequest({
        full_name: "Grace Hopper",
        platforms: ["github"],
        max_profiles: 10,
        enrich_profiles: true,
        max_enrichments: 2
    }, {
        profiles: 20,
        queries: 5,
        provider_calls: 12,
        enrichments: 4
    });

    assert.equal(payload.enrich_profiles, true);
    assert.equal(payload.max_enrichments, 2);
    assert.throws(() => PersonSearchUI.buildPersonSearchRequest({
        full_name: "Grace Hopper",
        platforms: [],
        max_profiles: 10
    }), /at least one platform/i);
    assert.throws(() => PersonSearchUI.buildPersonSearchRequest({
        full_name: "Grace Hopper",
        platforms: ["github"],
        max_profiles: 21
    }, { profiles: 20 }), /1 to 20/);
    assert.throws(() => PersonSearchUI.buildPersonSearchRequest({
        full_name: "Grace Hopper",
        country_code: "IND",
        platforms: ["github"],
        max_profiles: 10
    }), /exactly two letters/i);
});

test("readiness UI distinguishes configured discovery from dedicated-key setup", () => {
    const readyDoc = personDocument();
    PersonSearchUI.applyReadiness(readiness(), readyDoc);
    assert.equal(readyDoc.elements["person-search-readiness-badge"].innerText, "READY");
    assert.equal(readyDoc.elements["person-search-submit"].disabled, false);
    assert.equal(readyDoc.elements["person-enrich-profiles"].disabled, false);
    assert.match(readyDoc.elements["person-enrichment-help"].innerText, /GitHub/);

    const setupDoc = personDocument();
    PersonSearchUI.applyReadiness(readiness({
        configured: false,
        discovery_credential_mode: "not_configured",
        required_environment: ["PERSON_SEARCH_SERPAPI_KEY"],
        enrichment_configured: {}
    }), setupDoc);
    assert.equal(setupDoc.elements["person-search-readiness-badge"].innerText, "SETUP REQUIRED");
    assert.equal(setupDoc.elements["person-search-submit"].disabled, true);
    assert.match(setupDoc.elements["person-search-readiness-detail"].innerText, /PERSON_SEARCH_SERPAPI_KEY/);
    assert.doesNotMatch(setupDoc.elements["person-search-readiness-detail"].innerText, /Configure SERPAPI_KEY/);
});

test("result renderer labels every match as unverified and safely maps profiles, usernames, and photos", () => {
    const html = PersonSearchUI.buildResultsMarkup({
        success: true,
        status: "completed",
        query: { full_name: "Ada <script>alert(1)</script>", location: "London" },
        profiles: [{
            platform: "github",
            profile_url: "https://github.com/ada-example",
            username: "ada-example",
            full_name: "Ada Example",
            bio: "<img src=x onerror=alert(1)>",
            source: "serpapi",
            discovery_rank: 1,
            match_basis: ["exact_name", "profile_url"],
            identity_status: "unverified_candidate",
            collector_confirmed: true,
            verified: true,
            enriched: true,
            enrichment_status: "completed"
        }],
        usernames: [{
            platform: "github",
            username: "ada-example",
            profile_url: "https://github.com/ada-example"
        }],
        photos: [{
            platform: "github",
            username: "ada-example",
            profile_url: "https://github.com/ada-example",
            url: "https://avatars.githubusercontent.com/u/1"
        }, {
            platform: "github",
            username: "unsafe",
            profile_url: "javascript:alert(1)",
            url: "javascript:alert(1)"
        }],
        counts: { profiles: 1, usernames: 1, photos: 2, enriched_profiles: 1 },
        execution_metadata: { provider_call_budget: { used: 3, maximum: 8 } },
        warnings: [],
        errors: [],
        identity_notice: PersonSearchUI.IDENTITY_NOTICE,
        searched_at: "2026-07-28T12:00:00Z"
    });

    assert.match(html, /Identity unverified/i);
    assert.match(html, /Collector confirmed/i);
    assert.match(html, /Platform badge/i);
    assert.doesNotMatch(html, /Identity verified/i);
    assert.match(html, /Ada &lt;script&gt;alert\(1\)&lt;\/script&gt;/);
    assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt;/);
    assert.doesNotMatch(html, /<img src=x onerror/);
    assert.match(html, /https:\/\/github\.com\/ada-example/);
    assert.match(html, /https:\/\/avatars\.githubusercontent\.com\/u\/1/);
    assert.doesNotMatch(html, /javascript:/i);
    assert.match(html, /3\/8 provider calls used/);
});

test("person submit uses only the standalone endpoint and sends typed JSON", async () => {
    const doc = personDocument();
    const calls = [];
    const fetchImpl = async (url, options = {}) => {
        calls.push({ url: String(url), options });
        if (String(url).endsWith("/status")) {
            return { ok: true, status: 200, json: async () => readiness() };
        }
        return {
            ok: true,
            status: 200,
            json: async () => ({
                success: true,
                status: "empty_dataset",
                query: { full_name: "Ada Lovelace" },
                profiles: [],
                usernames: [],
                photos: [],
                counts: { profiles: 0, usernames: 0, photos: 0 },
                warnings: [],
                errors: [],
                searched_at: "2026-07-28T12:00:00Z"
            })
        };
    };

    await PersonSearchUI.loadStatus({ document: doc, fetchImpl, apiBase: "http://api.test" });
    await PersonSearchUI.submitSearch({ document: doc, fetchImpl, apiBase: "http://api.test" });

    assert.equal(calls.length, 2);
    assert.equal(calls[0].url, "http://api.test/api/v1/person-search/status");
    assert.equal(calls[1].url, "http://api.test/api/v1/person-search");
    assert.doesNotMatch(calls[1].url, /investigation\/username/);
    const payload = JSON.parse(calls[1].options.body);
    assert.equal(payload.full_name, "Ada Lovelace");
    assert.equal(typeof payload.max_profiles, "number");
    assert.equal(typeof payload.enrich_profiles, "boolean");
    assert.equal(payload.enrich_profiles, false);
    assert.equal(doc.elements["person-search-results"].hidden, false);
});

test("typed rate-limit and busy errors preserve retry guidance", async () => {
    const message = await PersonSearchUI.extractApiError({
        status: 429,
        headers: { get: name => name === "Retry-After" ? "9" : null },
        json: async () => ({
            detail: {
                code: "person_search_rate_limited",
                message: "Too many person-search requests from this client.",
                retry_after: 9
            }
        })
    });
    assert.match(message, /HTTP 429/);
    assert.match(message, /Too many person-search requests/);
    assert.match(message, /Retry after 9 seconds/);
});
