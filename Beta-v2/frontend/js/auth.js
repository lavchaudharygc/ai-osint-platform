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
    const KEEPALIVE_INTERVAL_MS = 5 * 60 * 1000;
    const KEEPALIVE_RETRY_MS = 30 * 1000;
    const SESSION_REQUEST_TIMEOUT_MS = 10 * 1000;
    const LOGOUT_TIMEOUT_MS = 5 * 1000;
    const MAX_TIMER_DELAY_MS = 2_147_000_000;

    let session = readSession();
    let keepaliveTimer = null;
    let refreshPromise = null;
    let refreshController = null;
    let initializeController = null;
    let loginPromise = null;
    let loginController = null;
    let logoutInProgress = false;
    let sessionRevision = 0;

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

    function makeAbortController() {
        const Controller = window.AbortController
            || (typeof AbortController !== "undefined" ? AbortController : null);
        return Controller ? new Controller() : null;
    }

    function cancelKeepaliveTimer() {
        if (keepaliveTimer !== null) window.clearTimeout(keepaliveTimer);
        keepaliveTimer = null;
    }

    function scheduleSessionRefresh(requestedDelay = null) {
        if (!session || keepaliveTimer !== null) return;
        const expiry = Date.parse(session.expiresAt);
        const remaining = expiry - Date.now();
        if (!Number.isFinite(expiry) || remaining <= 0) return;
        const normalDelay = Math.min(KEEPALIVE_INTERVAL_MS, Math.max(1, Math.floor(remaining / 2)));
        const delay = Number.isFinite(requestedDelay)
            ? Math.min(Math.max(1, requestedDelay), normalDelay)
            : normalDelay;
        keepaliveTimer = window.setTimeout(() => {
            keepaliveTimer = null;
            return refreshSession();
        }, Math.min(delay, MAX_TIMER_DELAY_MS));
    }

    function enforceSessionDeadline() {
        if (!session) return true;
        const expiry = Date.parse(session.expiresAt);
        if (!Number.isFinite(expiry) || expiry <= Date.now()) {
            clearSession("Your authenticated session expired. Sign in again.");
            return false;
        }
        scheduleSessionRefresh();
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
        sessionRevision += 1;
        sessionStorage.setItem(SESSION_KEY, JSON.stringify(next));
        cancelKeepaliveTimer();
        scheduleSessionRefresh();
        updateShell(true);
        window.dispatchEvent(new CustomEvent("soc:authenticated", { detail: publicSession() }));
    }

    function clearSession(message = "") {
        cancelKeepaliveTimer();
        session = null;
        sessionRevision += 1;
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

    async function refreshSession() {
        if (!session || logoutInProgress) return false;
        if (refreshPromise) return refreshPromise;
        const sessionAtStart = session;
        const revisionAtStart = sessionRevision;
        const controller = makeAbortController();
        refreshController = controller;
        let timeoutId = null;
        cancelKeepaliveTimer();
        refreshPromise = (async () => {
            try {
                const timeout = new Promise((_, reject) => {
                    timeoutId = window.setTimeout(() => {
                        controller?.abort("session_refresh_timeout");
                        reject(new Error("Session refresh timed out"));
                    }, SESSION_REQUEST_TIMEOUT_MS);
                });
                const request = (async () => {
                    const response = await fetch(`${AUTH_BASE}/me`, {
                        method: "GET",
                        credentials: "include",
                        cache: "no-store",
                        headers: { "Accept": "application/json" },
                        ...(controller ? { signal: controller.signal } : {}),
                    });
                    const payload = response.ok ? await response.json() : null;
                    return { response, payload };
                })();
                const { response, payload } = await Promise.race([
                    request,
                    timeout,
                ]);
                if (response.ok) {
                    if (
                        logoutInProgress
                        || session !== sessionAtStart
                        || sessionRevision !== revisionAtStart
                    ) return false;
                    persistSession(payload);
                    return true;
                }
                if (response.status === 401 || response.status === 419) {
                    if (
                        session === sessionAtStart
                        && sessionRevision === revisionAtStart
                        && !logoutInProgress
                    ) {
                        clearSession("Your authenticated session is no longer valid. Sign in again.");
                    }
                    return false;
                }
                if (
                    session === sessionAtStart
                    && sessionRevision === revisionAtStart
                    && !logoutInProgress
                ) scheduleSessionRefresh(KEEPALIVE_RETRY_MS);
                return false;
            } catch (_error) {
                // A temporary backend/network failure is not proof that the
                // operator's session ended. Keep the dashboard and retry.
                if (
                    session === sessionAtStart
                    && sessionRevision === revisionAtStart
                    && !logoutInProgress
                ) scheduleSessionRefresh(KEEPALIVE_RETRY_MS);
                return false;
            } finally {
                if (timeoutId !== null) window.clearTimeout(timeoutId);
                if (refreshController === controller) refreshController = null;
                refreshPromise = null;
            }
        })();
        return refreshPromise;
    }

    async function initialize() {
        const revisionAtStart = sessionRevision;
        initializeController?.abort("superseded");
        const controller = makeAbortController();
        initializeController = controller;
        let timeoutId = null;
        let timedOut = false;
        try {
            const timeout = new Promise((_, reject) => {
                timeoutId = window.setTimeout(() => {
                    timedOut = true;
                    controller?.abort("session_initialize_timeout");
                    reject(new Error("Session initialization timed out"));
                }, SESSION_REQUEST_TIMEOUT_MS);
            });
            const request = (async () => {
                const response = await fetch(`${AUTH_BASE}/me`, {
                    method: "GET",
                    credentials: "include",
                    cache: "no-store",
                    headers: { "Accept": "application/json" },
                    ...(controller ? { signal: controller.signal } : {}),
                });
                const payload = response.ok ? await response.json() : null;
                return { response, payload };
            })();
            const { response, payload } = await Promise.race([request, timeout]);
            if (sessionRevision !== revisionAtStart) return Boolean(session);
            if (!response.ok) {
                if (response.status === 401 || response.status === 419) {
                    clearSession("");
                } else if (session && enforceSessionDeadline()) {
                    updateShell(true);
                    cancelKeepaliveTimer();
                    scheduleSessionRefresh(KEEPALIVE_RETRY_MS);
                } else {
                    clearSession("Authentication service is unavailable. Start the Beta-v2 backend and try again.");
                }
                return false;
            }
            if (sessionRevision !== revisionAtStart) return Boolean(session);
            persistSession(payload);
            return true;
        } catch (_error) {
            if (controller?.signal.aborted && !timedOut) return Boolean(session);
            if (sessionRevision !== revisionAtStart) return Boolean(session);
            if (session && enforceSessionDeadline()) {
                updateShell(true);
                cancelKeepaliveTimer();
                scheduleSessionRefresh(KEEPALIVE_RETRY_MS);
            } else {
                clearSession("Authentication service is unavailable. Start the Beta-v2 backend and try again.");
            }
            return false;
        } finally {
            if (timeoutId !== null) window.clearTimeout(timeoutId);
            if (initializeController === controller) initializeController = null;
        }
    }

    async function performLogin() {
        const usernameInput = document.getElementById("login-user");
        const passwordInput = document.getElementById("login-pass");
        const button = document.getElementById("login-submit");
        const username = String(usernameInput?.value || "").trim();
        const password = String(passwordInput?.value || "");
        if (!username || !password) {
            updateShell(false, "Enter the backend-issued analyst username and password.");
            return false;
        }
        sessionRevision += 1;
        const revisionForLogin = sessionRevision;
        cancelKeepaliveTimer();
        initializeController?.abort("login_started");
        refreshController?.abort("login_started");
        const controller = makeAbortController();
        loginController = controller;
        let timeoutId = null;
        let timedOut = false;
        if (button) {
            button.disabled = true;
            button.textContent = "AUTHENTICATING...";
        }
        try {
            const timeout = new Promise((_, reject) => {
                timeoutId = window.setTimeout(() => {
                    timedOut = true;
                    controller?.abort("login_timeout");
                    reject(new Error("Login timed out"));
                }, SESSION_REQUEST_TIMEOUT_MS);
            });
            const request = (async () => {
                const response = await fetch(`${AUTH_BASE}/login`, {
                    method: "POST",
                    credentials: "include",
                    cache: "no-store",
                    headers: { "Accept": "application/json", "Content-Type": "application/json" },
                    body: JSON.stringify({ username, password }),
                    ...(controller ? { signal: controller.signal } : {}),
                });
                if (!response.ok) {
                    const message = await responseMessage(
                        response,
                        "Invalid credentials or account unavailable.",
                    );
                    return { response, message, payload: null };
                }
                return { response, message: "", payload: await response.json() };
            })();
            const { response, message, payload } = await Promise.race([request, timeout]);
            if (!response.ok) {
                if (sessionRevision !== revisionForLogin || logoutInProgress) return false;
                clearSession(message);
                return false;
            }
            if (sessionRevision !== revisionForLogin || logoutInProgress) return false;
            persistSession(payload);
            return true;
        } catch (_error) {
            if (controller?.signal.aborted && !timedOut) return false;
            if (sessionRevision !== revisionForLogin || logoutInProgress) return false;
            clearSession("Authentication service is unavailable. Start the Beta-v2 backend and try again.");
            return false;
        } finally {
            if (timeoutId !== null) window.clearTimeout(timeoutId);
            if (loginController === controller) loginController = null;
            if (passwordInput) passwordInput.value = "";
            if (button) {
                button.disabled = false;
                button.textContent = "AUTHENTICATE & ENTER SOC";
            }
        }
    }

    async function login() {
        if (loginPromise) return loginPromise;
        if (logoutInProgress) return false;
        const operation = performLogin();
        loginPromise = operation;
        try {
            return await operation;
        } finally {
            if (loginPromise === operation) loginPromise = null;
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
            // A collector/provider may report its own 401. Confirm the actual
            // SOC cookie with /auth/me before changing the operator's shell.
            await refreshSession();
        }
        return response;
    }

    async function logout() {
        if (logoutInProgress) return false;
        logoutInProgress = true;
        const csrfToken = session?.csrfToken || "";
        initializeController?.abort("logout");
        refreshController?.abort("logout");
        loginController?.abort("logout");
        clearSession("");
        if (!csrfToken) {
            logoutInProgress = false;
            return true;
        }

        const controller = makeAbortController();
        let timeoutId = null;
        try {
            const timeout = new Promise(resolve => {
                timeoutId = window.setTimeout(() => {
                    controller?.abort("logout_timeout");
                    resolve(null);
                }, LOGOUT_TIMEOUT_MS);
            });
            await Promise.race([
                fetch(`${AUTH_BASE}/logout`, {
                    method: "POST",
                    credentials: "include",
                    cache: "no-store",
                    keepalive: true,
                    headers: {
                        "Accept": "application/json",
                        "X-CSRF-Token": csrfToken,
                    },
                    ...(controller ? { signal: controller.signal } : {}),
                }).catch(() => null),
                timeout,
            ]);
        } catch (_error) {
            // Local state was already cleared; the request is best-effort.
        } finally {
            if (timeoutId !== null) window.clearTimeout(timeoutId);
            logoutInProgress = false;
        }
        return true;
    }

    function hasRole(role) {
        return Boolean(session?.roles.includes(role));
    }

    window.SocAuth = {
        initialize,
        login,
        logout,
        fetch: authenticatedFetch,
        refresh: refreshSession,
        hasRole,
        session: publicSession,
        clear: clearSession,
    };

    document.addEventListener?.("visibilitychange", () => {
        if (document.visibilityState === "visible" && session) void refreshSession();
    });
    window.addEventListener("focus", () => {
        if (session) void refreshSession();
    });
    window.addEventListener("DOMContentLoaded", initialize);
})();
