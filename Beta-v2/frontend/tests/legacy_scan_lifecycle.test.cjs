"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const appPath = path.join(__dirname, "..", "js", "app.js");
const appSource = fs.readFileSync(appPath, "utf8");

function deferred() {
    let resolve;
    let reject;
    const promise = new Promise((resolvePromise, rejectPromise) => {
        resolve = resolvePromise;
        reject = rejectPromise;
    });
    return { promise, resolve, reject };
}

function response(payload, jsonPromise = null) {
    return {
        ok: true,
        status: 200,
        async json() {
            return jsonPromise || payload;
        },
    };
}

function lateInvestigation(id) {
    return {
        investigation_id: id,
        consolidated_identity: null,
        ai_personality: null,
        gemini_reasoning: null,
        associated_accounts: [],
        dorking_results: { results: [] },
        telegram_cti: { total_records: 0, databases: [], results: [] },
        scraped_data: {},
        wmn_results: { hits: [] },
        internal_database_matches: { matches: [] },
    };
}

function createHarness() {
    const nodes = new Map();
    const events = new Map();
    const alerts = [];
    const exports = [];
    const fetchCalls = [];
    const clearedIntervals = [];
    const scrollCalls = [];
    let intervalId = 0;
    let fetchImpl = () => Promise.reject(new Error("fetch fixture not configured"));
    let logoutCalls = 0;
    let emailClearCalls = 0;

    function nodeFor(id) {
        if (!nodes.has(id)) {
            const node = {
                id,
                value: "",
                checked: false,
                disabled: false,
                innerHTML: "",
                textContent: "",
                className: "",
                children: [],
                scrollHeight: 0,
                scrollTop: 0,
                style: {},
                classList: { add() {}, remove() {}, toggle() {} },
                appendChild(child) { this.children.push(child); },
                addEventListener() {},
                remove() {},
                querySelectorAll() { return []; },
                replaceChildren(...children) {
                    this.children = children;
                    this.innerHTML = "";
                    this.textContent = "";
                },
            };
            nodes.set(id, node);
        }
        return nodes.get(id);
    }

    const sandbox = {
        API_BASE: "http://127.0.0.1:8010",
        AbortController,
        URL,
        console,
        location: { protocol: "http:", hostname: "127.0.0.1" },
        sessionStorage: { getItem() { return null; }, setItem() {}, removeItem() {} },
        document: {
            getElementById: nodeFor,
            querySelectorAll() { return []; },
            createElement() { return nodeFor(`created-${nodes.size}`); },
        },
        SocAuth: {
            hasRole(role) {
                return role === "investigator" || role === "breach_pii_viewer";
            },
            fetch(url, options) {
                fetchCalls.push({ url: String(url), options });
                return fetchImpl(url, options);
            },
            async logout() {
                logoutCalls += 1;
            },
        },
        LeaPdfExporter: {
            exportReport(data) { exports.push(data); },
        },
        clearEmailInvestigationState() { emailClearCalls += 1; },
        addEventListener(type, callback) {
            const callbacks = events.get(type) || [];
            callbacks.push(callback);
            events.set(type, callbacks);
        },
        dispatchEvent() {},
        alert(message) { alerts.push(String(message)); },
        scrollTo(options) { scrollCalls.push(options); },
        setInterval() {
            intervalId += 1;
            return intervalId;
        },
        clearInterval(id) { clearedIntervals.push(id); },
        setTimeout() { return 1; },
        clearTimeout() {},
    };
    sandbox.window = sandbox;
    vm.createContext(sandbox);
    vm.runInContext(appSource, sandbox, { filename: appPath });

    const renderCalls = [];
    sandbox.__renderCalls = renderCalls;
    vm.runInContext(
        "renderResults = data => { window.__renderCalls.push(data); document.getElementById('consolidated-identity-body').innerHTML = data.investigation_id; };",
        sandbox,
    );

    return {
        sandbox,
        nodeFor,
        events,
        alerts,
        exports,
        fetchCalls,
        clearedIntervals,
        scrollCalls,
        renderCalls,
        setFetchImpl(implementation) { fetchImpl = implementation; },
        get logoutCalls() { return logoutCalls; },
        get emailClearCalls() { return emailClearCalls; },
    };
}

function internalState(harness) {
    return vm.runInContext(
        "({ currentInvestigationData, cachedGroqData, cachedGeminiData, activeLegacyController, legacyRequestSerial, progressInterval })",
        harness.sandbox,
    );
}

function seedSensitiveLegacyState(harness, suffix) {
    vm.runInContext(
        `currentInvestigationData = { investigation_id: "SEED-${suffix}" };
         cachedGroqData = { summary: "GROQ-${suffix}" };
         cachedGeminiData = { summary: "GEMINI-${suffix}" };`,
        harness.sandbox,
    );

    for (const id of [
        "hero-target-username",
        "target-username",
        "provider-email",
        "provider-phone",
    ]) {
        harness.nodeFor(id).value = `${id}-${suffix}`;
    }
    for (const id of [
        "consolidated-confidence-badge",
        "ai-category-badge",
        "associated-accounts-badge",
        "media-gallery-badge",
        "dorking-count-badge",
        "cti-records-badge",
        "diagnostics-summary-badge",
    ]) {
        harness.nodeFor(id).textContent = `BADGE-${suffix}`;
    }
    for (const id of [
        "consolidated-identity-body",
        "ai-personality-body",
        "associated-accounts-body",
        "media-gallery-body",
        "dorking-results-body",
        "telegram-cti-body",
        "platform-dossiers-body",
        "diagnostics-body",
        "console-stream",
    ]) {
        harness.nodeFor(id).innerHTML = `SENSITIVE-RESULT-${suffix}`;
        harness.nodeFor(id).textContent = `SENSITIVE-RESULT-${suffix}`;
    }
    harness.nodeFor("scan-loader-overlay").style.display = "flex";
    harness.nodeFor("results-workspace").style.display = "block";
    harness.nodeFor("hero-search-view").style.display = "none";
    harness.nodeFor("card-media-gallery").style.display = "block";
}

function assertStateCleared(harness, previousSerial, label) {
    const state = internalState(harness);
    assert.equal(state.currentInvestigationData, null, `${label}: current result cache survived`);
    assert.equal(state.cachedGroqData, null, `${label}: Groq cache survived`);
    assert.equal(state.cachedGeminiData, null, `${label}: Gemini cache survived`);
    assert.equal(state.activeLegacyController, null, `${label}: active controller survived`);
    assert.equal(state.progressInterval, null, `${label}: progress timer survived`);
    assert.equal(state.legacyRequestSerial, previousSerial + 1, `${label}: request serial was not invalidated`);

    for (const id of [
        "hero-target-username",
        "target-username",
        "provider-email",
        "provider-phone",
    ]) {
        assert.equal(harness.nodeFor(id).value, "", `${label}: input ${id} survived`);
    }
    for (const id of [
        "consolidated-confidence-badge",
        "ai-category-badge",
        "associated-accounts-badge",
        "media-gallery-badge",
        "dorking-count-badge",
        "cti-records-badge",
        "diagnostics-summary-badge",
    ]) {
        assert.equal(harness.nodeFor(id).textContent, "", `${label}: badge ${id} survived`);
    }
    for (const id of [
        "consolidated-identity-body",
        "ai-personality-body",
        "associated-accounts-body",
        "media-gallery-body",
        "dorking-results-body",
        "telegram-cti-body",
        "platform-dossiers-body",
        "diagnostics-body",
        "console-stream",
    ]) {
        assert.equal(harness.nodeFor(id).innerHTML, "", `${label}: rendered result ${id} survived`);
        assert.equal(harness.nodeFor(id).textContent, "", `${label}: rendered text ${id} survived`);
    }
    assert.equal(harness.nodeFor("scan-loader-overlay").style.display, "none");
    assert.equal(harness.nodeFor("results-workspace").style.display, "none");
    assert.equal(harness.nodeFor("hero-search-view").style.display, "block");
    assert.equal(harness.nodeFor("card-media-gallery").style.display, "none");
}

function prepareScanInput(harness, suffix) {
    harness.nodeFor("hero-target-username").value = `target-${suffix}`;
    harness.nodeFor("target-username").value = `target-${suffix}`;
    harness.nodeFor("provider-email").value = `${suffix}@example.org`;
    harness.nodeFor("provider-phone").value = "+911234567890";
}

async function flushMicrotasks() {
    await Promise.resolve();
    await Promise.resolve();
}

async function testSessionEventWhileFetchIsPending() {
    const harness = createHarness();
    seedSensitiveLegacyState(harness, "EVENT");
    prepareScanInput(harness, "event");

    const pendingResponse = deferred();
    harness.setFetchImpl(() => pendingResponse.promise);
    const scanPromise = harness.sandbox.executeScan(true);
    assert.equal(harness.fetchCalls.length, 1);
    const { signal } = harness.fetchCalls[0].options;
    assert.equal(signal.aborted, false);
    harness.sandbox.triggerLeaPdfExport();
    assert.equal(harness.exports.length, 1, "seed result was not exportable before clear");
    assert.equal(harness.exports[0].investigation_id, "SEED-EVENT");
    const serialWhilePending = internalState(harness).legacyRequestSerial;

    for (const callback of harness.events.get("soc:unauthenticated") || []) callback();
    assert.equal(signal.aborted, true, "session event did not abort the pending request");
    assert.equal(signal.reason, "session_cleared");
    assertStateCleared(harness, serialWhilePending, "session event clear");

    pendingResponse.resolve(response(lateInvestigation("LATE-FETCH-RESPONSE")));
    await scanPromise;

    assertStateCleared(harness, serialWhilePending, "late fetch response");
    assert.equal(harness.renderCalls.length, 0, "late fetch response rendered results");
    assert.equal(harness.scrollCalls.length, 0, "late fetch response changed viewport");
    const exportsBefore = harness.exports.length;
    harness.sandbox.triggerLeaPdfExport();
    assert.equal(harness.exports.length, exportsBefore, "cleared result remained exportable");
    assert.match(harness.alerts.at(-1), /execute an OSINT investigation/i);
}

async function testLogoutWhileJsonIsPending() {
    const harness = createHarness();
    seedSensitiveLegacyState(harness, "LOGOUT");
    prepareScanInput(harness, "logout");

    const pendingJson = deferred();
    let jsonStarted = false;
    harness.setFetchImpl(async () => ({
        ok: true,
        status: 200,
        json() {
            jsonStarted = true;
            return pendingJson.promise;
        },
    }));

    const scanPromise = harness.sandbox.executeScan(true);
    await flushMicrotasks();
    assert.equal(jsonStarted, true, "scan did not reach the deferred JSON phase");
    const { signal } = harness.fetchCalls[0].options;
    const serialWhilePending = internalState(harness).legacyRequestSerial;

    await harness.sandbox.handleLogout();
    assert.equal(harness.logoutCalls, 1, "backend logout was not requested");
    assert.equal(harness.emailClearCalls, 1, "email-investigation state was not cleared");
    assert.equal(signal.aborted, true, "logout did not abort pending JSON work");
    assert.equal(signal.reason, "session_cleared");
    assertStateCleared(harness, serialWhilePending, "logout clear");

    pendingJson.resolve(lateInvestigation("LATE-JSON-RESPONSE"));
    await scanPromise;

    assertStateCleared(harness, serialWhilePending, "late JSON response");
    assert.equal(harness.renderCalls.length, 0, "late JSON response rendered results");
    assert.equal(harness.scrollCalls.length, 0, "late JSON response changed viewport");
    assert(!harness.nodeFor("consolidated-identity-body").innerHTML.includes("LATE-JSON-RESPONSE"));
}

async function main() {
    await testSessionEventWhileFetchIsPending();
    await testLogoutWhileJsonIsPending();
    console.log("legacy_scan_lifecycle.test.cjs: all assertions passed");
}

main().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
