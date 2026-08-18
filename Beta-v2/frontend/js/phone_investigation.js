/**
 * Comprehensive 4-Layer Phone OSINT UI Module for Beta-v2.
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
        const raw = stringValue(value).trim();
        if (!raw) return { empty: true, valid: false, message: "Enter a target phone number." };
        const cleaned = raw.replace(/[^\d+]/g, "");
        if (cleaned.length < 5 || cleaned.length > 20) {
            return { empty: false, valid: false, message: "Phone number must contain 5 to 20 digits." };
        }
        return { empty: false, valid: true, message: "Phone format valid." };
    }

    function setSyntaxIndicator(inspection) {
        const badge = el("phone-syntax-badge");
        const message = el("phone-validation-message");
        if (!badge || !message) return;
        const state = inspection.empty ? "neutral" : (inspection.valid ? "valid" : "invalid");
        badge.className = `email-syntax-badge ${state}`;
        badge.textContent = inspection.empty ? "NOT CHECKED" : (inspection.valid ? "VALID" : "INVALID");
        message.className = `email-validation-message${inspection.empty ? "" : ` ${state}`}`;
        message.textContent = inspection.message;
    }

    function showFormError(message) {
        const box = el("phone-form-error");
        if (!box) return;
        box.textContent = message;
        box.style.display = message ? "block" : "none";
    }

    function setPhoneLoading(isLoading, message = "Executing 4-layer Phone OSINT pipeline...") {
        const loading = el("phone-investigation-loading");
        const button = el("phone-investigate-button");
        const state = el("phone-form-state");
        if (loading) loading.style.display = isLoading ? "flex" : "none";
        if (button) {
            button.disabled = isLoading;
            button.textContent = isLoading ? "RUNNING OSINT SCAN..." : "INVESTIGATE PHONE";
        }
        if (state) {
            state.textContent = isLoading ? "RUNNING SCAN" : "READY";
            state.style.color = isLoading ? "var(--accent-cyan)" : "var(--text-muted)";
        }
        const loadingMessage = el("phone-loading-message");
        if (loadingMessage) loadingMessage.textContent = message;
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

    function renderParsing(result) {
        const body = el("phone-parsing-body");
        if (!body) return;
        const p = result.parsing;
        body.innerHTML = renderKeyValueGrid([
            { label: "Number Validity", value: p.valid ? "Valid (E.164 Recognized)" : "Invalid Format" },
            { label: "Original Format", value: p.original_format || result.target_phone },
            { label: "Country of Origin", value: p.country_name ? `${p.country_name} (${p.region_code || "ISO"})` : (p.region_code || "N/A") },
            { label: "International Format (E.164)", value: p.e164_format || "N/A" },
            { label: "National Format", value: p.national_format || "N/A" },
            { label: "Carrier Name", value: p.carrier || "Not Assigned / Unlisted Operator" },
            { label: "Line Type", value: p.number_type || "UNKNOWN" },
            { label: "Roaming / Network Status", value: p.roaming_indicator || "Standard" },
            { label: "Virtual / Disposable Check", value: p.is_disposable ? "WARNING: Disposable / Virtual Line" : "Standard Carrier SIM" },
        ]);
        const badge = el("phone-parsing-result-badge");
        if (badge) {
            badge.textContent = p.valid ? `${p.region_code || ""} VALID` : "INVALID";
            badge.className = `mono email-section-badge ${p.valid ? "completed" : "no_results"}`;
        }
    }

    function renderBreaches(result) {
        const body = el("phone-breaches-body");
        if (!body) return;
        const b = result.breach_discovery;

        if (b.status === "disabled" || b.status === "not_configured") {
            body.innerHTML = '<div class="email-not-run-state">Breach lookup by phone number is not configured or disabled.</div>';
            return;
        }

        if (b.status === "no_results" || !b.compromised) {
            body.innerHTML = '<div class="email-empty-state">No known breach records found associated with this phone number.</div>';
            const badge = el("phone-breaches-result-badge");
            if (badge) {
                badge.textContent = "CLEAN / NO BREACHES";
                badge.className = "mono email-section-badge completed";
            }
            return;
        }

        const dbRows = (b.databases || []).map(db => `
            <tr>
                <td class="mono"><strong>${escapeHTML(db.database_name)}</strong></td>
                <td>${escapeHTML(db.incident_summary || "Discovered in breach dump")}</td>
                <td class="mono">${db.record_count}</td>
                <td>${(db.exposed_data_types || []).map(t => `<span class="email-holehe-badge positive">${escapeHTML(t)}</span>`).join(" ")}</td>
            </tr>
        `).join("");

        body.innerHTML = `
            <div class="email-risk-overview" style="margin-bottom:12px;">
                <div class="email-risk-score">
                    <span class="email-risk-number ${b.confidence_score >= 80 ? "critical" : "medium"}">${b.confidence_score}%</span>
                    <span class="email-risk-label">CONFIDENCE SCORE</span>
                </div>
                <div style="flex:1; min-width:0;">
                    ${renderKeyValueGrid([
                        { label: "Breach Databases Hit", value: b.database_count },
                        { label: "Total Exposure Records", value: b.record_count },
                        { label: "Associated Emails Found", value: (b.associated_emails || []).join(", ") || "None" },
                        { label: "Associated Usernames Found", value: (b.associated_usernames || []).join(", ") || "None" },
                        { label: "Associated Names Found", value: (b.associated_names || []).join(", ") || "None" },
                        { label: "Physical Addresses Found", value: (b.associated_addresses || []).join(", ") || "None" },
                    ])}
                </div>
            </div>

            <div class="email-subsection-title">Discovered Breach Databases</div>
            <div style="overflow-x:auto;">
                <table class="email-restricted-table" style="width:100%;">
                    <thead>
                        <tr>
                            <th>Database / Breach</th>
                            <th>Summary / Exposure</th>
                            <th>Records</th>
                            <th>Exposed Data Types</th>
                        </tr>
                    </thead>
                    <tbody>${dbRows}</tbody>
                </table>
            </div>
        `;

        const badge = el("phone-breaches-result-badge");
        if (badge) {
            badge.textContent = `${b.database_count} BREACHES (${b.confidence_score}% CONFIDENCE)`;
            badge.className = "mono email-section-badge no_results";
        }
    }

    function renderWebDiscovery(result) {
        const body = el("phone-web-body");
        if (!body) return;
        const w = result.web_discovery;

        const dorkGroupsHtml = (w.dork_groups || []).map(group => `
            <div style="margin-bottom: 12px; background: rgba(0,0,0,0.2); padding: 10px; border-radius: 4px; border: 1px solid rgba(255,255,255,0.05);">
                <div class="mono" style="color: var(--accent-cyan); font-weight: 600; margin-bottom: 6px;">${escapeHTML(group.category)}</div>
                <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 8px;">
                    ${(group.dorks || []).map(d => `
                        <div style="background: rgba(255,255,255,0.03); padding: 8px; border-radius: 4px;">
                            <div style="font-size: 0.85rem; font-weight: 600;">${escapeHTML(d.title)}</div>
                            <div class="mono" style="font-size: 0.75rem; color: var(--text-muted); word-break: break-all; margin: 4px 0;">${escapeHTML(d.query)}</div>
                            <a class="email-safe-link" href="${escapeHTML(d.search_url)}" target="_blank" rel="noopener noreferrer" style="font-size: 0.75rem;">Run Dork Search ↗</a>
                        </div>
                    `).join("")}
                </div>
            </div>
        `).join("");

        const hitsHtml = (w.web_hits || []).length
            ? w.web_hits.map(h => `
                <div class="email-holehe-card" style="margin-bottom:8px;">
                    <div class="email-holehe-header">
                        <a href="${escapeHTML(h.url)}" target="_blank" class="email-safe-link" style="font-weight:600;">${escapeHTML(h.title)} ↗</a>
                    </div>
                    <div class="mono" style="font-size:0.8rem; color:var(--text-muted);">${escapeHTML(h.url)}</div>
                    <div style="font-size:0.85rem; margin-top:4px;">${escapeHTML(h.snippet)}</div>
                </div>
            `).join("")
            : '<div class="email-empty-state">No live SerpAPI hits parsed; click any Google Dork above to open search.</div>';

        body.innerHTML = `
            <div style="margin-bottom:12px;">
                <strong>Disposable Provider Status:</strong> <span class="mono">${escapeHTML(w.disposable_check)}</span>
            </div>

            <div class="email-subsection-title">Google Dorks Engine (Targeted OSINT Search Queries)</div>
            ${dorkGroupsHtml}

            <div class="email-subsection-title" style="margin-top:16px;">Search Engine Hits &amp; Mentions</div>
            <div>${hitsHtml}</div>
        `;

        const badge = el("phone-web-result-badge");
        if (badge) {
            badge.textContent = `${(w.dork_groups || []).length} DORK CATEGORIES`;
            badge.className = "mono email-section-badge completed";
        }
    }

    function renderSocialDiscovery(result) {
        const body = el("phone-social-body");
        if (!body) return;
        const s = result.social_discovery;

        const cards = (s.checks || []).map(c => `
            <div class="email-holehe-card">
                <div class="email-holehe-header">
                    <span class="email-holehe-name">${escapeHTML(c.platform)}</span>
                    <span class="email-holehe-badge positive">${escapeHTML(c.status.toUpperCase())}</span>
                </div>
                <div style="font-size: 0.8rem; color: var(--text-muted); margin: 4px 0;">${escapeHTML(c.details)}</div>
                <div>
                    <a class="email-safe-link" href="${escapeHTML(c.action_url)}" target="_blank" rel="noopener noreferrer">
                        Open ${escapeHTML(c.platform)} Lead ↗
                    </a>
                </div>
            </div>
        `).join("");

        body.innerHTML = `
            <div class="email-holehe-grid" style="grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));">
                ${cards}
            </div>
        `;

        const badge = el("phone-social-result-badge");
        if (badge) {
            badge.textContent = `${s.checked_count} PLATFORMS CHECKED`;
            badge.className = "mono email-section-badge completed";
        }
    }

    function renderExtractedProfile(result) {
        const body = el("phone-extracted-body");
        if (!body) return;
        const ep = result.extracted_profile;

        body.innerHTML = renderKeyValueGrid([
            { label: "Discovered Full Names", value: (ep.names || []).join(" | ") || "None discovered" },
            { label: "Linked Email Addresses", value: (ep.emails || []).join(" | ") || "None discovered" },
            { label: "Linked Usernames", value: (ep.usernames || []).join(" | ") || "None discovered" },
            { label: "Physical Addresses", value: (ep.addresses || []).join(" | ") || "None discovered" },
            { label: "Exposed Data Types", value: (ep.data_exposure_types || []).join(", ") || "Standard Phone & Carrier" },
        ]);

        const badge = el("phone-extracted-result-badge");
        if (badge) {
            badge.textContent = "PROFILE CONSOLIDATED";
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
        renderBreaches(result);
        renderWebDiscovery(result);
        renderSocialDiscovery(result);
        renderExtractedProfile(result);

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
            include_breaches: Boolean(el("phone-option-breaches")?.checked),
            include_web_dorks: Boolean(el("phone-option-dorks")?.checked),
            include_social: Boolean(el("phone-option-social")?.checked),
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
                throw new Error(errText || "Phone OSINT request failed");
            }
            const responseData = await response.json();
            if (serial !== requestSerial) return;
            currentPhoneResult = responseData;
            renderPhoneResult(currentPhoneResult);
        } catch (error) {
            if (serial !== requestSerial) return;
            showFormError(`Phone OSINT failed: ${stringValue(error?.message, "Unknown error")}`);
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

        const safeCase = (currentPhoneResult.case_id || "phone-case").replace(/[^A-Za-z0-9_.-]/g, "_");

        if (format === "json") {
            const content = JSON.stringify(currentPhoneResult, null, 2);
            downloadFile(content, `${safeCase}_phone_osint.json`, "application/json;charset=utf-8");
        } else if (format === "csv") {
            const rows = [
                ["Field", "Value"],
                ["Target Phone", currentPhoneResult.target_phone],
                ["Case ID", currentPhoneResult.case_id],
                ["Reason Code", currentPhoneResult.reason_code],
                ["Validity", currentPhoneResult.parsing.valid ? "Valid" : "Invalid"],
                ["Country", currentPhoneResult.parsing.country_name || currentPhoneResult.parsing.region_code || ""],
                ["Carrier", currentPhoneResult.parsing.carrier || ""],
                ["Line Type", currentPhoneResult.parsing.number_type],
                ["Discovered Names", (currentPhoneResult.extracted_profile?.names || []).join("; ")],
                ["Discovered Emails", (currentPhoneResult.extracted_profile?.emails || []).join("; ")],
                ["Discovered Usernames", (currentPhoneResult.extracted_profile?.usernames || []).join("; ")],
                ["Breach Count", currentPhoneResult.breach_discovery?.database_count || 0],
            ];
            const csv = rows.map(r => r.map(c => `"${String(c).replace(/"/g, '""')}"`).join(",")).join("\n");
            downloadFile(csv, `${safeCase}_phone_osint.csv`, "text/csv;charset=utf-8");
        } else if (format === "txt" || format === "pdf") {
            const txt = `PHONE OSINT INVESTIGATION REPORT
================================
Target Phone: ${currentPhoneResult.target_phone}
Case ID: ${currentPhoneResult.case_id}
Reason Code: ${currentPhoneResult.reason_code}
Timestamp: ${currentPhoneResult.timestamp}

1. VALIDATION & CARRIER INTELLIGENCE
-------------------------------------
Validity: ${currentPhoneResult.parsing.valid ? "Valid E.164 Number" : "Invalid"}
Country: ${currentPhoneResult.parsing.country_name || currentPhoneResult.parsing.region_code || "N/A"}
Carrier: ${currentPhoneResult.parsing.carrier || "Not Assigned"}
Line Type: ${currentPhoneResult.parsing.number_type}
Disposable / Virtual: ${currentPhoneResult.parsing.is_disposable ? "YES" : "NO"}

2. BREACH DISCOVERY
-------------------
Status: ${currentPhoneResult.breach_discovery.status}
Databases Hit: ${currentPhoneResult.breach_discovery.database_count}
Associated Emails: ${(currentPhoneResult.extracted_profile?.emails || []).join(", ") || "None"}
Associated Names: ${(currentPhoneResult.extracted_profile?.names || []).join(", ") || "None"}

3. SOCIAL & MESSENGER LEADS
---------------------------
${(currentPhoneResult.social_discovery.checks || []).map(c => `- ${c.platform}: ${c.action_url}`).join("\n")}
`;
            if (format === "pdf" && typeof window.print === "function") {
                const win = window.open("", "_blank");
                win.document.write(`<pre style="font-family:monospace; padding:20px;">${escapeHTML(txt)}</pre>`);
                win.document.close();
                win.focus();
                win.print();
            } else {
                downloadFile(txt, `${safeCase}_phone_osint.txt`, "text/plain;charset=utf-8");
            }
        }
    }

    function downloadFile(content, filename, mimeType) {
        const blob = new Blob([content], { type: mimeType });
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = filename;
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
