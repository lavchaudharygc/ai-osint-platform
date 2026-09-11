"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const sourcePath = path.join(__dirname, "..", "js", "auth.js");
const source = fs.readFileSync(sourcePath, "utf8");

function response(status, payload) {
    return {
        ok: status >= 200 && status < 300,
        status,
        headers: {
            get(name) {
                return String(name).toLowerCase() === "x-request-id"
                    ? "request-test-1234"
                    : null;
            },
        },
        async json() { return payload; },
    };
}

async function main() {
    assert.doesNotMatch(source, /testingaccount|uppolice/);

    const calls = [];
    const events = {};
    const dispatched = [];
    const storage = new Map();
    const diagnosticStorage = new Map();
    const expiresAt = new Date(Date.now() + 60 * 60 * 1000).toISOString();
    let expiryHandler = null;
    let nextTimerId = 0;
    const timers = new Map();
    let meAuthenticated = false;
    let meFailureStatus = null;
    let deferNextMe = false;
    let resolveDeferredMe = null;
    let deferNextMeBody = false;
    let resolveDeferredMeBody = null;
    let deferNextLogin = false;
    let resolveDeferredLogin = null;
    let loginRequestCount = 0;
    let hangLogout = false;
    let hangNextMe = false;
    let hangNextMeBody = false;
    let invalidNextMeJson = false;
    const nodes = Object.fromEntries([
        "login-screen", "main-dashboard", "login-error", "soc-authenticated-user",
        "login-user", "login-pass", "login-submit",
    ].map(id => [id, {
        id,
        value: "",
        textContent: "",
        disabled: false,
        style: { display: "" },
        focus() {},
    }]));

    async function fakeFetch(url, options = {}) {
        const headers = options.headers instanceof Headers
            ? Object.fromEntries(options.headers.entries())
            : { ...(options.headers || {}) };
        calls.push({ url: String(url), options: { ...options, headers } });
        if (String(url).endsWith("/me")) {
            if (invalidNextMeJson) {
                invalidNextMeJson = false;
                return {
                    ok: true,
                    status: 200,
                    headers: response(200, {}).headers,
                    async json() {
                        throw new SyntaxError("PRIVATE-AUTH-JSON-SENTINEL");
                    },
                };
            }
            if (hangNextMeBody) {
                hangNextMeBody = false;
                return {
                    ok: true,
                    status: 200,
                    json() { return new Promise(() => {}); },
                };
            }
            if (hangNextMe) {
                hangNextMe = false;
                return new Promise(() => {});
            }
            if (deferNextMeBody) {
                deferNextMeBody = false;
                return {
                    ok: true,
                    status: 200,
                    json() {
                        return new Promise(resolve => {
                            resolveDeferredMeBody = () => resolve({
                                user: "stale-analyst",
                                roles: ["investigator"],
                                csrf_token: "stale-csrf-token",
                                expires_at: expiresAt,
                            });
                        });
                    },
                };
            }
            if (deferNextMe) {
                deferNextMe = false;
                return new Promise(resolve => {
                    resolveDeferredMe = () => resolve(
                        response(401, { detail: "Stale unauthenticated response" }),
                    );
                });
            }
            if (meFailureStatus) {
                return response(meFailureStatus, { detail: "Temporary authentication service failure" });
            }
            return meAuthenticated
                ? response(200, {
                    user: "analyst-one",
                    roles: ["investigator", "breach_pii_viewer"],
                    csrf_token: "csrf-test-token",
                    expires_at: expiresAt,
                })
                : response(401, { detail: "Not authenticated" });
        }
        if (String(url).endsWith("/login")) {
            loginRequestCount += 1;
            meAuthenticated = true;
            if (deferNextLogin) {
                deferNextLogin = false;
                return new Promise(resolve => {
                    resolveDeferredLogin = () => resolve(response(200, {
                        user: "analyst-one",
                        roles: ["investigator", "breach_pii_viewer"],
                        csrf_token: "csrf-test-token",
                        expires_at: expiresAt,
                    }));
                });
            }
            return response(200, {
                user: "analyst-one",
                roles: ["investigator", "breach_pii_viewer"],
                csrf_token: "csrf-test-token",
                expires_at: expiresAt,
            });
        }
        if (String(url).endsWith("/logout")) {
            meAuthenticated = false;
            if (hangLogout) return new Promise(() => {});
            return response(200, { status: "logged_out" });
        }
        if (String(url).endsWith("/provider-unauthorized")) {
            return response(401, { detail: "Collector credentials rejected" });
        }
        return response(200, { status: "ok" });
    }

    class FakeCustomEvent {
        constructor(type, init = {}) { this.type = type; this.detail = init.detail; }
    }

    function updateLatestTimer() {
        expiryHandler = timers.size ? [...timers.values()].at(-1) : null;
    }

    function fakeSetTimeout(handler) {
        const timerId = ++nextTimerId;
        const wrapped = () => {
            timers.delete(timerId);
            updateLatestTimer();
            return handler();
        };
        timers.set(timerId, wrapped);
        updateLatestTimer();
        return timerId;
    }

    function fakeClearTimeout(timerId) {
        timers.delete(timerId);
        updateLatestTimer();
    }

    const sandbox = {
        console: {
            debug() {},
            warn() {},
            log: console.log,
            error: console.error,
        },
        Headers,
        CustomEvent: FakeCustomEvent,
        fetch: fakeFetch,
        sessionStorage: {
            getItem(key) { return storage.has(key) ? storage.get(key) : null; },
            setItem(key, value) { storage.set(key, String(value)); },
            removeItem(key) { storage.delete(key); },
        },
        localStorage: {
            getItem(key) { return diagnosticStorage.has(key) ? diagnosticStorage.get(key) : null; },
            setItem(key, value) { diagnosticStorage.set(key, String(value)); },
            removeItem(key) { diagnosticStorage.delete(key); },
        },
        document: { getElementById(id) { return nodes[id] || null; } },
        location: { protocol: "http:", hostname: "127.0.0.1" },
        API_BASE: "http://127.0.0.1:8010",
        setTimeout: fakeSetTimeout,
        clearTimeout: fakeClearTimeout,
        addEventListener(type, handler) { events[type] = handler; },
        dispatchEvent(event) { dispatched.push(event); },
    };
    sandbox.window = sandbox;

    diagnosticStorage.set("upp_soc_auth_diagnostics_v1", JSON.stringify([
        {
            at: new Date().toISOString(),
            event: "session.initialize_failed",
            endpoint: "auth_initialize",
            reason: "http_error",
            status: 503,
            request_id: "poison-safe-id-1234",
            username: "POISON-USERNAME",
            password: "POISON-PASSWORD",
            target: "POISON-TARGET",
            csrf_token: "POISON-CSRF",
        },
        {
            at: new Date().toISOString(),
            event: "attacker.controlled_event",
            target: "POISON-UNKNOWN-EVENT",
        },
    ]));

    vm.runInNewContext(source, sandbox, { filename: sourcePath });
    await events.DOMContentLoaded();
    assert.equal(nodes["login-screen"].style.display, "flex");
    assert.equal(nodes["main-dashboard"].style.display, "none");

    nodes["login-user"].value = "analyst-one";
    nodes["login-pass"].value = "temporary-test-password";
    assert.equal(await sandbox.SocAuth.login(), true);
    assert.equal(nodes["login-pass"].value, "");
    assert.equal(nodes["login-screen"].style.display, "none");
    assert.equal(nodes["main-dashboard"].style.display, "block");
    assert.equal(sandbox.SocAuth.hasRole("breach_pii_viewer"), true);
    assert.match(nodes["soc-authenticated-user"].textContent, /analyst-one/);

    const stored = [...storage.values()].join("\n");
    assert.doesNotMatch(stored, /temporary-test-password/);
    assert.match(stored, /csrf-test-token/);

    hangNextMe = true;
    const hungInitialize = sandbox.SocAuth.initialize();
    const initializeTimeout = expiryHandler;
    assert.equal(typeof initializeTimeout, "function");
    initializeTimeout();
    assert.equal(await hungInitialize, false);
    assert.equal(storage.size, 1, "startup timeout must retain a non-expired local session");
    assert.equal(nodes["main-dashboard"].style.display, "block");
    assert.equal(typeof expiryHandler, "function", "startup timeout must schedule a retry");

    await sandbox.SocAuth.fetch("http://127.0.0.1:8010/api/v1/email-investigation", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
    });
    const protectedCall = calls.at(-1);
    assert.equal(protectedCall.options.credentials, "include");
    assert.equal(protectedCall.options.headers["x-csrf-token"], "csrf-test-token");
    assert.ok(dispatched.some(event => event.type === "soc:authenticated"));

    const scheduledKeepalive = expiryHandler;
    assert.equal(typeof scheduledKeepalive, "function");
    await scheduledKeepalive();
    assert.equal(storage.size, 1, "successful keepalive must retain local session state");
    assert.equal(nodes["main-dashboard"].style.display, "block");

    invalidNextMeJson = true;
    assert.equal(await sandbox.SocAuth.refresh(), false);
    assert.equal(storage.size, 1, "invalid refresh JSON must retain the local session");
    assert.equal(nodes["main-dashboard"].style.display, "block");

    hangNextMe = true;
    const hungRefresh = sandbox.SocAuth.refresh();
    const refreshTimeout = expiryHandler;
    assert.equal(typeof refreshTimeout, "function");
    refreshTimeout();
    assert.equal(await hungRefresh, false);
    assert.equal(storage.size, 1, "refresh timeout must retain the valid local session");
    assert.equal(nodes["main-dashboard"].style.display, "block");
    assert.equal(typeof expiryHandler, "function", "refresh timeout must schedule a retry");

    hangNextMeBody = true;
    const hungBodyRefresh = sandbox.SocAuth.refresh();
    const bodyTimeout = expiryHandler;
    assert.equal(typeof bodyTimeout, "function");
    bodyTimeout();
    assert.equal(await hungBodyRefresh, false);
    assert.equal(storage.size, 1, "refresh body timeout must retain the local session");
    assert.equal(typeof expiryHandler, "function", "body timeout must schedule a retry");

    const providerDenied = await sandbox.SocAuth.fetch(
        "http://127.0.0.1:8010/api/v1/provider-unauthorized",
    );
    assert.equal(providerDenied.status, 401);
    assert.equal(storage.size, 1, "feature 401 must not destroy a backend-valid SOC session");
    assert.equal(nodes["main-dashboard"].style.display, "block");

    meFailureStatus = 503;
    await sandbox.SocAuth.fetch("http://127.0.0.1:8010/api/v1/provider-unauthorized");
    assert.equal(storage.size, 1, "temporary /auth/me failure must not log the operator out");
    assert.equal(nodes["main-dashboard"].style.display, "block");

    meFailureStatus = null;
    meAuthenticated = false;
    await sandbox.SocAuth.fetch("http://127.0.0.1:8010/api/v1/provider-unauthorized");
    assert.equal(storage.size, 0, "confirmed invalid SOC session must be cleared");
    assert.equal(nodes["main-dashboard"].style.display, "none");
    assert.ok(dispatched.some(event => event.type === "soc:unauthenticated"));

    deferNextMe = true;
    const staleInitialize = sandbox.SocAuth.initialize();
    assert.equal(typeof resolveDeferredMe, "function");
    nodes["login-user"].value = "analyst-one";
    nodes["login-pass"].value = "temporary-test-password";
    assert.equal(await sandbox.SocAuth.login(), true);
    resolveDeferredMe();
    assert.equal(await staleInitialize, true);
    assert.equal(storage.size, 1, "stale startup response must not clear a fresh login");
    assert.equal(nodes["main-dashboard"].style.display, "block");

    await sandbox.SocAuth.logout();
    assert.equal(storage.size, 0);
    assert.equal(nodes["main-dashboard"].style.display, "none");

    deferNextMeBody = true;
    const staleBodyInitialize = sandbox.SocAuth.initialize();
    for (let attempt = 0; attempt < 10 && !resolveDeferredMeBody; attempt += 1) {
        await Promise.resolve();
    }
    assert.equal(typeof resolveDeferredMeBody, "function");
    nodes["login-user"].value = "analyst-one";
    nodes["login-pass"].value = "temporary-test-password";
    assert.equal(await sandbox.SocAuth.login(), true);
    resolveDeferredMeBody();
    assert.equal(await staleBodyInitialize, true);
    assert.match(nodes["soc-authenticated-user"].textContent, /analyst-one/);
    assert.doesNotMatch(nodes["soc-authenticated-user"].textContent, /stale-analyst/);

    await sandbox.SocAuth.logout();
    deferNextLogin = true;
    nodes["login-user"].value = "analyst-one";
    nodes["login-pass"].value = "temporary-test-password";
    const loginCallsBeforeSingleFlight = loginRequestCount;
    const firstLogin = sandbox.SocAuth.login();
    const secondLogin = sandbox.SocAuth.login();
    assert.equal(
        loginRequestCount - loginCallsBeforeSingleFlight,
        1,
        "overlapping login submissions must share one backend request",
    );
    assert.equal(typeof resolveDeferredLogin, "function");
    resolveDeferredLogin();
    assert.deepEqual(await Promise.all([firstLogin, secondLogin]), [true, true]);
    assert.equal(storage.size, 1);

    hangLogout = true;
    const boundedLogout = sandbox.SocAuth.logout();
    assert.equal(storage.size, 0, "logout must clear local state before network completion");
    assert.equal(nodes["main-dashboard"].style.display, "none");
    const logoutTimeout = expiryHandler;
    assert.equal(typeof logoutTimeout, "function");
    logoutTimeout();
    assert.equal(await boundedLogout, true);

    hangLogout = false;
    deferNextLogin = true;
    nodes["login-user"].value = "analyst-one";
    nodes["login-pass"].value = "temporary-test-password";
    const timedLogin = sandbox.SocAuth.login();
    const loginTimeout = expiryHandler;
    assert.equal(typeof loginTimeout, "function");
    loginTimeout();
    assert.equal(await timedLogin, false);
    assert.equal(nodes["login-submit"].disabled, false);
    assert.equal(nodes["login-pass"].value, "");
    assert.equal(storage.size, 0);

    const diagnostics = sandbox.SocAuth.diagnostics();
    assert.ok(diagnostics.length > 0);
    assert.ok(diagnostics.length <= 100);
    assert.ok(diagnostics.some(row => row.event === "session.renewed"));
    assert.ok(diagnostics.some(row => row.reason === "timeout" && row.session_retained === true));
    assert.ok(diagnostics.some(row => row.reason === "server_rejected"));
    assert.ok(diagnostics.some(row => (
        row.reason === "invalid_json"
        && row.status === 200
        && row.request_id === "request-test-1234"
    )));
    assert.ok(diagnostics.some(row => row.request_id === "request-test-1234"));
    const serializedDiagnostics = JSON.stringify(diagnostics);
    assert.doesNotMatch(serializedDiagnostics, /temporary-test-password/);
    assert.doesNotMatch(serializedDiagnostics, /csrf-test-token/);
    assert.doesNotMatch(serializedDiagnostics, /analyst-one/);
    assert.doesNotMatch(serializedDiagnostics, /POISON-/);
    assert.doesNotMatch(serializedDiagnostics, /PRIVATE-AUTH-JSON-SENTINEL/);
    assert.ok(diagnostics.some(row => row.request_id === "poison-safe-id-1234"));
    assert.ok(diagnostics.every(row => !Object.hasOwn(row, "username")));
    assert.ok(diagnostics.every(row => !Object.hasOwn(row, "password")));
    assert.ok(diagnostics.every(row => !Object.hasOwn(row, "target")));

    console.log("auth_ui.test.cjs: all assertions passed");
}

main().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
