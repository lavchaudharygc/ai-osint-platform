/**
 * Phone Investigation UI Module for Beta-v2.
 */
(function () {
    "use strict";

    const PHONE_API_BASE = typeof API_BASE !== "undefined"
        ? API_BASE
        : (window.API_BASE || "http://127.0.0.1:8010");
    const PHONE_ENDPOINT = `${PHONE_API_BASE}/api/v1/phone-investigation`;
    const REQUEST_TIMEOUT_MS = 60000;
    const CASE_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_.:/-]{2,63}$/;
    const REASON_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_.:\- ]{1,63}$/;

    let currentPhoneResult = null;
    let activeController = null;
    let requestSerial = 0;

    function el(id) {
        return document.getElementById(id);
    }

    function escapeHTML(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function stringValue(value, fallback = "") {
        if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
            return String(value);
        }
        return fallback;
    }

    function inspectPhoneSyntax(value) {
        const raw = stringValue(value).strip ? stringValue(value).strip() : stringValue(value).trim();
        if (!raw) return { empty: True, valid: False, message: "Enter a target phone number." };
        const cleaned = raw.replace(/[^\d+]/g, "");
        if (cleaned.length < 5 || cleaned.length > 20) {
            return { empty: False, valid: False, message: "Phone number must contain 5 to 20 digits." };
        }
        return { empty: False, valid: True, message: "Phone syntax format valid." };
    }

    function renderKeyValueGrid(items) {
        const rows = items.filter(item => item && item.value !== undefined && item.value !== null && item.value !== "");
        if (!rows.length) return '<div class="email-empty-state">No properties reported.</div>';
        return `
            <div class="email-kv-grid">
                ${rows.map(item => `
                    <div class="email-kv-item">
                        <span class="email-kv-label">${escapeHTML(item.label)}</span>
                        <span class="email-kv-value">${escapeHTML(item.value)}</span>
                    </div>
                `).join("")}
            </div>
        `;
    }

    function setSyntaxIndicator(inspection) {
        const badge = el("phone-syntax-badge");
        const message = el("phone-validation-message");
        if (!badge || !message) return;
        const state = inspection.empty ? "neutral" : (inspection.valid ? "valid" : "invalid");
        badge.className = `email-syntax-badge ${state}`;
        badge.textContent = inspection.empty ? "NOT CHECKED" : (inspection.valid ? "SYNTAX VALID" : "INVALID");
        message.className = `email-validation-message${inspection.empty ? "" : ` ${state}`}`;
        message.textContent = inspection.message;
    }

    function showFormError(message) {
        const box = el("phone-form-error");
        if (!box) return;
        box.textContent = message;
        box.style.display = message ? "block" : "none";
    }

    function setPhoneLoading(isLoading, message = "Parsing E.164 structure and telecom carrier data...") {
        const loading = el("phone-investigation-loading");
        const button = el("phone-investigate-button");
        const state = el("phone-form-state");
        if (loading) loading.style.display = isLoading ? "flex" : "none";
        if (button) {
            button.disabled = isLoading;
            button.textContent = isLoading ? "INVESTIGATION RUNNING..." : "INVESTIGATE PHONE";
        }
        if (state) {
            state.textContent = isLoading ? "REQUEST ACTIVE" : "READY";
            state.style.color = isLoading ? "var(--accent-cyan)" : "var(--text-muted)";
        }
        const loadingMessage = el("phone-loading-message");
        if (loadingMessage) loadingMessage.textContent = message;
    }

    function renderParsing(result) {
        const body = el("phone-parsing-body");
        if (!body) return;
        const p = result.parsing;
        body.innerHTML = renderKeyValueGrid([
            { label: "Parsing Status", value: p.valid ? "Valid E.164 Number" : "Unparseable Number" },
            { label: "E.164 Standard", value: p.e164_format || "N/A" },
            { label: "International Format", value: p.international_format || "N/A" },
            { label: "National Format", value: p.national_format || "N/A" },
            { label: "Country Code", value: p.country_code ? `+${p.country_code}` : "N/A" },
            { label: "Region Code", value: p.region_code || "N/A" },
            { label: "Telecom Carrier", value: p.carrier || "Not Assigned / Private" },
            { label: "Line Type", value: p.number_type || "UNKNOWN" },
        ]);
        const badge = el("phone-parsing-result-badge");
        if (badge) {
            badge.textContent = p.valid ? `${p.region_code || ""} VALID` : "INVALID";
            badge.className = `mono email-section-badge ${p.valid ? "completed" : "no_results"}`;
        }
    }

    function renderRisk(result) {
        const body = el("phone-risk-body");
        if (!body) return;
        const r = result.risk_summary;
        const score = r.risk_score;
        const label = (r.risk_label || "low").toUpperCase();
        
        let scoreClass = "low";
        if (score >= 80) scoreClass = "critical";
        else if (score >= 60) scoreClass = "high";
        else if (score >= 30) scoreClass = "medium";

        const reasonsHtml = (r.reasons || []).map(item => `<li>${escapeHTML(item)}</li>`).join("");

        body.innerHTML = `
            <div class="email-risk-overview">
                <div class="email-risk-score">
                    <span class="email-risk-number ${scoreClass}">${score}</span>
                    <span class="email-risk-label">${label} RISK</span>
                </div>
                <div style="flex:1; min-width:0;">
                    ${renderKeyValueGrid([
                        { label: "Line Classification", value: result.parsing.number_type },
                        { label: "VoIP Fraud Risk", value: r.is_voip_risk ? "YES — Virtual VoIP Line" : "NO — Standard Line" },
                    ])}
                </div>
            </div>
            <div class="email-subsection-title">Risk Factors &amp; Analyst Handling</div>
            <ul class="email-limitations-list">${reasonsHtml}</ul>
        `;

        const badge = el("phone-risk-result-badge");
        if (badge) {
            badge.textContent = `${score}/100 ${label}`;
            badge.className = `mono email-section-badge ${score >= 60 ? "no_results" : "completed"}`;
        }
    }

    function renderMessaging(result) {
        const body = el("phone-messaging-body");
        if (!body) return;
        const m = result.messaging;
        if (m.status === "skipped") {
            body.innerHTML = '<div class="email-not-run-state">Messaging presence checks were skipped.</div>';
            return;
        }

        body.innerHTML = `
            <div class="email-holehe-grid" style="grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));">
                <div class="email-holehe-card">
                    <div class="email-holehe-header">
                        <span class="email-holehe-name">WhatsApp Direct Chat</span>
                        <span class="email-holehe-badge positive">DIRECT DEEP LINK</span>
                    </div>
                    <div class="email-holehe-meta mono">${escapeHTML(m.whatsapp_url)}</div>
                    <div style="margin-top:8px;">
                        <a class="email-safe-link" href="${escapeHTML(m.whatsapp_url)}" target="_blank" rel="noopener noreferrer">
                            Open WhatsApp Chat (${escapeHTML(result.target_phone)}) ↗
                        </a>
                    </div>
                </div>

                <div class="email-holehe-card">
                    <div class="email-holehe-header">
                        <span class="email-holehe-name">Telegram Direct Search</span>
                        <span class="email-holehe-badge positive">DIRECT DEEP LINK</span>
                    </div>
                    <div class="email-holehe-meta mono">${escapeHTML(m.telegram_url)}</div>
                    <div style="margin-top:8px;">
                        <a class="email-safe-link" href="${escapeHTML(m.telegram_url)}" target="_blank" rel="noopener noreferrer">
                            Open Telegram Search (${escapeHTML(result.target_phone)}) ↗
                        </a>
                    </div>
                </div>
            </div>
        `;

        const badge = el("phone-messaging-result-badge");
        if (badge) {
            badge.textContent = "LEADS GENERATED";
            badge.className = "mono email-section-badge completed";
        }
    }

    function renderRegistries(result) {
        const body = el("phone-registries-body");
        if (!body) return;
        const spam = result.spam;
        const tc = result.truecaller;

        body.innerHTML = `
            <div class="email-holehe-grid" style="grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));">
                <div class="email-holehe-card">
                    <div class="email-holehe-header">
                        <span class="email-holehe-name">SpamCalls.net Search</span>
                    </div>
                    <div class="email-holehe-meta mono">${escapeHTML(spam.spamcalls_search_url)}</div>
                    <div style="margin-top:8px;">
                        <a class="email-safe-link" href="${escapeHTML(spam.spamcalls_search_url)}" target="_blank" rel="noopener noreferrer">
                            Search Spam Calls Registry ↗
                        </a>
                    </div>
                </div>

                <div class="email-holehe-card">
                    <div class="email-holehe-header">
                        <span class="email-holehe-name">Tellows Spam Registry</span>
                    </div>
                    <div class="email-holehe-meta mono">${escapeHTML(spam.tellows_search_url)}</div>
                    <div style="margin-top:8px;">
                        <a class="email-safe-link" href="${escapeHTML(spam.tellows_search_url)}" target="_blank" rel="noopener noreferrer">
                            Search Tellows Registry ↗
                        </a>
                    </div>
                </div>

                <div class="email-holehe-card">
                    <div class="email-holehe-header">
                        <span class="email-holehe-name">Truecaller Search Lead</span>
                    </div>
                    <div class="email-holehe-meta mono">${escapeHTML(tc.search_url)}</div>
                    <div style="margin-top:8px;">
                        <a class="email-safe-link" href="${escapeHTML(tc.search_url)}" target="_blank" rel="noopener noreferrer">
                            Search Truecaller Public Directory ↗
                        </a>
                    </div>
                </div>
            </div>
        `;

        const badge = el("phone-registries-result-badge");
        if (badge) {
            badge.textContent = "SEARCH LEADS READY";
            badge.className = "mono email-section-badge completed";
        }
    }

    function renderPhoneResult(result) {
        el("phone-result-target").textContent = result.target_phone || "Unknown phone";
        el("phone-result-meta").textContent = [
            result.investigation_id ? `Investigation ${result.investigation_id}` : "",
            result.case_id ? `Case ${result.case_id}` : "",
            result.reason_code ? `Reason ${result.reason_code}` : "",
            result.authorization?.authenticated_user ? `Operator ${result.authorization.authenticated_user}` : "",
            result.status ? result.status.toUpperCase() : "COMPLETED",
            new Date(result.timestamp).toLocaleString(),
        ].filter(Boolean).join(" · ");

        renderParsing(result);
        renderRisk(result);
        renderMessaging(result);
        renderRegistries(result);

        el("phone-investigation-results").style.display = "block";
        el("phone-investigation-results").scrollIntoView({ behavior: "smooth", block: "start" });
    }

    async function submitPhoneInvestigation(event) {
        event.preventDefault();
        if (activeController) return;

        const targetRaw = el("phone-target-input")?.value || "";
        const countryCode = el("phone-country-code")?.value || "IN";
        const caseId = stringValue(el("phone-case-id")?.value).trim();
        const reasonCode = stringValue(el("phone-reason-code")?.value).trim();
        const authorized = Boolean(el("phone-authorization-confirmed")?.checked);

        if (!targetRaw) {
            showFormError("Enter a target phone number.");
            el("phone-target-input")?.focus();
            return;
        }
        if (!CASE_ID_PATTERN.test(caseId)) {
            showFormError("Case ID is required (3–64 characters: letters, numbers, _, ., :, /, or -).");
            el("phone-case-id")?.focus();
            return;
        }
        if (!REASON_PATTERN.test(reasonCode)) {
            showFormError("Select a valid documented authorization reason code.");
            el("phone-reason-code")?.focus();
            return;
        }
        if (!authorized) {
            showFormError("Explicit authorization confirmation is mandatory before any provider call.");
            el("phone-authorization-confirmed")?.focus();
            return;
        }

        showFormError("");
        el("phone-investigation-results").style.display = "none";

        const payload = {
            phone_number: targetRaw,
            default_country: countryCode,
            authorized: true,
            reason_code: reasonCode,
            case_id: caseId,
            include_messaging_checks: Boolean(el("phone-option-messaging")?.checked),
            include_spam_check: Boolean(el("phone-option-spam")?.checked),
            include_truecaller: Boolean(el("phone-option-truecaller")?.checked),
        };

        const controller = new AbortController();
        const serial = ++requestSerial;
        activeController = controller;
        const timeoutId = window.setTimeout(() => controller.abort("timeout"), REQUEST_TIMEOUT_MS);
        setPhoneLoading(true);

        try {
            const response = await window.SocAuth.fetch(PHONE_ENDPOINT, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
                signal: controller.signal,
            });
            if (!response.ok) {
                const errText = await response.text();
                throw new Error(errText || "Phone investigation request failed");
            }
            const responseData = await response.json();
            if (serial !== requestSerial) return;
            currentPhoneResult = responseData;
            renderPhoneResult(currentPhoneResult);
        } catch (error) {
            if (serial !== requestSerial) return;
            showFormError(`Phone investigation failed: ${stringValue(error?.message, "Unknown error")}`);
        } finally {
            window.clearTimeout(timeoutId);
            if (serial === requestSerial) {
                activeController = null;
                setPhoneLoading(false);
            }
        }
    }

    function openPhoneInvestigation() {
        el("hero-search-view").style.display = "none";
        el("results-workspace").style.display = "none";
        el("email-investigation-view").style.display = "none";
        el("phone-investigation-view").style.display = "block";
        el("nav-username-investigation")?.classList.remove("is-active");
        el("nav-email-investigation")?.classList.remove("is-active");
        el("nav-phone-investigation")?.classList.add("is-active");
        const leaExport = el("nav-lea-export");
        if (leaExport) leaExport.style.display = "none";
    }

    function exportPhoneInvestigation(format) {
        if (!currentPhoneResult) {
            showFormError("Run a phone investigation before exporting evidence.");
            return;
        }
        const jsonContent = JSON.stringify(currentPhoneResult, null, 2);
        const safeCase = (currentPhoneResult.case_id || "phone-case").replace(/[^A-Za-z0-9_.-]/g, "_");
        const blob = new Blob([jsonContent], { type: "application/json;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = `${safeCase}_phone_investigation.json`;
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    }

    window.openPhoneInvestigation = openPhoneInvestigation;
    window.exportPhoneInvestigation = exportPhoneInvestigation;

    window.addEventListener("DOMContentLoaded", function () {
        const form = el("phone-investigation-form");
        const input = el("phone-target-input");
        form?.addEventListener("submit", submitPhoneInvestigation);
        input?.addEventListener("input", () => {
            setSyntaxIndicator(inspectPhoneSyntax(input.value));
            showFormError("");
        });
    });
})();
