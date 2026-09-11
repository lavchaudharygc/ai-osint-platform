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
    const DIAGNOSTIC_KEY = "upp_soc_auth_diagnostics_v1";
    const DIAGNOSTIC_LIMIT = 100;
    const SAFE_ENDPOINTS = new Set([
        "auth_initialize",
        "auth_login",
        "auth_logout",
        "auth_refresh",
        "protected_request",
        "session_storage",
    ]);

    const SAFE_EVENTS = new Set([
        "auth.login_failed",
        "auth.login_rejected",
        "auth.login_succeeded",
        "auth.logout_finished",
        "protected.auth_challenge",
        "session.cleared",
        "session.initialize_failed",
        "session.initialize_ignored",
        "session.initialize_rejected",
        "session.initialize_retry",
        "session.initialized",
        "session.local_state_rejected",
        "session.refresh_ignored",
        "session.refresh_rejected",
        "session.refresh_retry",
        "session.renewed",
    ]);

    const SAFE_REASONS = new Set([
        "backend_timeout",
        "backend_unavailable",
        "credentials_accepted",
        "feature_auth_status",
        "http_error",
        "http_rejected",
        "initial_session_rejected",
        "invalid_json",
        "invalid_local_state",
        "invalid_session_payload",
        "keepalive_success",
        "local_expired",
        "login_network_error",
        "login_rejected",
        "login_timeout",
        "manual_clear",
        "missing_csrf",
        "network_error",
        "operator_logout",
        "server_error",
        "server_rejected",
        "server_session_valid",
        "stale_operation",
        "storage_error",
        "success",
        "timeout",
        "unexpected_client_error",
    ]);

    function sanitizeDiagnosticRow(value) {
        if (!value || typeof value !== "object" || Array.isArray(value)) return null;
        const at = String(value.at || "");
        const timestamp = Date.parse(at);
        if (
            !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(at)
            || !Number.isFinite(timestamp)
            || timestamp > Date.now() + 5 * 60 * 1000
        ) return null;
        const event = String(value.event || "");
        if (!SAFE_EVENTS.has(event)) return null;

        const row = { at, event };
        if (SAFE_ENDPOINTS.has(value.endpoint)) row.endpoint = value.endpoint;
        if (SAFE_REASONS.has(value.reason)) row.reason = value.reason;
        if (Number.isInteger(value.status) && value.status >= 100 && value.status <= 599) {
            row.status = value.status;
        }
        for (const key of ["duration_ms", "retry_ms"]) {
            if (typeof value[key] === "number" && Number.isFinite(value[key]) && value[key] >= 0) {
                row[key] = Math.min(3_600_000, Math.round(value[key]));
            }
        }
        if (typeof value.session_retained === "boolean") {
            row.session_retained = value.session_retained;
        }
        if (/^[A-Za-z0-9_-]{8,64}$/.test(String(value.request_id || ""))) {
            row.request_id = String(value.request_id);
        }
        return row;
    }

    function parseDiagnostics(serialized) {
        try {
            const parsed = JSON.parse(serialized || "[]");
            if (!Array.isArray(parsed)) return [];
            return parsed
                .map(sanitizeDiagnosticRow)
                .filter(Boolean)
                .slice(-DIAGNOSTIC_LIMIT);
        } catch (_error) {
            return [];
        }
    }

    function readDiagnostics() {
        try {
            return parseDiagnostics(window.localStorage?.getItem(DIAGNOSTIC_KEY));
        } catch (_error) {
            return [];
        }
    }

    function mergeDiagnostics(...collections) {
        const unique = new Map();
        for (const collection of collections) {
            for (const candidate of Array.isArray(collection) ? collection : []) {
                const row = sanitizeDiagnosticRow(candidate);
                if (!row) continue;
                unique.set(JSON.stringify(row), row);
            }
        }
        return [...unique.values()]
            .sort((left, right) => left.at.localeCompare(right.at))
            .slice(-DIAGNOSTIC_LIMIT);
    }

    let diagnosticEvents = readDiagnostics();

    function safeRequestId(response) {
        try {
            const value = String(response?.headers?.get?.("x-request-id") || "");
            return /^[A-Za-z0-9_-]{8,64}$/.test(value) ? value : "";
        } catch (_error) {
            return "";
        }
    }

    function recordDiagnostic(event, level = "debug", fields = {}) {
        const row = sanitizeDiagnosticRow({
            at: new Date().toISOString(),
            event: String(event || ""),
            ...fields,
        });
        if (!row) return;
        // Re-read before every write so another tab's event is not routinely
        // replaced by this tab's older in-memory snapshot.
        diagnosticEvents = mergeDiagnostics(readDiagnostics(), diagnosticEvents, [row]);
        try {
            window.localStorage?.setItem(DIAGNOSTIC_KEY, JSON.stringify(diagnosticEvents));
        } catch (_error) {
            // In-memory diagnostics still work when browser storage is blocked.
        }
        const method = level === "warn" ? "warn" : "debug";
        try {
            window.console?.[method]?.("[SOC diagnostic]", { ...row });
        } catch (_error) {
            // Diagnostics must never interfere with authentication.
        }
    }

    function listDiagnostics() {
        return diagnosticEvents.map(row => ({ ...row }));
    }

    function clearDiagnostics() {
        diagnosticEvents = [];
        try {
            window.localStorage?.removeItem(DIAGNOSTIC_KEY);
        } catch (_error) {
            // The in-memory list was still cleared.
        }
    }

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
                recordDiagnostic("session.local_state_rejected", "warn", {
                    endpoint: "session_storage",
                    reason: Number.isFinite(expiry) && expiry <= Date.now()
                        ? "local_expired"
                        : "invalid_local_state",
                    session_retained: false,
                });
                return null;
            }
            return { username, roles, csrfToken, expiresAt };
        } catch (_error) {
            recordDiagnostic("session.local_state_rejected", "warn", {
                endpoint: "session_storage",
                reason: "storage_error",
                session_retained: false,
            });
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
            clearSession("Your authenticated session expired. Sign in again.", "local_expired");
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

    function clearSession(message = "", reason = "manual_clear") {
        cancelKeepaliveTimer();
        session = null;
        sessionRevision += 1;
        sessionStorage.removeItem(SESSION_KEY);
        updateShell(false, message);
        window.dispatchEvent(new CustomEvent("soc:unauthenticated"));
        recordDiagnostic("session.cleared", reason === "operator_logout" ? "debug" : "warn", {
            endpoint: "session_storage",
            reason,
            session_retained: false,
        });
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
        let timedOut = false;
        let failureReason = "network_error";
        let lastResponse = null;
        const startedAt = Date.now();
        cancelKeepaliveTimer();
        refreshPromise = (async () => {
            try {
                const timeout = new Promise((_, reject) => {
                    timeoutId = window.setTimeout(() => {
                        timedOut = true;
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
                    lastResponse = response;
                    let payload = null;
                    if (response.ok) {
                        failureReason = "invalid_json";
                        payload = await response.json();
                    }
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
                    ) {
                        recordDiagnostic("session.refresh_ignored", "debug", {
                            endpoint: "auth_refresh",
                            reason: "stale_operation",
                            status: response.status,
                            duration_ms: Date.now() - startedAt,
                            session_retained: Boolean(session),
                            request_id: safeRequestId(response),
                        });
                        return false;
                    }
                    failureReason = "invalid_session_payload";
                    persistSession(payload);
                    recordDiagnostic("session.renewed", "debug", {
                        endpoint: "auth_refresh",
                        reason: "keepalive_success",
                        status: response.status,
                        duration_ms: Date.now() - startedAt,
                        session_retained: true,
                        request_id: safeRequestId(response),
                    });
                    return true;
                }
                if (response.status === 401 || response.status === 419) {
                    recordDiagnostic("session.refresh_rejected", "warn", {
                        endpoint: "auth_refresh",
                        reason: "server_rejected",
                        status: response.status,
                        duration_ms: Date.now() - startedAt,
                        session_retained: false,
                        request_id: safeRequestId(response),
                    });
                    if (
                        session === sessionAtStart
                        && sessionRevision === revisionAtStart
                        && !logoutInProgress
                    ) {
                        clearSession(
                            "Your authenticated session is no longer valid. Sign in again.",
                            "server_rejected",
                        );
                    }
                    return false;
                }
                if (
                    session === sessionAtStart
                    && sessionRevision === revisionAtStart
                    && !logoutInProgress
                ) {
                    recordDiagnostic("session.refresh_retry", "warn", {
                        endpoint: "auth_refresh",
                        reason: "http_error",
                        status: response.status,
                        duration_ms: Date.now() - startedAt,
                        retry_ms: KEEPALIVE_RETRY_MS,
                        session_retained: true,
                        request_id: safeRequestId(response),
                    });
                    scheduleSessionRefresh(KEEPALIVE_RETRY_MS);
                }
                return false;
            } catch (_error) {
                // A temporary backend/network failure is not proof that the
                // operator's session ended. Keep the dashboard and retry.
                if (
                    session === sessionAtStart
                    && sessionRevision === revisionAtStart
                    && !logoutInProgress
                ) {
                    recordDiagnostic("session.refresh_retry", "warn", {
                        endpoint: "auth_refresh",
                        reason: timedOut ? "timeout" : failureReason,
                        status: lastResponse?.status,
                        duration_ms: Date.now() - startedAt,
                        retry_ms: KEEPALIVE_RETRY_MS,
                        session_retained: true,
                        request_id: safeRequestId(lastResponse),
                    });
                    scheduleSessionRefresh(KEEPALIVE_RETRY_MS);
                }
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
        let failureReason = "network_error";
        let lastResponse = null;
        const startedAt = Date.now();
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
                lastResponse = response;
                let payload = null;
                if (response.ok) {
                    failureReason = "invalid_json";
                    payload = await response.json();
                }
                return { response, payload };
            })();
            const { response, payload } = await Promise.race([request, timeout]);
            if (sessionRevision !== revisionAtStart) {
                recordDiagnostic("session.initialize_ignored", "debug", {
                    endpoint: "auth_initialize",
                    reason: "stale_operation",
                    status: response.status,
                    duration_ms: Date.now() - startedAt,
                    session_retained: Boolean(session),
                    request_id: safeRequestId(response),
                });
                return Boolean(session);
            }
            if (!response.ok) {
                if (response.status === 401 || response.status === 419) {
                    recordDiagnostic("session.initialize_rejected", "warn", {
                        endpoint: "auth_initialize",
                        reason: "server_rejected",
                        status: response.status,
                        duration_ms: Date.now() - startedAt,
                        session_retained: false,
                        request_id: safeRequestId(response),
                    });
                    clearSession("", "initial_session_rejected");
                } else if (session && enforceSessionDeadline()) {
                    updateShell(true);
                    cancelKeepaliveTimer();
                    recordDiagnostic("session.initialize_retry", "warn", {
                        endpoint: "auth_initialize",
                        reason: "http_error",
                        status: response.status,
                        duration_ms: Date.now() - startedAt,
                        retry_ms: KEEPALIVE_RETRY_MS,
                        session_retained: true,
                        request_id: safeRequestId(response),
                    });
                    scheduleSessionRefresh(KEEPALIVE_RETRY_MS);
                } else {
                    recordDiagnostic("session.initialize_failed", "warn", {
                        endpoint: "auth_initialize",
                        reason: "http_error",
                        status: response.status,
                        duration_ms: Date.now() - startedAt,
                        session_retained: false,
                        request_id: safeRequestId(response),
                    });
                    clearSession(
                        "Authentication service is unavailable. Start the Beta-v2 backend and try again.",
                        "backend_unavailable",
                    );
                }
                return false;
            }
            if (sessionRevision !== revisionAtStart) {
                recordDiagnostic("session.initialize_ignored", "debug", {
                    endpoint: "auth_initialize",
                    reason: "stale_operation",
                    status: response.status,
                    duration_ms: Date.now() - startedAt,
                    session_retained: Boolean(session),
                    request_id: safeRequestId(response),
                });
                return Boolean(session);
            }
            failureReason = "invalid_session_payload";
            persistSession(payload);
            recordDiagnostic("session.initialized", "debug", {
                endpoint: "auth_initialize",
                reason: "server_session_valid",
                status: response.status,
                duration_ms: Date.now() - startedAt,
                session_retained: true,
                request_id: safeRequestId(response),
            });
            return true;
        } catch (_error) {
            if (controller?.signal.aborted && !timedOut) return Boolean(session);
            if (sessionRevision !== revisionAtStart) return Boolean(session);
            if (session && enforceSessionDeadline()) {
                updateShell(true);
                cancelKeepaliveTimer();
                recordDiagnostic("session.initialize_retry", "warn", {
                    endpoint: "auth_initialize",
                    reason: timedOut ? "timeout" : failureReason,
                    status: lastResponse?.status,
                    duration_ms: Date.now() - startedAt,
                    retry_ms: KEEPALIVE_RETRY_MS,
                    session_retained: true,
                    request_id: safeRequestId(lastResponse),
                });
                scheduleSessionRefresh(KEEPALIVE_RETRY_MS);
            } else {
                const reason = timedOut ? "timeout" : failureReason;
                recordDiagnostic("session.initialize_failed", "warn", {
                    endpoint: "auth_initialize",
                    reason,
                    status: lastResponse?.status,
                    duration_ms: Date.now() - startedAt,
                    session_retained: false,
                    request_id: safeRequestId(lastResponse),
                });
                clearSession(
                    "Authentication service is unavailable. Start the Beta-v2 backend and try again.",
                    timedOut
                        ? "backend_timeout"
                        : (failureReason === "network_error" ? "backend_unavailable" : failureReason),
                );
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
        let failureReason = "network_error";
        let lastResponse = null;
        const startedAt = Date.now();
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
                lastResponse = response;
                if (!response.ok) {
                    const message = await responseMessage(
                        response,
                        "Invalid credentials or account unavailable.",
                    );
                    return { response, message, payload: null };
                }
                failureReason = "invalid_json";
                return { response, message: "", payload: await response.json() };
            })();
            const { response, message, payload } = await Promise.race([request, timeout]);
            if (!response.ok) {
                if (sessionRevision !== revisionForLogin || logoutInProgress) return false;
                recordDiagnostic("auth.login_rejected", "warn", {
                    endpoint: "auth_login",
                    reason: "http_rejected",
                    status: response.status,
                    duration_ms: Date.now() - startedAt,
                    session_retained: false,
                    request_id: safeRequestId(response),
                });
                clearSession(message, "login_rejected");
                return false;
            }
            if (sessionRevision !== revisionForLogin || logoutInProgress) return false;
            failureReason = "invalid_session_payload";
            persistSession(payload);
            recordDiagnostic("auth.login_succeeded", "debug", {
                endpoint: "auth_login",
                reason: "credentials_accepted",
                status: response.status,
                duration_ms: Date.now() - startedAt,
                session_retained: true,
                request_id: safeRequestId(response),
            });
            return true;
        } catch (_error) {
            if (controller?.signal.aborted && !timedOut) return false;
            if (sessionRevision !== revisionForLogin || logoutInProgress) return false;
            recordDiagnostic("auth.login_failed", "warn", {
                endpoint: "auth_login",
                reason: timedOut ? "timeout" : failureReason,
                status: lastResponse?.status,
                duration_ms: Date.now() - startedAt,
                session_retained: false,
                request_id: safeRequestId(lastResponse),
            });
            clearSession(
                "Authentication service is unavailable. Start the Beta-v2 backend and try again.",
                timedOut
                    ? "login_timeout"
                    : (failureReason === "network_error" ? "login_network_error" : failureReason),
            );
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
                clearSession(
                    "Your authenticated session is missing its CSRF proof. Sign in again.",
                    "missing_csrf",
                );
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
            recordDiagnostic("protected.auth_challenge", "warn", {
                endpoint: "protected_request",
                reason: "feature_auth_status",
                status: response.status,
                session_retained: Boolean(session),
                request_id: safeRequestId(response),
            });
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
        clearSession("", "operator_logout");
        if (!csrfToken) {
            logoutInProgress = false;
            return true;
        }

        const controller = makeAbortController();
        let timeoutId = null;
        const startedAt = Date.now();
        try {
            const timeout = new Promise(resolve => {
                timeoutId = window.setTimeout(() => {
                    controller?.abort("logout_timeout");
                    resolve({ response: null, reason: "timeout" });
                }, LOGOUT_TIMEOUT_MS);
            });
            const outcome = await Promise.race([
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
                }).then(response => ({
                    response,
                    reason: response.ok
                        ? "success"
                        : (response.status >= 500 ? "server_error" : "http_rejected"),
                }))
                    .catch(() => ({ response: null, reason: "network_error" })),
                timeout,
            ]);
            recordDiagnostic("auth.logout_finished", outcome.response?.ok ? "debug" : "warn", {
                endpoint: "auth_logout",
                reason: outcome.reason,
                status: outcome.response?.status,
                duration_ms: Date.now() - startedAt,
                session_retained: false,
                request_id: safeRequestId(outcome.response),
            });
        } catch (_error) {
            // Local state was already cleared; the request is best-effort.
            recordDiagnostic("auth.logout_finished", "warn", {
                endpoint: "auth_logout",
                reason: "unexpected_client_error",
                duration_ms: Date.now() - startedAt,
                session_retained: false,
            });
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
        diagnostics: listDiagnostics,
        clearDiagnostics,
    };

    document.addEventListener?.("visibilitychange", () => {
        if (document.visibilityState === "visible" && session) void refreshSession();
    });
    window.addEventListener("focus", () => {
        if (session) void refreshSession();
    });
    window.addEventListener("storage", event => {
        if (event?.key !== DIAGNOSTIC_KEY) return;
        if (event.newValue === null) {
            diagnosticEvents = [];
            return;
        }
        diagnosticEvents = mergeDiagnostics(
            diagnosticEvents,
            parseDiagnostics(event.newValue),
        );
    });
    window.addEventListener("DOMContentLoaded", initialize);
})();
