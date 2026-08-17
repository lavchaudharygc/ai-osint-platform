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
        async json() { return payload; },
    };
}

async function main() {
    assert.doesNotMatch(source, /testingaccount|uppolice/);

    const calls = [];
    const events = {};
    const dispatched = [];
    const storage = new Map();
    const expiresAt = new Date(Date.now() + 60 * 60 * 1000).toISOString();
    let expiryHandler = null;
    let meAuthenticated = false;
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
            meAuthenticated = true;
            return response(200, {
                user: "analyst-one",
                roles: ["investigator", "breach_pii_viewer"],
                csrf_token: "csrf-test-token",
                expires_at: expiresAt,
            });
        }
        if (String(url).endsWith("/logout")) return response(200, { status: "logged_out" });
        return response(200, { status: "ok" });
    }

    class FakeCustomEvent {
        constructor(type, init = {}) { this.type = type; this.detail = init.detail; }
    }

    const sandbox = {
        console,
        Headers,
        CustomEvent: FakeCustomEvent,
        fetch: fakeFetch,
        sessionStorage: {
            getItem(key) { return storage.has(key) ? storage.get(key) : null; },
            setItem(key, value) { storage.set(key, String(value)); },
            removeItem(key) { storage.delete(key); },
        },
        document: { getElementById(id) { return nodes[id] || null; } },
        location: { protocol: "http:", hostname: "127.0.0.1" },
        API_BASE: "http://127.0.0.1:8010",
        setTimeout(handler) { expiryHandler = handler; return 1; },
        clearTimeout() { expiryHandler = null; },
        addEventListener(type, handler) { events[type] = handler; },
        dispatchEvent(event) { dispatched.push(event); },
    };
    sandbox.window = sandbox;

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

    await sandbox.SocAuth.fetch("http://127.0.0.1:8010/api/v1/email-investigation", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
    });
    const protectedCall = calls.at(-1);
    assert.equal(protectedCall.options.credentials, "include");
    assert.equal(protectedCall.options.headers["x-csrf-token"], "csrf-test-token");
    assert.ok(dispatched.some(event => event.type === "soc:authenticated"));

    const scheduledExpiry = expiryHandler;
    assert.equal(typeof scheduledExpiry, "function");
    scheduledExpiry();
    assert.equal(storage.size, 0);
    assert.equal(nodes["main-dashboard"].style.display, "none");
    assert.ok(dispatched.some(event => event.type === "soc:unauthenticated"));

    nodes["login-user"].value = "analyst-one";
    nodes["login-pass"].value = "temporary-test-password";
    assert.equal(await sandbox.SocAuth.login(), true);
    await sandbox.SocAuth.logout();
    assert.equal(storage.size, 0);
    assert.equal(nodes["main-dashboard"].style.display, "none");

    console.log("auth_ui.test.cjs: all assertions passed");
}

main().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
