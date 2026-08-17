"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { URL: NodeURL } = require("node:url");

const SCRIPT_PATH = path.join(__dirname, "..", "js", "email_investigation.js");
const MODULE_SOURCE = fs.readFileSync(SCRIPT_PATH, "utf8");

const REQUIRED_IDS = [
    "email-investigation-form",
    "email-target-input",
    "email-case-id",
    "email-reason-code",
    "email-authorization-confirmed",
    "email-option-gravatar",
    "email-option-breaches",
    "email-restricted-option-row",
    "email-option-restricted-records",
    "email-option-dorking",
    "email-dork-query-limit",
    "email-investigation-results",
    "email-investigation-view",
    "hero-search-view",
    "results-workspace",
    "nav-username-investigation",
    "nav-email-investigation",
    "nav-lea-export",
    "email-syntax-badge",
    "email-validation-message",
    "email-form-error",
    "email-investigation-loading",
    "email-investigate-button",
    "email-cancel-button",
    "email-form-state",
    "email-loading-message",
    "email-result-target",
    "email-result-meta",
    "email-validation-domain-body",
    "email-breach-summary-body",
    "email-breach-list-body",
    "email-discovery-results-body",
    "email-harvest-results-body",
    "email-gravatar-results-body",
    "email-limitations-body",
    "email-validation-result-badge",
    "email-breach-result-badge",
    "email-discovery-result-badge",
    "email-harvest-result-badge",
    "email-gravatar-result-badge",
    "provider-email",
    "hero-target-username",
    "target-username",
];

function makeResponse(overrides = {}) {
    const base = {
        investigation_id: "UPP-EMAIL-TEST",
        status: "partial",
        case_id: "CASE-123",
        reason_code: "active_investigation",
        normalized_email: "Subject@example.com",
        authorization: {
            attested: true,
            scope: "single_email",
            breach_provider_enabled: true,
            authenticated_user: "analyst-one",
            roles: ["investigator", "breach_pii_viewer"],
            restricted_disclosure: "audited",
            audit_event_id: "audit-event-test",
        },
        address_analysis: {
            status: "completed",
            local_part: "Subject",
            domain: "example.com",
            local_part_pattern: "word",
            provider_category: "corporate",
            provider_name: "Example Mail",
            disposable: "not_listed",
            notes: [],
            provenance: {
                provider: "local",
                method: "parse",
                collected_at: "2026-08-16T00:00:00Z",
                calls_made: 0,
                scope: "exact_email_only",
            },
        },
        domain_intelligence: {
            status: "completed",
            domain: "example.com",
            domain_resolves: true,
            has_mx: true,
            mx_records: [{ priority: 10, host: "mx.example.com" }],
            addresses: ["203.0.113.2"],
            mail_provider: "Custom",
            provenance: {
                provider: "dns",
                method: "dns",
                collected_at: "2026-08-16T00:00:00Z",
                calls_made: 1,
                scope: "target_domain",
            },
        },
        gravatar: {
            status: "found",
            profile_found: true,
            display_name: "Analyst Test",
            username: "safe",
            profile_url: "https://gravatar.com/safe",
            avatar_url: "http://127.0.0.1/private-avatar",
            location: "Test",
            about: "Public profile",
            verified_accounts: [{ service: "Unsafe scheme", url: "javascript:alert(1)" }],
            provenance: {
                provider: "gravatar",
                method: "hash",
                collected_at: "2026-08-16T00:00:00Z",
                calls_made: 1,
                scope: "exact_email_hash",
            },
        },
        breach_intelligence: {
            status: "found",
            compromised: true,
            database_count: 1,
            record_count: 2,
            truncated: false,
            databases: [{
                name: "Example Breach",
                source: "leakosint",
                breach_date: "2025-01",
                record_count: 2,
                data_types: ["Email", "Password"],
                credential_exposure_detected: true,
                sensitive_fields_redacted: ["Password"],
                password: "DO_NOT_RENDER_OR_EXPORT",
                incident_summary: "Public incident summary",
                disclosure_policy: "restricted_contact_v1",
                records_truncated: false,
                restricted_records: [{
                    record_id: "record-1",
                    target_email_match: true,
                    suppressed_categories: ["authentication"],
                    additional_fields_detected: 2,
                    fields: [
                        { key: "email", label: "Email", category: "contact", value: "Subject@example.com" },
                        { key: "full_name", label: "Full Name", category: "contact", value: "AUTHORIZED CONTACT SENTINEL" },
                        { key: "phone", label: "Phone", category: "contact", value: "9999999999" },
                        { key: "password", label: "Password", category: "authentication", value: "NEVER DISPLAY PASSWORD" },
                        { key: "unknown", label: "Unknown", category: "other", value: "NEVER DISPLAY UNKNOWN" },
                    ],
                }],
            }],
            provenance: {
                provider: "leakosint",
                method: "metadata",
                collected_at: "2026-08-16T00:00:00Z",
                calls_made: 1,
                scope: "exact_email_only",
            },
        },
        web_discovery: {
            status: "completed",
            provider: "serpapi",
            query_cap: 3,
            queries_planned: 1,
            queries_run: 1,
            call_cap: 6,
            provider_calls_made: 2,
            result_count: 2,
            truncated: false,
            queries: [
                { query: "Subject@example.com", engine: "google", status: "completed", result_count: 1 },
                { query: "Subject@example.com", engine: "bing", status: "completed", result_count: 1 },
            ],
            results: [{
                result_id: "result-1",
                title: "=HYPERLINK(\"https://attacker.invalid\")",
                url: "https://example.com/evidence",
                domain: "example.com",
                snippet: "Subject@example.com and other@example.com",
                category: "exact_match",
                query: "Subject@example.com",
                match_type: "direct",
                credibility: "high",
                captured_at: "2026-08-16T00:00:00Z",
                source_engines: ["google"],
            }, {
                result_id: "result-2",
                title: "Unsafe URL",
                url: "javascript:alert(1)",
                domain: "evil.test",
                snippet: "unrelated@evil.test",
                category: "forum",
                query: "Subject@example.com",
                match_type: "partial",
                credibility: "low",
                captured_at: "2026-08-16T00:00:00Z",
                source_engines: ["bing"],
            }],
            harvested_emails: [],
            provenance: {
                provider: "serpapi",
                method: "search",
                collected_at: "2026-08-16T00:00:00Z",
                calls_made: 1,
                scope: "bounded",
            },
        },
        risk_summary: {
            overall_status: "compromised",
            score: 71,
            label: "high",
            independent_evidence_groups: 2,
            corroborated: true,
            rationale: ["Two independent evidence groups."],
        },
        limitations: ["Test limitation"],
        timestamp: "2026-08-16T00:00:00Z",
    };
    return { ...base, ...overrides };
}

function createHarness(
    response = makeResponse(),
    roles = ["investigator", "breach_pii_viewer"],
) {
    const eventHandlers = {};
    const windowEventHandlers = {};
    const domReadyHandlers = [];
    const downloads = [];
    const fetchCalls = [];
    let lastBlob = null;

    const nodes = Object.fromEntries(REQUIRED_IDS.map(id => [id, {
        id,
        value: "",
        checked: false,
        disabled: false,
        textContent: "",
        innerHTML: "",
        className: "",
        style: { display: "" },
        classList: { add() {}, remove() {}, toggle() {} },
        addEventListener(type, handler) { eventHandlers[`${id}:${type}`] = handler; },
        focus() {},
        scrollIntoView() {},
        replaceChildren() { this.innerHTML = ""; },
        reset() {},
    }]));

    class FakeBlob {
        constructor(parts, options) {
            this.parts = parts;
            this.type = options?.type || "";
            lastBlob = this;
        }
    }

    class SafeURL extends NodeURL {}
    SafeURL.createObjectURL = () => "blob:test-export";
    SafeURL.revokeObjectURL = () => {};

    class FakeAbortController {
        constructor() { this.signal = { aborted: false, reason: null }; }
        abort(reason) { this.signal.aborted = true; this.signal.reason = reason; }
    }

    async function fakeFetch(url, options) {
        fetchCalls.push({ url, options, payload: options.body ? JSON.parse(options.body) : null });
        return { ok: true, status: 200, async json() { return response; } };
    }

    const sandbox = {
        URL: SafeURL,
        Blob: FakeBlob,
        AbortController: FakeAbortController,
        console,
        API_BASE: "http://127.0.0.1:8010",
        document: {
            getElementById(id) { return nodes[id] || null; },
            createElement() {
                return {
                    href: "",
                    download: "",
                    click() { downloads.push({ href: this.href, filename: this.download }); },
                    remove() {},
                };
            },
            body: { appendChild() {} },
        },
        addEventListener(type, handler) {
            if (type === "DOMContentLoaded") domReadyHandlers.push(handler);
            else (windowEventHandlers[type] ||= []).push(handler);
        },
        scrollTo() {},
        setTimeout(handler, milliseconds) {
            if (milliseconds <= 1000) {
                handler();
                return 0;
            }
            const timer = setTimeout(handler, milliseconds);
            timer.unref();
            return timer;
        },
        clearTimeout,
        SocAuth: {
            hasRole(role) { return roles.includes(role); },
            fetch: fakeFetch,
        },
        fetch: fakeFetch,
    };
    sandbox.window = sandbox;

    vm.runInNewContext(MODULE_SOURCE, sandbox, { filename: SCRIPT_PATH });
    domReadyHandlers.forEach(handler => handler());

    return {
        sandbox,
        nodes,
        eventHandlers,
        windowEventHandlers,
        fetchCalls,
        downloads,
        getLastBlob: () => lastBlob,
    };
}

function fillValidForm(harness, dorkLimit = "3") {
    const { nodes } = harness;
    nodes["email-target-input"].value = "Subject@Example.com";
    nodes["email-case-id"].value = "CASE-123";
    nodes["email-reason-code"].value = "active_investigation";
    nodes["email-authorization-confirmed"].checked = true;
    nodes["email-option-gravatar"].checked = true;
    nodes["email-option-breaches"].checked = true;
    nodes["email-option-restricted-records"].checked = true;
    nodes["email-option-dorking"].checked = true;
    nodes["email-dork-query-limit"].value = dorkLimit;
}

async function submit(harness) {
    await harness.eventHandlers["email-investigation-form:submit"]({ preventDefault() {} });
}

async function main() {
    const governanceHarness = createHarness();
    assert.equal(
        governanceHarness.nodes["email-option-restricted-records"].checked,
        false,
        "restricted disclosure must be an explicit opt-in",
    );
    fillValidForm(governanceHarness);
    governanceHarness.nodes["email-authorization-confirmed"].checked = false;
    await submit(governanceHarness);
    assert.equal(governanceHarness.fetchCalls.length, 0, "authorization gate must block all calls");
    assert.match(governanceHarness.nodes["email-form-error"].textContent, /authorization/i);

    const zeroQueryHarness = createHarness();
    fillValidForm(zeroQueryHarness, "0");
    await submit(zeroQueryHarness);
    assert.equal(zeroQueryHarness.fetchCalls[0].payload.include_web_discovery, false);
    assert.equal(zeroQueryHarness.fetchCalls[0].payload.dork_query_limit, 0);

    const harness = createHarness();
    fillValidForm(harness);
    harness.eventHandlers["email-target-input:input"]();
    assert.equal(harness.nodes["email-syntax-badge"].textContent, "SYNTAX VALID");
    await submit(harness);

    const payload = harness.fetchCalls[0].payload;
    assert.equal(payload.email, "Subject@example.com");
    assert.equal(payload.authorized, true);
    assert.equal(payload.case_id, "CASE-123");
    assert.equal(payload.reason_code, "active_investigation");
    assert.equal(payload.include_restricted_breach_details, true);
    assert.equal(payload.dork_query_limit, 3);
    assert.equal(harness.nodes["email-investigation-results"].style.display, "block");

    const allRendered = Object.values(harness.nodes)
        .map(node => `${node.innerHTML} ${node.textContent}`)
        .join("\n");
    assert.match(allRendered, /SERVER RISK SCORE/);
    assert.match(allRendered, /71\/100/);
    assert.match(allRendered, /QUERIES:\s*1\/3/);
    assert.match(allRendered, /PROVIDER CALLS:\s*2\/6/);
    assert.match(allRendered, /GOOGLE/);
    assert.match(allRendered, /BING/);
    assert.match(allRendered, /CREDENTIAL MATERIAL PRESENT/);
    assert.match(allRendered, /\[REDACTED\]/);
    assert.doesNotMatch(allRendered, /DO_NOT_RENDER_OR_EXPORT/);
    assert.match(allRendered, /AUTHORIZED CONTACT SENTINEL/);
    assert.match(allRendered, /9999999999/);
    assert.match(allRendered, /SUPPRESSED VALUE CATEGORIES:\s*Authentication/);
    assert.match(allRendered, /2 UNREVIEWED FIELD\(S\) NOT DISCLOSED/);
    assert.doesNotMatch(allRendered, /NEVER DISPLAY PASSWORD|NEVER DISPLAY UNKNOWN/);
    assert.doesNotMatch(allRendered, /javascript:/i);
    assert.doesNotMatch(allRendered, /127\.0\.0\.1\/private-avatar/);

    const validAvatarResponse = makeResponse();
    validAvatarResponse.gravatar.avatar_url = "https://secure.gravatar.com/avatar/public-hash";
    const validAvatarHarness = createHarness(validAvatarResponse);
    fillValidForm(validAvatarHarness);
    await submit(validAvatarHarness);
    const avatarHTML = validAvatarHarness.nodes["email-gravatar-results-body"].innerHTML;
    assert.match(avatarHTML, /\/api\/v1\/investigation\/proxy_image\?url=/);
    assert.match(avatarHTML, /https%3A%2F%2Fsecure\.gravatar\.com%2Favatar%2Fpublic-hash/);
    assert.match(avatarHTML, /crossorigin="use-credentials"/);
    assert.doesNotMatch(avatarHTML, /src="https:\/\/secure\.gravatar\.com/i);

    const harvestRendered = harness.nodes["email-harvest-results-body"].innerHTML;
    assert.match(harvestRendered, /other@example\.com/);
    assert.doesNotMatch(harvestRendered, /unrelated@evil\.test/);

    harness.sandbox.exportEmailInvestigation("csv");
    const csv = harness.getLastBlob().parts.join("");
    assert.match(csv, /"'=HYPERLINK/);
    assert.doesNotMatch(csv, /DO_NOT_RENDER_OR_EXPORT/);
    assert.doesNotMatch(csv, /AUTHORIZED CONTACT SENTINEL|9999999999/);
    assert.equal(harness.downloads[0].filename, "CASE-123_email_investigation.csv");
    assert.doesNotMatch(harness.downloads[0].filename, /Subject|example\.com/i);

    harness.sandbox.exportEmailInvestigation("json");
    const jsonExport = harness.getLastBlob().parts.join("");
    assert.doesNotMatch(jsonExport, /AUTHORIZED CONTACT SENTINEL|9999999999|restricted_records/i);

    for (const handler of harness.windowEventHandlers["soc:unauthenticated"] || []) handler();
    const afterLogout = Object.values(harness.nodes)
        .map(node => `${node.innerHTML} ${node.textContent}`)
        .join("\n");
    assert.doesNotMatch(afterLogout, /AUTHORIZED CONTACT SENTINEL|9999999999/);
    assert.equal(harness.nodes["email-investigation-results"].style.display, "none");

    const investigatorOnlyHarness = createHarness(makeResponse(), ["investigator"]);
    fillValidForm(investigatorOnlyHarness);
    await submit(investigatorOnlyHarness);
    assert.equal(
        investigatorOnlyHarness.fetchCalls[0].payload.include_restricted_breach_details,
        false,
        "both backend roles are required for restricted disclosure",
    );
    assert.equal(investigatorOnlyHarness.nodes["email-restricted-option-row"].style.display, "none");

    const unavailableHarness = createHarness(makeResponse({
        breach_intelligence: {
            status: "not_configured",
            compromised: null,
            database_count: 0,
            record_count: 0,
            truncated: false,
            databases: [],
            provenance: {
                provider: "leakosint",
                method: "disabled",
                collected_at: "2026-08-16T00:00:00Z",
                calls_made: 0,
                scope: "exact_email_only",
            },
        },
        risk_summary: {
            overall_status: "unknown",
            score: null,
            label: "unknown",
            independent_evidence_groups: 0,
            corroborated: false,
            rationale: ["Breach provider is unavailable."],
        },
    }));
    fillValidForm(unavailableHarness);
    await submit(unavailableHarness);
    const unavailable = `${unavailableHarness.nodes["email-breach-summary-body"].innerHTML} ${unavailableHarness.nodes["email-breach-list-body"].innerHTML}`;
    assert.match(unavailable, /not configured/i);
    assert.match(unavailable, /No safety conclusion/i);
    assert.doesNotMatch(unavailable, /NO HITS RETURNED/);

    console.log("email_investigation_ui.test.cjs: all assertions passed");
}

main().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
