/**
 * Backend-authenticated SOC session client.
 *
 * The signed session remains in an HttpOnly cookie. JavaScript keeps only the
 * CSRF token and the server-returned analyst identity for this browser tab.
 */
(function () {
    "use strict";

    const AUTH_API_BASE = window.API_BASE
        || (window.location.hostname
            ? `${window.location.protocol}//${window.location.hostname}:8010`
            : "http://127.0.0.1:8010");
    const AUTH_BASE = `${AUTH_API_BASE}/api/v1/auth`;
    const SESSION_KEY = "upp_soc_server_session";

    let session = readSession();
    let expiryTimer = null;

    function readSession() {
        try {
            const parsed = JSON.parse(sessionStorage.getItem(SESSION_KEY) || "null");
            if (!parsed || typeof parsed !== "object") return null;
            const username = typeof parsed.username === "string" ? parsed.username : "";
            const roles = Array.isArray(parsed.roles)
                ? parsed.roles.filter(role => typeof role === "string").slice(0, 20)
                : [];
            const csrfToken = typeof parsed.csrfToken === "string" ? parsed.csrfToken : "";
            const expiresAt = String(parsed.expiresAt || "");
            const expiry = Date.parse(expiresAt);
            if (!username || !csrfToken || !Number.isFinite(expiry) || expiry <= Date.now()) {
                sessionStorage.removeItem(SESSION_KEY);
                return null;
            }
            return { username, roles, csrfToken, expiresAt };
        } catch (_error) {
            return null;
        }
    }

    function publicSession() {
        return session
            ? { username: session.username, roles: [...session.roles], expiresAt: session.expiresAt }
            : null;
    }

    function cancelExpiryTimer() {
        if (expiryTimer !== null) window.clearTimeout(expiryTimer);
        expiryTimer = null;
    }

    function enforceSessionDeadline() {
        if (!session) return true;
        const expiry = Date.parse(session.expiresAt);
        if (!Number.isFinite(expiry) || expiry <= Date.now()) {
            clearSession("Your authenticated session expired. Sign in again.");
            return false;
        }
        cancelExpiryTimer();
        expiryTimer = window.setTimeout(
            () => clearSession("Your authenticated session expired. Sign in again."),
            Math.max(1, Math.min(expiry - Date.now(), 2_147_000_000)),
        );
        return true;
    }

    function updateShell(authenticated, message = "") {
        const login = document.getElementById("login-screen");
        const dashboard = document.getElementById("main-dashboard");
        const error = document.getElementById("login-error");
        const identity = document.getElementById("soc-authenticated-user");
        if (login) login.style.display = authenticated ? "none" : "flex";
        if (dashboard) dashboard.style.display = authenticated ? "block" : "none";
        if (error) {
            error.textContent = message || "Authentication failed. Check the server configuration and credentials.";
            error.style.display = !authenticated && message ? "block" : "none";
        }
        if (identity) {
            identity.textContent = authenticated && session
                ? `${session.username} · ${session.roles.join(", ") || "no roles"}`
                : "";
            identity.style.display = authenticated ? "inline-flex" : "none";
        }
        if (!authenticated) document.getElementById("login-user")?.focus();
    }

    function persistSession(payload) {
        const user = payload && typeof payload.user === "object" ? payload.user : {};
        const rolesValue = user.roles || payload?.roles;
        const usernameValue = typeof payload?.user === "string"
            ? payload.user
            : (user.username || payload?.username);
        const next = {
            username: String(usernameValue || "").slice(0, 128),
            roles: Array.isArray(rolesValue)
                ? rolesValue.filter(role => typeof role === "string").slice(0, 20)
                : [],
            csrfToken: String(payload?.csrf_token || "").slice(0, 256),
            expiresAt: String(payload?.expires_at || "").slice(0, 80),
        };
        const expiry = Date.parse(next.expiresAt);
        if (!next.username || !next.csrfToken || !Number.isFinite(expiry) || expiry <= Date.now()) {
            throw new Error("Authentication response was incomplete or expired.");
        }
        session = next;
        sessionStorage.setItem(SESSION_KEY, JSON.stringify(next));
        enforceSessionDeadline();
        updateShell(true);
        window.dispatchEvent(new CustomEvent("soc:authenticated", { detail: publicSession() }));
    }

    function clearSession(message = "") {
        cancelExpiryTimer();
        session = null;
        sessionStorage.removeItem(SESSION_KEY);
        updateShell(false, message);
        window.dispatchEvent(new CustomEvent("soc:unauthenticated"));
    }

    async function responseMessage(response, fallback) {
        try {
            const payload = await response.json();
            return typeof payload.detail === "string" ? payload.detail : fallback;
        } catch (_error) {
            return fallback;
        }
    }

    async function initialize() {
        try {
            const response = await fetch(`${AUTH_BASE}/me`, {
                method: "GET",
                credentials: "include",
                cache: "no-store",
                headers: { "Accept": "application/json" },
            });
            if (!response.ok) {
                clearSession("");
                return false;
            }
            persistSession(await response.json());
            return true;
        } catch (_error) {
            clearSession("Authentication service is unavailable. Start the Beta-v2 backend and try again.");
            return false;
        }
    }

    async function login() {
        const usernameInput = document.getElementById("login-user");
        const passwordInput = document.getElementById("login-pass");
        const button = document.getElementById("login-submit");
        const username = String(usernameInput?.value || "").trim();
        const password = String(passwordInput?.value || "");
        if (!username || !password) {
            updateShell(false, "Enter the backend-issued analyst username and password.");
            return false;
        }
        if (button) {
            button.disabled = true;
            button.textContent = "AUTHENTICATING...";
        }
        try {
            const response = await fetch(`${AUTH_BASE}/login`, {
                method: "POST",
                credentials: "include",
                cache: "no-store",
                headers: { "Accept": "application/json", "Content-Type": "application/json" },
                body: JSON.stringify({ username, password }),
            });
            if (!response.ok) {
                clearSession(await responseMessage(response, "Invalid credentials or account unavailable."));
                return false;
            }
            persistSession(await response.json());
            return true;
        } catch (_error) {
            clearSession("Authentication service is unavailable. Start the Beta-v2 backend and try again.");
            return false;
        } finally {
            if (passwordInput) passwordInput.value = "";
            if (button) {
                button.disabled = false;
                button.textContent = "AUTHENTICATE & ENTER SOC";
            }
        }
    }

    async function authenticatedFetch(url, options = {}, redirectOnAuthFailure = true) {
        if (!enforceSessionDeadline()) {
            throw new Error("Authenticated session expired.");
        }
        const method = String(options.method || "GET").toUpperCase();
        const headers = new Headers(options.headers || {});
        if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
            if (!session?.csrfToken) {
                clearSession("Your authenticated session is missing its CSRF proof. Sign in again.");
                throw new Error("Authenticated session required.");
            }
            headers.set("X-CSRF-Token", session.csrfToken);
        }
        const response = await fetch(url, {
            ...options,
            method,
            headers,
            credentials: "include",
            cache: options.cache || "no-store",
        });
        if (redirectOnAuthFailure && (response.status === 401 || response.status === 419)) {
            clearSession("Your authenticated session expired. Sign in again.");
        }
        return response;
    }

    async function logout() {
        try {
            await authenticatedFetch(`${AUTH_BASE}/logout`, { method: "POST" }, false);
        } catch (_error) {
            // Local session is cleared even when the backend is unavailable.
        }
        clearSession("");
    }

    function hasRole(role) {
        return Boolean(session?.roles.includes(role));
    }

    window.SocAuth = {
        initialize,
        login,
        logout,
        fetch: authenticatedFetch,
        hasRole,
        session: publicSession,
        clear: clearSession,
    };

    document.addEventListener?.("visibilitychange", () => {
        if (document.visibilityState === "visible") enforceSessionDeadline();
    });
    window.addEventListener("focus", enforceSessionDeadline);
    window.addEventListener("DOMContentLoaded", initialize);
})();
