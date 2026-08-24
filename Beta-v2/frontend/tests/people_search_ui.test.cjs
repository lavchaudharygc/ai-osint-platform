"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const frontendRoot = path.join(__dirname, "..");
const PeopleSearchUI = require(path.join(frontendRoot, "js", "person_search.js"));

function fakeElement(overrides = {}) {
    const classes = new Set();
    const handlers = new Map();
    return {
        value: "",
        checked: false,
        disabled: false,
        innerHTML: "",
        textContent: "",
        style: {},
        className: "",
        classList: {
            add(value) { classes.add(value); },
            remove(value) { classes.delete(value); },
            toggle(value, force) {
                if (force === undefined ? !classes.has(value) : force) classes.add(value);
                else classes.delete(value);
            },
            contains(value) { return classes.has(value); },
        },
        addEventListener(type, handler) { handlers.set(type, handler); },
        querySelectorAll() { return []; },
        scrollIntoView() {},
        focus() {},
        reset() {},
        _handlers: handlers,
        ...overrides,
    };
}

function createDocument() {
    const ids = [
        "people-search-view",
        "hero-search-view",
        "email-investigation-view",
        "phone-investigation-view",
        "results-workspace",
        "nav-username-investigation",
        "nav-people-search",
        "nav-email-investigation",
        "nav-phone-investigation",
        "nav-lea-export",
        "people-search-form",
        "people-full-name",
        "people-location",
        "people-organization",
        "people-country-code",
        "people-candidate-limit",
        "people-search-readiness",
        "people-search-readiness-title",
        "people-search-readiness-detail",
        "people-search-status-refresh",
        "people-platform-select-all",
        "people-platform-clear",
        "people-search-submit",
        "people-search-cancel",
        "people-search-loading",
        "people-search-form-state",
        "people-search-error",
        "people-search-result-announcement",
        "people-search-results",
    ];
    const elements = Object.fromEntries(ids.map(id => [id, fakeElement()]));
    const platforms = PeopleSearchUI.PLATFORM_ORDER.map(value => fakeElement({ value, checked: true }));
    const document = {
        getElementById(id) { return elements[id] || null; },
        querySelectorAll(selector) {
            if (selector === "[data-people-platform]") return platforms;
            if (selector === "[data-people-platform]:checked") return platforms.filter(input => input.checked);
            return [];
        },
    };
    return { document, elements, platforms };
}

function profile(platform, index, overrides = {}) {
    return {
        platform,
        full_name: `${platform} Candidate ${index}`,
        username: `${platform}_${index}`,
        profile_url: `https://${platform}.example.org/profile/${index}`,
        image_url: `https://images.example.org/${platform}/${index}.jpg`,
        description: `Public ${platform} candidate ${index}`,
        ...overrides,
    };
}

test("People Search DOM contract is present and isolated", () => {
    const html = fs.readFileSync(path.join(frontendRoot, "index.html"), "utf8");
    const css = fs.readFileSync(path.join(frontendRoot, "css", "soc_theme.css"), "utf8");
    assert.match(html, /id="nav-people-search"/);
    assert.match(html, /id="people-search-view"/);
    assert.match(html, /id="people-search-form"/);
    assert.match(html, /id="people-full-name"/);
    assert.match(html, /data-people-platform/);
    assert.match(html, /id="people-candidate-limit"/);
    assert.match(html, /src="js\/person_search\.js"/);
    assert.doesNotMatch(html, /Idcrawl/i);
    assert.match(html, /id="people-search-result-announcement"[^>]*aria-live="polite"/);
    assert.doesNotMatch(html, /id="people-search-results"[^>]*aria-live=/);
    assert.match(css, /\.people-sr-only\s*\{[^}]*clip:\s*rect\(0, 0, 0, 0\);/s);
    assert.match(css, /\.people-profile-grid\s*\{[^}]*grid-template-columns:\s*1fr;/s);
});

test("People Search navigation is visible only to investigators", () => {
    const appSource = fs.readFileSync(path.join(frontendRoot, "js", "app.js"), "utf8");
    const events = {};
    const roles = new Set(["breach_pii_viewer"]);
    const nodes = {
        "nav-username-investigation": fakeElement(),
        "nav-people-search": fakeElement(),
    };
    const sandbox = {
        console,
        URL,
        AbortController,
        location: { protocol: "http:", hostname: "127.0.0.1" },
        document: { getElementById(id) { return nodes[id] || null; } },
        SocAuth: {
            hasRole(role) { return roles.has(role); },
            async fetch() { return { ok: true, async json() { return {}; } }; },
        },
        addEventListener(type, handler) { events[type] = handler; },
        scrollTo() {},
        setInterval() { return 1; },
        clearInterval() {},
        setTimeout() { return 1; },
        clearTimeout() {},
        alert() {},
    };
    sandbox.window = sandbox;
    vm.runInNewContext(appSource, sandbox, { filename: "app.js" });

    events["soc:authenticated"]();
    assert.equal(nodes["nav-people-search"].style.display, "none");

    roles.add("investigator");
    events["soc:authenticated"]();
    assert.equal(nodes["nav-people-search"].style.display, "inline-flex");
});

test("request builder normalizes exact-name filters and enforces server limits", () => {
    const payload = PeopleSearchUI.buildPeopleSearchRequest({
        full_name: "  Ada   Lovelace  ",
        location: "  Uttar Pradesh ",
        organization: " Analytical Engine Society ",
        country_code: "in",
        platforms: ["twitter", "instagram", "github"],
        max_profiles: "12",
    }, { profiles: 12 });

    assert.deepEqual(payload, {
        full_name: "Ada Lovelace",
        platforms: ["instagram", "twitter", "github"],
        max_profiles: 12,
        location: "Uttar Pradesh",
        organization: "Analytical Engine Society",
        country_code: "IN",
    });
    assert.deepEqual(Object.keys(payload).sort(), [
        "country_code",
        "full_name",
        "location",
        "max_profiles",
        "organization",
        "platforms",
    ]);
    assert.equal(Object.hasOwn(payload, "enrich_profiles"), false);
    assert.throws(() => PeopleSearchUI.buildPeopleSearchRequest({
        full_name: "Ada Lovelace",
        platforms: ["instagram"],
        max_profiles: 13,
    }, { profiles: 12 }), /1 to 12/);
    assert.throws(() => PeopleSearchUI.buildPeopleSearchRequest({
        full_name: "Ada Lovelace",
        platforms: [],
        max_profiles: 5,
    }), /Select at least one platform/);
    assert.throws(() => PeopleSearchUI.buildPeopleSearchRequest({
        full_name: "Ada\u202eLovelace",
        platforms: ["instagram"],
        max_profiles: 5,
    }), /invisible characters/);
    assert.throws(() => PeopleSearchUI.buildPeopleSearchRequest({
        full_name: "Ada\u00adLovelace",
        platforms: ["instagram"],
        max_profiles: 5,
    }), /invisible characters/);
});

test("renderer escapes hostile text and rejects unsafe links and images", () => {
    const data = {
        status: "completed",
        query: { full_name: '<img src=x onerror="owned()">' },
        profiles: [
            profile("instagram", 1, {
                full_name: "<script>owned()</script>",
                profile_url: "javascript:owned()",
                image_url: "http://127.0.0.1/private.jpg",
                description: '<svg onload="owned()">',
            }),
            profile("twitter", 2),
        ],
        photos: [
            { url: "http://10.0.0.8/private.png", full_name: "private" },
            { url: "https://cdn.example.org/public.png", full_name: "Public & Candidate" },
        ],
        identity_notice: "Candidate <b>only</b>",
    };
    const html = PeopleSearchUI.buildResultsMarkup(data, new Set(), "http://127.0.0.1:8010");

    assert.match(html, /&lt;img src=x onerror=&quot;owned\(\)&quot;&gt;/);
    assert.match(html, /&lt;script&gt;owned\(\)&lt;\/script&gt;/);
    assert.match(html, /Candidate &lt;b&gt;only&lt;\/b&gt;/);
    assert.doesNotMatch(html, /<script|javascript:|127\.0\.0\.1\/private|10\.0\.0\.8\/private/i);
    assert.match(html, /\/api\/v1\/investigation\/proxy_image\?url=/);
    assert.match(html, /https%3A%2F%2Fcdn\.example\.org%2Fpublic\.png/);
    assert.match(html, /crossorigin="use-credentials"/);
    assert.match(html, /aria-label="Open Twitter \/ X profile for twitter Candidate 2"/);
    assert.match(html, /aria-label="View source for twitter Candidate 2 on Twitter \/ X"/);
    assert.equal(PeopleSearchUI.safeAbsolutePublicHttpURL("http://localhost/secret"), "");
    assert.equal(PeopleSearchUI.safeAbsolutePublicHttpURL("https://profiles.example.org/user"), "https://profiles.example.org/user");

    const partial = PeopleSearchUI.buildResultsMarkup({
        status: "partial",
        query: { full_name: "Partial Person" },
        profiles: [],
    });
    const providerError = PeopleSearchUI.buildResultsMarkup({
        status: "provider_error",
        query: { full_name: "Error Person" },
        profiles: [],
    });
    assert.match(partial, /people-result-status is-warning mono[^>]*>PARTIAL/);
    assert.match(providerError, /people-result-status is-error mono[^>]*>PROVIDER ERROR/);
});

test("readiness prioritizes a server-disabled policy over missing configuration", () => {
    const { document, elements } = createDocument();
    const ready = PeopleSearchUI.applyReadiness({
        enabled: false,
        configured: false,
        limits: { profiles: 20 },
    }, document);

    assert.equal(ready, false);
    assert.equal(elements["people-search-readiness-title"].textContent, "People Search disabled");
    assert.equal(elements["people-search-submit"].disabled, true);
});

test("profile groups start at five cards and expand or collapse inline", () => {
    const { document, elements } = createDocument();
    const focused = [];
    const groupRoot = {
        querySelector(selector) {
            if (selector.includes("data-people-profile-index")) {
                return fakeElement({ focus() { focused.push("first-new-profile"); } });
            }
            if (selector.includes("data-people-toggle-group")) {
                return fakeElement({ focus() { focused.push("replacement-toggle"); } });
            }
            return null;
        },
    };
    elements["people-search-results"].querySelector = selector => {
        assert.match(selector, /data-people-profile-group="instagram"/);
        return groupRoot;
    };
    const data = {
        status: "completed",
        query: { full_name: "Example Person" },
        profiles: Array.from({ length: 6 }, (_, index) => profile("instagram", index + 1)),
    };

    PeopleSearchUI.renderResult(data, document, "http://127.0.0.1:8010");
    assert.equal(elements["people-search-result-announcement"].textContent, "People Search returned 6 profile candidates.");
    assert.equal((elements["people-search-results"].innerHTML.match(/class="people-profile-card"/g) || []).length, 5);
    assert.match(elements["people-search-results"].innerHTML, /Show more profiles \(1 more\)/);

    assert.equal(PeopleSearchUI.toggleGroup("instagram", document, "http://127.0.0.1:8010"), true);
    assert.equal(focused.at(-1), "first-new-profile");
    assert.equal(elements["people-search-result-announcement"].textContent, "1 additional Instagram profile shown.");
    assert.equal((elements["people-search-results"].innerHTML.match(/class="people-profile-card"/g) || []).length, 6);
    assert.match(elements["people-search-results"].innerHTML, />Show less<\/button>/);

    assert.equal(PeopleSearchUI.toggleGroup("instagram", document, "http://127.0.0.1:8010"), false);
    assert.equal(focused.at(-1), "replacement-toggle");
    assert.equal(elements["people-search-result-announcement"].textContent, "Instagram collapsed to the first 5 profiles.");
    assert.equal((elements["people-search-results"].innerHTML.match(/class="people-profile-card"/g) || []).length, 5);
});

test("navigation is exclusive and leaving the view aborts and suppresses a stale response", async () => {
    const { document, elements } = createDocument();
    PeopleSearchUI.clear(document);
    elements["people-full-name"].value = "Example Person";
    elements["people-location"].value = "Lucknow";
    elements["people-country-code"].value = "IN";
    elements["people-candidate-limit"].value = "10";
    PeopleSearchUI.applyReadiness({ enabled: true, configured: true, limits: { profiles: 20 } }, document);

    await PeopleSearchUI.open({ document, loadStatus: false });
    assert.equal(elements["people-search-view"].style.display, "block");
    assert.equal(elements["hero-search-view"].style.display, "none");
    assert.equal(elements["email-investigation-view"].style.display, "none");
    assert.equal(elements["phone-investigation-view"].style.display, "none");
    assert.equal(elements["nav-people-search"].classList.contains("is-active"), true);
    assert.equal(elements["nav-lea-export"].style.display, "none");

    PeopleSearchUI.renderResult({
        status: "completed",
        query: { full_name: "Previous Person" },
        profiles: Array.from({ length: 6 }, (_, index) => profile("instagram", index + 1)),
    }, document, "http://127.0.0.1:8010");
    PeopleSearchUI.toggleGroup("instagram", document, "http://127.0.0.1:8010");
    const previousMarkup = elements["people-search-results"].innerHTML;
    assert.match(previousMarkup, />Show less<\/button>/);
    assert.deepEqual(PeopleSearchUI.stateSnapshot().expandedGroups, ["instagram"]);

    let resolveFetch;
    let captured;
    const fetchImpl = (url, options) => {
        captured = { url, options, payload: JSON.parse(options.body) };
        return new Promise(resolve => { resolveFetch = resolve; });
    };
    const pending = PeopleSearchUI.submitSearch({
        document,
        fetchImpl,
        apiBase: "http://api.test",
    });
    assert.equal(captured.url, "http://api.test/api/v1/person-search");
    assert.equal(captured.payload.full_name, "Example Person");
    assert.equal(captured.payload.location, "Lucknow");
    assert.equal(captured.options.signal.aborted, false);
    assert.equal(elements["people-search-results"].style.display, "block");
    assert.equal(elements["people-search-results"].innerHTML, previousMarkup);

    PeopleSearchUI.deactivate(document);
    assert.equal(captured.options.signal.aborted, true);
    assert.equal(captured.options.signal.reason, "view_changed");
    resolveFetch({
        ok: true,
        status: 200,
        async json() {
            return { status: "completed", query: { full_name: "LATE" }, profiles: [profile("instagram", 99)] };
        },
    });
    assert.equal(await pending, null);
    assert.doesNotMatch(elements["people-search-results"].innerHTML, /LATE|instagram_99/);
    assert.match(elements["people-search-results"].innerHTML, /Previous Person/);
    assert.match(elements["people-search-results"].innerHTML, />Show less<\/button>/);
    assert.deepEqual(PeopleSearchUI.stateSnapshot().expandedGroups, ["instagram"]);
    assert.equal(PeopleSearchUI.stateSnapshot().busy, false);
    assert.equal(PeopleSearchUI.stateSnapshot().hasActiveRequest, false);

    PeopleSearchUI.clear(document);
    assert.equal(elements["people-search-view"].style.display, "none");
    assert.equal(elements["people-search-results"].innerHTML, "");
});

test("a superseded readiness request cannot re-enable Retry during the current request", async () => {
    const { document, elements } = createDocument();
    PeopleSearchUI.clear(document);
    const resolvers = [];
    const fetchImpl = () => new Promise(resolve => { resolvers.push(resolve); });

    const first = PeopleSearchUI.loadStatus({ document, fetchImpl, apiBase: "http://api.test" });
    const second = PeopleSearchUI.loadStatus({ document, fetchImpl, apiBase: "http://api.test" });
    assert.equal(elements["people-search-status-refresh"].disabled, true);

    resolvers[0]({
        ok: true,
        status: 200,
        async json() { return { enabled: true, configured: true, limits: { profiles: 20 } }; },
    });
    assert.equal(await first, null);
    assert.equal(elements["people-search-status-refresh"].disabled, true);

    resolvers[1]({
        ok: true,
        status: 200,
        async json() { return { enabled: true, configured: true, limits: { profiles: 20 } }; },
    });
    assert.deepEqual(await second, { enabled: true, configured: true, limits: { profiles: 20 } });
    assert.equal(elements["people-search-status-refresh"].disabled, false);

    PeopleSearchUI.clear(document);
});
