/**
 * UP Police Cyber Cell — OSINT SOC Engine (Beta-v2) Frontend Core
 */

const API_BASE = "http://127.0.0.1:8010";
let currentInvestigationData = null;
let progressInterval = null;

// Auth credentials check
window.addEventListener("DOMContentLoaded", () => {
    const isAuth = sessionStorage.getItem("upp_soc_auth");
    if (isAuth === "true") {
        document.getElementById("login-screen").style.display = "none";
        document.getElementById("main-dashboard").style.display = "block";
    }
    fetchApiKeysStatus();
});

function handleLogin() {
    const u = document.getElementById("login-user").value.trim();
    const p = document.getElementById("login-pass").value.trim();
    const err = document.getElementById("login-error");

    if (u === "uppolice" && p === "testingaccount") {
        sessionStorage.setItem("upp_soc_auth", "true");
        err.style.display = "none";
        document.getElementById("login-screen").style.display = "none";
        document.getElementById("main-dashboard").style.display = "block";
    } else {
        err.style.display = "block";
    }
}

function handleLogout() {
    sessionStorage.removeItem("upp_soc_auth");
    document.getElementById("main-dashboard").style.display = "none";
    document.getElementById("login-screen").style.display = "flex";
}

/* ---------- Smart Input Classifier ---------- */
function classifyInput(raw) {
    const s = raw.trim();
    if (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s)) return { kind: "email", raw: s };
    if (/^\+?[0-9][0-9\s().\-]{6,}$/.test(s)) return { kind: "phone", raw: s.replace(/[^\d+]/g, "") };
    const isUrl = /^https?:\/\//i.test(s);
    const isDomain = /^[a-z0-9-]+\.(?:com|org|net|io|co|ai|app|dev|info|biz|edu|gov|in|uk|us|me|xyz)$/i.test(s);
    if (isUrl || isDomain) return { kind: "domain", raw: s.replace(/^https?:\/\//i, "").replace(/\/.*$/, "") };
    if (/\s/.test(s)) return { kind: "name", raw: s };
    return { kind: "username", raw: s.replace(/^@/, "") };
}

const KIND_LABELS = {
    email: "EMAIL",
    phone: "PHONE",
    domain: "DOMAIN",
    name: "FULL NAME",
    username: "USERNAME",
};

function detectInputType(value) {
    const badge = document.getElementById("input-kind-badge");
    const heroBadge = document.getElementById("hero-kind-badge");
    const { kind } = classifyInput(value);
    const label = value.trim() ? (KIND_LABELS[kind] || kind.toUpperCase()) : "";

    if (badge) {
        badge.textContent = label;
        badge.style.display = label ? "inline-block" : "none";
    }
    if (heroBadge) {
        heroBadge.textContent = label;
        heroBadge.style.display = label ? "inline-block" : "none";
    }
}

function escapeHTML(val) {
    return String(val ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

function logConsole(text) {
    const stream = document.getElementById("console-stream");
    if (!stream) return;
    const time = new Date().toLocaleTimeString();
    const line = document.createElement("div");
    line.className = "terminal-line";
    line.textContent = `[${time}] ${text}`;
    stream.appendChild(line);
    stream.scrollTop = stream.scrollHeight;
}

function triggerLeaPdfExport() {
    if (!currentInvestigationData) {
        alert("Please execute an OSINT investigation scan first before exporting the official report.");
        return;
    }
    window.LeaPdfExporter.exportReport(currentInvestigationData);
}

/* ---------- Loader & Progress Fillup Animation ---------- */
function startScanLoader(target) {
    const overlay = document.getElementById("scan-loader-overlay");
    const bar = document.getElementById("loader-progress-bar");
    const pct = document.getElementById("loader-progress-pct");
    const text = document.getElementById("loader-step-text");
    const targetLabel = document.getElementById("loader-target-label");

    if (targetLabel) targetLabel.textContent = target;
    if (overlay) overlay.style.display = "flex";

    // Calibrated against live backend pipeline timing (avg 180,000 ms total runtime)
    const steps = [
        { p: 10, msg: "Initializing WhatsMyName 700+ cross-platform probe engine..." },
        { p: 25, msg: "Scraping public profiles & LinkedIn dossier (Apify + SignalHire)..." },
        { p: 40, msg: "Querying SignalHire candidate enrichment & contact discovery..." },
        { p: 55, msg: "Executing Google Search Dorking queries via SerpAPI & BrightData..." },
        { p: 70, msg: "Searching Telegram CTI darkweb & leak databases..." },
        { p: 85, msg: "Running AI multi-source behavioral classifier & threat scoring..." },
        { p: 95, msg: "Synthesizing Consolidated Identity & associated accounts matrix..." },
    ];

    let currentPct = 0;
    let stepIdx = 0;
    const startTime = Date.now();
    const ESTIMATED_TOTAL_MS = 180000;

    clearInterval(progressInterval);
    progressInterval = setInterval(() => {
        const elapsed = Date.now() - startTime;
        let targetPct = Math.min(97, Math.floor((elapsed / ESTIMATED_TOTAL_MS) * 97));

        if (currentPct < targetPct) {
            currentPct += 1;
        } else if (currentPct < 98 && elapsed >= ESTIMATED_TOTAL_MS) {
            if (Math.random() < 0.25) {
                currentPct += 1;
            }
        }

        if (bar) bar.style.width = currentPct + "%";
        if (pct) pct.textContent = currentPct + "%";

        while (stepIdx < steps.length - 1 && currentPct >= steps[stepIdx + 1].p) {
            stepIdx++;
        }
        if (steps[stepIdx] && text && text.textContent !== steps[stepIdx].msg) {
            text.textContent = steps[stepIdx].msg;
            logConsole(`[PROBE] ${steps[stepIdx].msg}`);
        }
    }, 450);
}

function stopScanLoader() {
    clearInterval(progressInterval);
    const bar = document.getElementById("loader-progress-bar");
    const pct = document.getElementById("loader-progress-pct");
    const overlay = document.getElementById("scan-loader-overlay");

    if (bar) bar.style.width = "100%";
    if (pct) pct.textContent = "100%";

    setTimeout(() => {
        if (overlay) overlay.style.display = "none";
    }, 400);
}

function resetToHeroView() {
    document.getElementById("hero-search-view").style.display = "block";
    document.getElementById("results-workspace").style.display = "none";
    window.scrollTo({ top: 0, behavior: "smooth" });
}

/* ---------- Main Investigation Execution ---------- */
async function executeScan(fromHero = false) {
    const heroInput = document.getElementById("hero-target-username");
    const sidebarInput = document.getElementById("target-username");

    let queryVal = "";
    if (fromHero && heroInput && heroInput.value.trim()) {
        queryVal = heroInput.value.trim();
        if (sidebarInput) sidebarInput.value = queryVal;
    } else if (sidebarInput && sidebarInput.value.trim()) {
        queryVal = sidebarInput.value.trim();
    } else if (heroInput && heroInput.value.trim()) {
        queryVal = heroInput.value.trim();
    }

    if (!queryVal) {
        alert("PLEASE ENTER A TARGET USERNAME / IDENTIFIER.");
        return;
    }

    const { kind } = classifyInput(queryVal);
    const emailVal = document.getElementById("provider-email")?.value.trim() || null;
    const phoneVal = document.getElementById("provider-phone")?.value.trim() || null;

    const payload = {
        username: queryVal,
        email: emailVal,
        phone_number: phoneVal,
        cache_mode: "use",
    };

    // Show loader fillup animation
    startScanLoader(queryVal);

    logConsole(`[SYS] OSINT DISPATCH — TARGET: ${queryVal} (${kind.toUpperCase()})`);

    try {
        const res = await fetch(`${API_BASE}/api/v1/investigation/username`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        if (!res.ok) {
            throw new Error(`API Error HTTP ${res.status}`);
        }

        const data = await res.json();
        currentInvestigationData = data;

        stopScanLoader();

        // Transition from Hero to Results Workspace
        document.getElementById("hero-search-view").style.display = "none";
        document.getElementById("results-workspace").style.display = "block";

        logConsole(`[SYS] ENVELOPE RECEIVED — CASE ID: ${data.investigation_id}`);
        logConsole("[SYS] RENDERING DETAILED OSINT INTELLIGENCE WORKSPACE...");

        renderResults(data);
        window.scrollTo({ top: 0, behavior: "smooth" });

    } catch (err) {
        stopScanLoader();
        logConsole(`[ERR] SCAN INTERRUPTED: ${err.message}`);
        alert(`OSINT Scan Interrupted: ${err.message}`);
    }
}

/* ---------- Rendering Engine ---------- */
function renderResults(data) {
    renderConsolidatedIdentity(data.consolidated_identity);
    renderAiPersonality(data.ai_personality, data.gemini_reasoning);
    renderAssociatedAccounts(data.associated_accounts);
    renderGoogleDorking(data.dorking_results);
    renderTelegramCTI(data.telegram_cti);
    renderPlatformDossiers(data.scraped_data);
    renderDiagnosticsPanel(data);
    renderMediaGallery(data);
}

// 1. Consolidated Identity Profile
function renderConsolidatedIdentity(ci) {
    const body = document.getElementById("consolidated-identity-body");
    const badge = document.getElementById("consolidated-confidence-badge");
    if (!body) return;
    if (!ci) { body.innerHTML = "<div style='color:var(--text-muted);'>No consolidated identity generated.</div>"; return; }

    const pct = ci.confidence_percentage || 0;
    if (badge) {
        badge.textContent = `${pct}% CONFIDENCE (${(ci.overall_confidence || "low").toUpperCase()})`;
        badge.style.color = pct >= 70 ? "var(--status-success)" : (pct >= 45 ? "var(--risk-medium)" : "var(--risk-high)");
    }

    const emailsHTML = (ci.emails || []).map(e => `
        <span class="tag-chip mono ${e.deliverable ? 'interest' : ''}">${escapeHTML(e.email)} <small>(${e.status})</small></span>
    `).join("");

    const linksHTML = (ci.links || []).map(l => `
        <a href="${escapeHTML(l)}" target="_blank" class="tag-chip mono" style="text-decoration:none;">${escapeHTML(l.replace(/^https?:\/\//, '').slice(0, 35))} ↗</a>
    `).join("");

    const photoHTML = ci.profile_pic ? `
        <div style="flex-shrink:0; text-align:center;">
            <img src="${ci.profile_pic}" alt="Profile" referrerpolicy="no-referrer" style="width:90px; height:90px; border-radius:50%; border:2px solid var(--accent-cyan); object-fit:cover; background:var(--bg-panel); display:block; margin:0 auto;" onerror="this.style.display='none';">
        </div>
    ` : `
        <div style="flex-shrink:0; text-align:center;">
            <div style="width:90px; height:90px; border-radius:50%; border:2px solid var(--border-divider); background:var(--bg-panel); display:flex; align-items:center; justify-content:center; margin:0 auto; color:var(--text-muted);">
                <svg style="width:36px; height:36px;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
                    <circle cx="12" cy="7" r="4"></circle>
                </svg>
            </div>
        </div>
    `;

    body.innerHTML = `
        <div style="display:flex; flex-direction:row; gap:20px; align-items:flex-start; flex-wrap:wrap; padding:6px 0;">
            ${photoHTML}
            <div style="flex:1; min-width:240px;">
                <table class="soc-table" style="margin-bottom:0;">
                    <tr><td style="width:30%; color:var(--text-muted); padding:6px 8px;">Likely Full Name</td><td style="padding:6px 8px;"><strong>${escapeHTML(ci.likely_name || "N/A")}</strong></td></tr>
                    <tr><td style="color:var(--text-muted); padding:6px 8px;">Location</td><td style="padding:6px 8px;">${escapeHTML(ci.location || "N/A")}</td></tr>
                    <tr><td style="color:var(--text-muted); padding:6px 8px;">Behavioral Category</td><td style="padding:6px 8px;"><span class="tag-chip interest">${escapeHTML(ci.profession || "N/A")}</span></td></tr>
                </table>
            </div>
        </div>
        <div style="margin-top:10px;">
            <div style="font-size:10px; font-weight:600; color:var(--text-muted); margin-bottom:4px;">VERIFIED & GUESS TARGET EMAILS (${(ci.emails||[]).length} DETECTED)</div>
            <div>${emailsHTML || "<span style='color:var(--text-muted);'>None</span>"}</div>
        </div>
        <div style="margin-top:14px;">
            <div style="font-size:10px; font-weight:600; color:var(--text-muted); margin-bottom:4px;">INTELLIGENCE TARGET DOSSIER LINKS (${(ci.links||[]).length} RESOLVED)</div>
            <div>${linksHTML || "<span style='color:var(--text-muted);'>None</span>"}</div>
        </div>
    `;
}

window.currentAiMode = "groq"; // "groq" | "gemini" | "sidebyside"
let cachedGroqData = null;
let cachedGeminiData = null;

function handleAiToggleChange(isGemini) {
    window.currentAiMode = isGemini ? "gemini" : "groq";

    // Sync all checkbox toggles
    document.querySelectorAll(".ai-toggle-checkbox").forEach(cb => cb.checked = isGemini);

    // Toggle label emphasis class
    document.querySelectorAll(".ai-toggle-row").forEach(row => {
        row.classList.toggle("ai-active", isGemini);
    });

    const label = document.getElementById("hero-ai-mode-label");
    if (label) label.textContent = isGemini ? "Gemini 3.6" : "Groq Llama-3.3";

    renderAiPersonalityBody();
}
window.handleAiToggleChange = handleAiToggleChange;

function switchAiModelMode(mode) {
    window.currentAiMode = mode;
    const isGemini = mode === "gemini";
    handleAiToggleChange(isGemini);
}
window.switchAiModelMode = switchAiModelMode;

// 2. AI Behavioral Profile
function renderAiPersonality(groq, gemini) {
    cachedGroqData = groq || null;
    renderAiPersonalityBody();
}

function renderAiPersonalityBody() {
    const body = document.getElementById("ai-personality-body");
    const catBadge = document.getElementById("ai-category-badge");
    if (!body) return;

    const groq = cachedGroqData || {};

    if (!cachedGroqData) {
        body.innerHTML = "<div style='color:var(--text-muted);'>No AI profile data available.</div>";
        return;
    }

    if (catBadge) {
        catBadge.textContent = `${groq.primaryCategory || "Unclassified"} · ${groq.confidence || 0}% (Groq)`;
    }

    body.innerHTML = renderGroqView(groq);
}
window.renderAiPersonalityBody = renderAiPersonalityBody;

function renderGroqView(ap) {
    if (!ap || !ap.summary) return "<div style='color:var(--text-muted); font-size:12px;'>Groq profiling data unavailable.</div>";
    const traitsHTML = (ap.traits || []).map(t => `<span class="tag-chip">${escapeHTML(t)}</span>`).join("");
    const interestsHTML = (ap.interests || []).map(i => `<span class="tag-chip interest">${escapeHTML(i)}</span>`).join("");
    const riskFlagsHTML = (ap.riskFlags || []).map(f => `
        <span class="risk-badge ${f.severity || 'low'}">${f.severity ? f.severity.toUpperCase() : 'LOW'}: ${escapeHTML(f.label)}</span>
    `).join("");

    return `
        <div style="font-size:12px; color:var(--text-primary); margin-bottom:12px; line-height:1.6;">${escapeHTML(ap.summary)}</div>
        <div style="margin-bottom:8px;">
            <div style="font-size:10px; color:var(--text-muted); font-weight:600; margin-bottom:4px;">BEHAVIORAL TRAITS</div>
            <div>${traitsHTML || "<span style='color:var(--text-muted); font-size:11px;'>None</span>"}</div>
        </div>
        <div style="margin-bottom:8px;">
            <div style="font-size:10px; color:var(--text-muted); font-weight:600; margin-bottom:4px;">DETECTED INTERESTS</div>
            <div>${interestsHTML || "<span style='color:var(--text-muted); font-size:11px;'>None</span>"}</div>
        </div>
        <div>
            <div style="font-size:10px; color:var(--text-muted); font-weight:600; margin-bottom:4px;">RISK FLAGS</div>
            <div>${riskFlagsHTML || "<span style='color:var(--status-success); font-size:11px;'>No risk flags.</span>"}</div>
        </div>
    `;
}
// 3. WhatsMyName Probe Matrix (deprecated, merged into platform matrix)

// 4. Google Search Dorking
function renderGoogleDorking(dorking) {
    const body = document.getElementById("dorking-results-body");
    const badge = document.getElementById("dorking-count-badge");
    if (!body) return;
    const results = dorking?.results || [];

    if (badge) badge.textContent = `${results.length} HITS RESOLVED`;

    if (!results.length) {
        body.innerHTML = "<div style='color:var(--text-muted); font-size:12px;'>No organic Google dorking hits.</div>";
        return;
    }

    const rows = results.map(r => `
        <tr>
            <td style="white-space:nowrap;"><span class="tag-chip interest">${escapeHTML(r.category || "Public Records")}</span></td>
            <td><a href="${escapeHTML(r.url)}" target="_blank" style="color:var(--text-primary); font-weight:600; text-decoration:none;">${escapeHTML(r.title)} &#x2197;</a><br><span class="mono" style="font-size:10px; color:var(--text-muted);">${escapeHTML(r.domain)}</span></td>
            <td style="color:var(--text-secondary); font-size:11px; max-width:260px;">${escapeHTML(r.snippet)}</td>
            <td class="mono" style="font-size:10px; color:var(--accent-cyan); white-space:nowrap;">${escapeHTML(r.query)}</td>
        </tr>
    `).join("");

    body.innerHTML = `<div class="table-scroll">
        <table class="soc-table">
            <thead><tr><th>Category</th><th>Title / Domain</th><th>Snippet Preview</th><th>Query Used</th></tr></thead>
            <tbody>${rows}</tbody>
        </table></div>`;
}

// 5. Associated Accounts
function renderAssociatedAccounts(accounts) {
    const body = document.getElementById("associated-accounts-body");
    const badge = document.getElementById("associated-accounts-badge");
    if (!body) return;
    const list = accounts || [];
    if (badge) badge.textContent = `${list.length} ACCOUNTS DISCOVERED`;
    if (!list.length) {
        body.innerHTML = "<div style='color:var(--text-muted); font-size:12px;'>No associated accounts discovered.</div>";
        return;
    }
    const rows = list.map(a => {
        const confColor = a.confidence >= 75 ? 'var(--status-success)' : (a.confidence >= 50 ? 'var(--risk-medium)' : 'var(--text-muted)');
        const reasonsHTML = (a.reasons || []).map(r => `<div style="font-size:10px; color:var(--text-secondary); margin-top:2px;">&#x2022; ${escapeHTML(r)}</div>`).join('');
        return `
            <tr>
                <td style="font-weight:600; color:var(--accent-cyan);">${escapeHTML(a.platform)}</td>
                <td><span class="tag-chip">${escapeHTML(a.category || 'general')}</span></td>
                <td class="mono">@${escapeHTML(a.username)}</td>
                <td><a href="${escapeHTML(a.url)}" target="_blank" style="color:var(--accent-cyan); text-decoration:none; font-size:11px;">${escapeHTML((a.url||'').slice(0,45))} &#x2197;</a></td>
                <td><span style="color:${confColor}; font-weight:700; font-size:13px;">${a.confidence}%</span><br><span style="font-size:9px; color:var(--text-muted);">${escapeHTML(a.match_status||'')}</span></td>
                <td>${reasonsHTML}</td>
            </tr>`;
    }).join('');
    body.innerHTML = `<div class="table-scroll">
        <table class="soc-table">
            <thead><tr><th>Platform</th><th>Category</th><th>Handle</th><th>Profile URL</th><th>Confidence</th><th>Evidence</th></tr></thead>
            <tbody>${rows}</tbody>
        </table></div>`;
}

// 6. Telegram CTI Breach Intelligence
function renderTelegramCTI(cti) {
    const body = document.getElementById("telegram-cti-body");
    const badge = document.getElementById("cti-records-badge");
    if (!body) return;
    const records = cti?.total_records || 0;

    if (badge) badge.textContent = `${records} COMPROMISED RECORDS (${(cti?.databases || []).length} DATABASES)`;

    if (!records) {
        body.innerHTML = "<div style='color:var(--status-success); font-size:12px;'>No breach records found in leak databases.</div>";
        return;
    }

    const FIELD_LABELS = {
        NickName: 'Nickname', Email: 'Email', Password: 'Password',
        Url: 'URL / Source', Phone: 'Phone', Name: 'Name',
        Username: 'Username', IP: 'IP Address', Country: 'Country',
        Address: 'Address', DOB: 'Date of Birth', Login: 'Login',
    };

    const results = cti?.results || [];
    let cardsHTML = '';
    results.forEach(res => {
        const dbName = res.database || 'Leak DB';
        const infoLeak = res.info_leak || '';
        const entries = res.data || [];
        entries.forEach(item => {
            const fieldRows = Object.entries(item).map(([k, v]) => {
                if (!v || v === '-') return '';
                const label = FIELD_LABELS[k] || k;
                const isPass = k.toLowerCase().includes('pass');
                const isUrl = k === 'Url' || k === 'url';
                const valStr = String(v);
                const display = isUrl
                    ? `<a href="${escapeHTML(valStr)}" target="_blank" style="color:var(--accent-cyan); word-break:break-all;">${escapeHTML(valStr)}</a>`
                    : `<span class="mono" style="color:${isPass ? 'var(--risk-critical)' : 'var(--text-primary)'}">${escapeHTML(valStr)}</span>`;
                return `<tr><td style="color:var(--text-muted); font-size:10px; width:100px; white-space:nowrap;">${escapeHTML(label)}</td><td>${display}</td></tr>`;
            }).filter(Boolean).join('');

            cardsHTML += `
                <div style="background:var(--bg-elevated); border:1px solid var(--risk-critical); border-left:3px solid var(--risk-critical); border-radius:4px; padding:12px; margin-bottom:10px;">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                        <span style="font-weight:700; font-size:11px; color:var(--risk-critical); letter-spacing:0.05em;">${escapeHTML(dbName)}</span>
                        <span style="font-size:10px; color:var(--text-muted); font-family:monospace;">${escapeHTML(infoLeak)}</span>
                    </div>
                    <table style="width:100%; border-collapse:collapse;">${fieldRows}</table>
                </div>`;
        });
    });

    body.innerHTML = cardsHTML || "<div style='color:var(--text-muted);'>No records could be parsed.</div>";
}

// 7. Platform Dossiers
function renderPlatformDossiers(scraped) {
    const body = document.getElementById("platform-dossiers-body");
    if (!body) return;
    if (!scraped || Object.keys(scraped).length === 0) {
        body.innerHTML = "<div style='color:var(--text-muted);'>No platform dossier data cached.</div>";
        return;
    }

    let cardsHTML = "";

    // Instagram Dossier
    if (scraped.instagram && scraped.instagram.success !== false) {
        const ig = scraped.instagram;
        const tagsHTML = (ig.post_hashtags || []).slice(0, 40).map(t => `<span class="tag-chip interest">#${escapeHTML(t)}</span>`).join("");
        const postsCount = (ig.posts || []).length;
        const verifiedBadge = ig.is_verified ? '<span style="color:var(--status-success); font-size:10px; margin-left:6px;">&#x2714; VERIFIED</span>' : '';
        const privateBadge = ig.is_private ? '<span style="color:var(--risk-medium); font-size:10px; margin-left:6px;">PRIVATE</span>' : '';
        cardsHTML += `
            <div style="background:var(--bg-elevated); border:1px solid var(--border-divider); border-radius:6px; padding:14px; margin-bottom:14px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                    <span style="font-weight:600; color:var(--accent-cyan);">INSTAGRAM DOSSIER${verifiedBadge}${privateBadge}</span>
                    <span class="mono" style="font-size:11px;">@${escapeHTML(ig.username || '')}</span>
                </div>
                <table class="soc-table" style="margin-bottom:8px;">
                    <tr><td style="color:var(--text-muted); width:120px;">Full Name</td><td><strong>${escapeHTML(ig.full_name || 'N/A')}</strong></td></tr>
                    <tr><td style="color:var(--text-muted);">Followers</td><td>${(ig.follower_count || 0).toLocaleString()}</td></tr>
                    <tr><td style="color:var(--text-muted);">Following</td><td>${(ig.following_count || 0).toLocaleString()}</td></tr>
                    <tr><td style="color:var(--text-muted);">Posts</td><td>${ig.post_count || postsCount || 0} (${postsCount} scraped)</td></tr>
                    ${ig.business_category ? `<tr><td style="color:var(--text-muted);">Category</td><td><span class="tag-chip">${escapeHTML(ig.business_category)}</span></td></tr>` : ''}
                    ${ig.external_url ? `<tr><td style="color:var(--text-muted);">Website</td><td><a href="${escapeHTML(ig.external_url)}" target="_blank" style="color:var(--accent-cyan);">${escapeHTML(ig.external_url)}</a></td></tr>` : ''}
                </table>
                <div style="font-size:12px; color:var(--text-secondary); margin-bottom:8px; padding:8px; background:var(--bg-panel); border-radius:4px;">${escapeHTML(ig.bio || 'No bio.')}</div>
                <div>
                    <div style="font-size:10px; font-weight:600; color:var(--text-muted); margin-bottom:4px;">POST HASHTAGS EXTRACTED (${(ig.post_hashtags||[]).length} UNIQUE)</div>
                    <div>${tagsHTML || "<span style='color:var(--text-muted); font-size:11px;'>No hashtags extracted.</span>"}</div>
                </div>
            </div>
        `;
    }

    // TikTok Dossier
    if (scraped.tiktok && scraped.tiktok.success !== false) {
        const tt = scraped.tiktok;
        const tagsHTML = (tt.hashtags || []).slice(0, 40).map(t => `<span class="tag-chip interest">#${escapeHTML(t)}</span>`).join("");
        cardsHTML += `
            <div style="background:var(--bg-elevated); border:1px solid var(--border-divider); border-radius:6px; padding:14px; margin-bottom:14px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                    <span style="font-weight:600; color:var(--accent-cyan);">TIKTOK PUBLIC DOSSIER</span>
                    <span class="mono" style="font-size:11px;">@${escapeHTML(tt.username || '')}</span>
                </div>
                <table class="soc-table" style="margin-bottom:8px;">
                    <tr><td style="color:var(--text-muted); width:120px;">Full Name</td><td><strong>${escapeHTML(tt.full_name || 'N/A')}</strong></td></tr>
                    <tr><td style="color:var(--text-muted);">Followers / Fans</td><td>${(tt.follower_count || 0).toLocaleString()}</td></tr>
                    <tr><td style="color:var(--text-muted);">Total Hearts / Likes</td><td>${(tt.heart_count || 0).toLocaleString()}</td></tr>
                    <tr><td style="color:var(--text-muted);">Videos Count</td><td>${tt.video_count || (tt.videos || []).length}</td></tr>
                    ${tt.url ? `<tr><td style="color:var(--text-muted);">Profile URL</td><td><a href="${escapeHTML(tt.url)}" target="_blank" style="color:var(--accent-cyan);">${escapeHTML(tt.url)}</a></td></tr>` : ''}
                </table>
                <div style="font-size:12px; color:var(--text-secondary); margin-bottom:8px; padding:8px; background:var(--bg-panel); border-radius:4px;">${escapeHTML(tt.bio || 'No TikTok bio.')}</div>
                <div>
                    <div style="font-size:10px; font-weight:600; color:var(--text-muted); margin-bottom:4px;">VIDEO HASHTAGS (${(tt.hashtags||[]).length} EXTRACTED)</div>
                    <div>${tagsHTML || "<span style='color:var(--text-muted); font-size:11px;'>No video hashtags found.</span>"}</div>
                </div>
            </div>
        `;
    }

    // LinkedIn Dossier
    if (scraped.linkedin && (scraped.linkedin.success || scraped.linkedin.full_name || scraped.linkedin.headline || scraped.linkedin.basic_info)) {
        const li = scraped.linkedin;
        const info = li.basic_info || li || {};
        const fullname = info.fullname || info.full_name || "N/A";
        const headline = info.headline || "N/A";
        const companyName = info.current_company || li.current_company || li.company || "N/A";
        const locationText = (info.location && typeof info.location === 'object') ? (info.location.full || info.location.city || "N/A") : (info.location || "N/A");
        const profileUrl = info.profile_url || li.profile_url || li.url || "";
        const followers = info.follower_count ? info.follower_count.toLocaleString() : "N/A";
        const picUrl = info.profile_picture_url || info.profile_pic_url || "";
        const label = li.source ? `LINKEDIN (${escapeHTML(String(li.source).toUpperCase())})` : "LINKEDIN DOSSIER";

        let expHTML = "";
        const experiences = li.experience || [];
        if (experiences.length > 0) {
            expHTML = `
                <div style="margin-top:12px;">
                    <div style="font-size:10px; font-weight:700; color:var(--text-muted); margin-bottom:6px; letter-spacing:0.05em;">WORK HISTORY & EXPERIENCE</div>
                    <div style="display:flex; flex-direction:column; gap:8px; border-left:2px solid var(--border-divider); padding-left:12px; margin-left:4px;">
                        ${experiences.map(e => `
                            <div style="font-size:11px; line-height:1.4;">
                                <strong style="color:var(--text-primary);">${escapeHTML(e.title)}</strong> at <span style="color:var(--accent-cyan); font-weight:600;">${escapeHTML(e.company)}</span>
                                <div style="color:var(--text-muted); font-size:10px;">${escapeHTML(e.duration || '')} ${e.location ? `· ${escapeHTML(e.location)}` : ''}</div>
                            </div>
                        `).join("")}
                    </div>
                </div>
            `;
        }

        let eduHTML = "";
        const educations = li.education || [];
        if (educations.length > 0) {
            eduHTML = `
                <div style="margin-top:12px;">
                    <div style="font-size:10px; font-weight:700; color:var(--text-muted); margin-bottom:6px; letter-spacing:0.05em;">EDUCATION HISTORY</div>
                    <div style="display:flex; flex-direction:column; gap:6px;">
                        ${educations.map(e => `
                            <div style="font-size:11px; line-height:1.4;">
                                <strong>${escapeHTML(e.school)}</strong>
                                <div style="color:var(--text-secondary); font-size:10px;">${escapeHTML(e.degree || e.degree_name || '')} ${e.field_of_study ? `(${escapeHTML(e.field_of_study)})` : ''}</div>
                            </div>
                        `).join("")}
                    </div>
                </div>
            `;
        }

        let featHTML = "";
        const featured = li.featured || [];
        if (featured.length > 0) {
            featHTML = `
                <div style="margin-top:12px;">
                    <div style="font-size:10px; font-weight:700; color:var(--text-muted); margin-bottom:6px; letter-spacing:0.05em;">FEATURED PUBLICATIONS & LINKS</div>
                    <div style="display:flex; flex-wrap:wrap; gap:8px;">
                        ${featured.map(f => `
                            <a href="${escapeHTML(f.url)}" target="_blank" style="display:flex; align-items:center; gap:8px; background:var(--bg-panel); border:1px solid var(--border-divider); border-radius:4px; padding:6px 10px; text-decoration:none; color:var(--text-primary); font-size:11px; max-width:320px;">
                                ${f.image_url ? `<img src="${f.image_url}" referrerpolicy="no-referrer" style="width:24px; height:24px; object-fit:cover; border-radius:2px;" onerror="this.style.display='none';">` : ''}
                                <div style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
                                    <strong style="color:var(--accent-cyan);">${escapeHTML(f.title || 'Featured Link')}</strong>
                                    <div style="font-size:9px; color:var(--text-muted);">${escapeHTML(f.description || '')}</div>
                                </div>
                            </a>
                        `).join("")}
                    </div>
                </div>
            `;
        }

        let rrHTML = "";
        if (li.rocketreach && li.rocketreach.success) {
            const rr = li.rocketreach;
            const rrEmailsHTML = (rr.raw_emails || (rr.emails || []).map(e => ({email: e}))).map(e => {
                const addr = typeof e === 'string' ? e : e.email;
                const status = typeof e === 'object' && e.smtp_valid ? e.smtp_valid : '';
                const typeStr = typeof e === 'object' && e.type ? ` (${e.type})` : '';
                const isGood = status === 'valid' || !status;
                return `<span class="tag-chip mono ${isGood ? 'interest' : ''}">${escapeHTML(addr)}${escapeHTML(typeStr)}</span>`;
            }).join("");

            const rrPhonesHTML = (rr.raw_phones || (rr.phones || []).map(p => ({number: p}))).map(p => {
                const num = typeof p === 'string' ? p : (p.number || p.e164);
                const typeStr = typeof p === 'object' && p.type ? ` [${p.type}]` : '';
                return `<span class="tag-chip mono" style="color:var(--status-success); border-color:var(--status-success);">${escapeHTML(num)}${escapeHTML(typeStr)}</span>`;
            }).join("");

            rrHTML = `
                <div style="margin-top:12px; padding:10px; background:rgba(0,220,255,0.04); border:1px solid rgba(0,220,255,0.2); border-radius:4px;">
                    <div style="font-size:10px; font-weight:700; color:var(--accent-cyan); margin-bottom:6px; letter-spacing:0.05em; display:flex; justify-content:space-between;">
                        <span>🚀 ROCKETREACH CONTACT ENRICHMENT</span>
                        <span>CONFIRMED MATCH</span>
                    </div>
                    ${rr.full_name ? `<div style="font-size:11px; color:var(--text-primary);"><strong>Full Name:</strong> ${escapeHTML(rr.full_name)} ${rr.current_title ? `· <em>${escapeHTML(rr.current_title)}</em>` : ''}</div>` : ''}
                    ${rr.current_employer ? `<div style="font-size:11px; color:var(--text-secondary);"><strong>Employer:</strong> ${escapeHTML(rr.current_employer)} ${rr.location ? `(${escapeHTML(rr.location)})` : ''}</div>` : ''}
                    <div style="font-size:10px; margin-top:6px;">
                        <strong>Direct Emails (${(rr.emails||[]).length}):</strong> ${rrEmailsHTML || "<span style='color:var(--text-muted);'>None</span>"}<br>
                        <strong>Phone Numbers (${(rr.phones||[]).length}):</strong> ${rrPhonesHTML || "<span style='color:var(--text-muted);'>None</span>"}
                    </div>
                </div>
            `;
        }

        cardsHTML += `
            <div style="background:var(--bg-elevated); border:1px solid var(--border-divider); border-radius:6px; padding:14px; margin-bottom:14px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                    <span style="font-weight:600; color:var(--accent-cyan);">${label}</span>
                    <span class="mono" style="font-size:11px;"><a href="${escapeHTML(profileUrl)}" target="_blank" style="color:var(--accent-cyan); text-decoration:none;">${escapeHTML(profileUrl)} &#x2197;</a></span>
                </div>
                <div style="display:flex; gap:16px; align-items:flex-start; margin-bottom:10px; flex-wrap:wrap;">
                    ${picUrl ? `<img src="${picUrl}" referrerpolicy="no-referrer" style="width:64px; height:64px; border-radius:50%; border:2px solid var(--accent-cyan); object-fit:cover;" onerror="this.style.display='none';">` : ''}
                    <div style="flex:1;">
                        <div style="font-size:14px; font-weight:700; color:var(--text-primary);">${escapeHTML(fullname)}</div>
                        <div style="font-size:12px; color:var(--text-secondary); margin-top:2px;">${escapeHTML(headline)}</div>
                        <div style="font-size:11px; color:var(--text-muted); margin-top:4px;">
                            <strong>Current Employment:</strong> ${escapeHTML(companyName)} | <strong>Location:</strong> ${escapeHTML(locationText)}
                        </div>
                    </div>
                </div>
                <div style="font-size:11px; margin-top:6px; color:var(--text-secondary);">
                    <strong>Followers:</strong> ${followers}<br>
                    <strong>Emails:</strong> ${(li.emails || []).map(e => `<span class="tag-chip interest">${escapeHTML(e)}</span>`).join("") || "<span style='color:var(--text-muted);'>None</span>"}<br>
                    <strong>Phone Numbers:</strong> ${(li.phone_numbers || li.phones || []).map(p => `<span class="tag-chip mono" style="color:var(--status-success); border-color:var(--status-success);">${escapeHTML(p)}</span>`).join("") || "<span style='color:var(--text-muted);'>None</span>"}
                </div>
                ${rrHTML}
                ${expHTML}
                ${eduHTML}
                ${featHTML}
            </div>
        `;
    // Standalone RocketReach Card
    const rrData = scraped.rocketreach || (scraped.linkedin && scraped.linkedin.rocketreach);
    if (rrData && (rrData.success || (rrData.emails && rrData.emails.length > 0) || (rrData.phones && rrData.phones.length > 0) || rrData.full_name)) {
        const rr = rrData;
        const rrEmails = (rr.raw_emails || (rr.emails || []).map(e => ({email: e}))).map(e => {
            const addr = typeof e === 'string' ? e : e.email;
            const status = typeof e === 'object' && e.smtp_valid ? e.smtp_valid : '';
            const typeStr = typeof e === 'object' && e.type ? ` (${e.type})` : '';
            const isGood = status === 'valid' || !status;
            return `<span class="tag-chip mono ${isGood ? 'interest' : ''}">${escapeHTML(addr)}${escapeHTML(typeStr)}</span>`;
        }).join("");

        const rrPhones = (rr.raw_phones || (rr.phones || []).map(p => ({number: p}))).map(p => {
            const num = typeof p === 'string' ? p : (p.number || p.e164);
            const typeStr = typeof p === 'object' && p.type ? ` [${p.type}]` : '';
            return `<span class="tag-chip mono" style="color:var(--status-success); border-color:var(--status-success);">${escapeHTML(num)}${escapeHTML(typeStr)}</span>`;
        }).join("");

        let rrExp = "";
        if (rr.job_history && rr.job_history.length > 0) {
            rrExp = `
                <div style="margin-top:12px;">
                    <div style="font-size:10px; font-weight:700; color:var(--text-muted); margin-bottom:6px; letter-spacing:0.05em;">WORK HISTORY (ROCKETREACH)</div>
                    <div style="display:flex; flex-direction:column; gap:6px; border-left:2px solid var(--accent-cyan); padding-left:10px;">
                        ${rr.job_history.map(j => `
                            <div style="font-size:11px; line-height:1.4;">
                                <strong style="color:var(--text-primary);">${escapeHTML(j.title || 'Role')}</strong> at <span style="color:var(--accent-cyan);">${escapeHTML(j.company || 'Company')}</span>
                                <div style="color:var(--text-muted); font-size:10px;">${escapeHTML(j.duration || '')} ${j.location ? `· ${escapeHTML(j.location)}` : ''}</div>
                            </div>
                        `).join("")}
                    </div>
                </div>
            `;
        }

        cardsHTML += `
            <div style="background:var(--bg-elevated); border:1px solid rgba(0,220,255,0.3); border-radius:6px; padding:14px; margin-bottom:14px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                    <span style="font-weight:600; color:var(--accent-cyan);">🚀 ROCKETREACH CONTACT DOSSIER</span>
                    <span class="mono" style="font-size:11px; color:var(--status-success);">CONFIRMED MATCH</span>
                </div>
                <div style="font-size:14px; font-weight:700; color:var(--text-primary);">${escapeHTML(rr.full_name || 'N/A')}</div>
                <div style="font-size:11px; color:var(--text-secondary); margin-top:2px;">${escapeHTML(rr.current_title || 'N/A')} ${rr.current_employer ? `at ${escapeHTML(rr.current_employer)}` : ''}</div>
                <div style="font-size:11px; color:var(--text-muted); margin-top:4px;"><strong>Location:</strong> ${escapeHTML(rr.location || 'N/A')}</div>
                <div style="font-size:11px; margin-top:10px; color:var(--text-secondary);">
                    <strong>Verified Emails:</strong> ${rrEmails || "<span style='color:var(--text-muted);'>None</span>"}<br>
                    <strong>Phone Numbers:</strong> ${rrPhones || "<span style='color:var(--text-muted);'>None</span>"}
                </div>
                ${rrExp}
            </div>
        `;
    }

    // Twitter / X Dossier
    if (scraped.twitter && scraped.twitter.success !== false) {
        const tw = scraped.twitter;
        const tweetsHTML = (tw.tweets || []).map(t => `
            <div style="background:var(--bg-panel); border:1px solid var(--border-divider); border-radius:4px; padding:8px 10px; margin-bottom:6px; font-size:11px; line-height:1.4;">
                <div style="color:var(--text-primary);">${escapeHTML(t.text)}</div>
                <div style="font-size:9px; color:var(--text-muted); margin-top:4px; display:flex; gap:10px;">
                    <span>❤️ ${t.like_count}</span>
                    <span>🔁 ${t.retweet_count}</span>
                    <span>${t.created_at ? escapeHTML(new Date(t.created_at).toLocaleDateString()) : ''}</span>
                </div>
            </div>
        `).join("");

        cardsHTML += `
            <div style="background:var(--bg-elevated); border:1px solid var(--border-divider); border-radius:6px; padding:14px; margin-bottom:14px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                    <span style="font-weight:600; color:var(--accent-cyan);">X (TWITTER) PUBLIC DOSSIER</span>
                    <span class="mono" style="font-size:11px;">@${escapeHTML(tw.username || '')}</span>
                </div>
                <div style="display:flex; gap:16px; align-items:flex-start; margin-bottom:10px; flex-wrap:wrap;">
                    ${tw.profile_pic_url ? `<img src="${tw.profile_pic_url}" referrerpolicy="no-referrer" style="width:64px; height:64px; border-radius:50%; border:2px solid var(--accent-cyan); object-fit:cover;" onerror="this.style.display='none';">` : ''}
                    <div style="flex:1;">
                        <div style="font-size:14px; font-weight:700; color:var(--text-primary);">${escapeHTML(tw.full_name || 'N/A')}</div>
                        <div style="font-size:11px; color:var(--text-muted); margin-top:4px;">
                            <strong>Followers:</strong> ${(tw.follower_count || 0).toLocaleString()} | <strong>Following:</strong> ${(tw.following_count || 0).toLocaleString()} | <strong>Total Tweets:</strong> ${(tw.post_count || 0).toLocaleString()}
                        </div>
                    </div>
                </div>
                <div style="font-size:12px; color:var(--text-secondary); margin-bottom:8px; padding:8px; background:var(--bg-panel); border-radius:4px;">${escapeHTML(tw.bio || 'No bio.')}</div>
                ${tweetsHTML ? `
                    <div style="margin-top:10px;">
                        <div style="font-size:10px; font-weight:600; color:var(--text-muted); margin-bottom:6px; letter-spacing:0.05em;">RECENT PUBLIC TWEETS</div>
                        <div>${tweetsHTML}</div>
                    </div>
                ` : ''}
            </div>
        `;
    }

    // Facebook Dossier
    if (scraped.facebook && scraped.facebook.success !== false) {
        const fb = scraped.facebook;
        cardsHTML += `
            <div style="background:var(--bg-elevated); border:1px solid var(--border-divider); border-radius:6px; padding:14px; margin-bottom:14px;">
                <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
                    <span style="font-weight:600; color:var(--accent-cyan);">FACEBOOK PAGE DOSSIER</span>
                    <span class="mono" style="font-size:11px;">@${escapeHTML(fb.page_name || fb.username)}</span>
                </div>
                <div style="font-size:13px; margin-bottom:6px;"><strong>Page Title:</strong> ${escapeHTML(fb.title || fb.page_name)}</div>
                <div style="font-size:12px; color:var(--text-secondary);">${escapeHTML(fb.bio || "Public Facebook page.")}</div>
            </div>
        `;
    }

    body.innerHTML = cardsHTML || "<div style='color:var(--text-muted);'>No dossier details.</div>";
}


/* ---------- Diagnostics & Integrity Check ---------- */
async function fetchApiKeysStatus() {
    const listContainer = document.getElementById("hero-api-keys-list");
    const statusDot = document.getElementById("hero-api-status-dot");
    if (!listContainer) return;

    try {
        const res = await fetch(`${API_BASE}/api/v1/investigation/diagnostics/keys`);
        if (!res.ok) throw new Error("Diagnostics API unreachable");
        const keys = await res.json();

        let html = "";
        let missingCount = 0;
        let activeCount = 0;

        for (const [keyName, details] of Object.entries(keys)) {
            const isOK = details.configured;
            const badgeColor = isOK ? "var(--status-success)" : "var(--text-muted)";
            const badgeBg = isOK ? "rgba(40,167,69,0.15)" : "rgba(255,255,255,0.05)";
            const label = keyName.toUpperCase().replace("_", " ");

            if (isOK) activeCount++; else missingCount++;

            html += `
                <div style="display:flex; justify-content:space-between; align-items:center; background:var(--bg-panel); border:1px solid var(--border-divider); padding:6px 10px; border-radius:4px; margin-bottom:4px;">
                    <span style="font-weight:600; color:var(--text-secondary);">${label}</span>
                    <span style="color:${badgeColor}; background:${badgeBg}; padding:1px 5px; border-radius:3px; font-weight:700; font-size:8px; border:1px solid ${badgeColor};">${details.status.toUpperCase()}</span>
                </div>
            `;
        }

        listContainer.innerHTML = html;
        if (statusDot) {
            if (missingCount === 0) {
                statusDot.textContent = "● FULLY OPERATIONAL";
                statusDot.style.color = "var(--status-success)";
            } else if (activeCount > 0) {
                statusDot.textContent = `● DEGRADED (${missingCount} MISSING)`;
                statusDot.style.color = "var(--risk-medium)";
            } else {
                statusDot.textContent = "● OFFLINE (NO KEYS)";
                statusDot.style.color = "var(--risk-high)";
            }
        }

    } catch (err) {
        listContainer.innerHTML = `<div style="color:var(--risk-high); font-size:10px;">Failed to query active SOC integrations.</div>`;
        if (statusDot) {
            statusDot.textContent = "● OFFLINE";
            statusDot.style.color = "var(--risk-high)";
        }
    }
}

function renderDiagnosticsPanel(data) {
    const body = document.getElementById("diagnostics-body");
    const summaryBadge = document.getElementById("diagnostics-summary-badge");
    if (!body) return;

    let items = [];
    let errorsCount = 0;
    let warningsCount = 0;

    // WMN Probe
    const wmn = data.wmn_results || {};
    if (wmn.status === "success") {
        items.push({
            name: "WhatsMyName 700+ Site Probe",
            status: "OK",
            details: `Scanned ${wmn.scanned || 719} sites. Found ${wmn.hits_count || 0} hits.`,
            recovery: null
        });
    } else {
        errorsCount++;
        items.push({
            name: "WhatsMyName 700+ Site Probe",
            status: "ERROR",
            details: wmn.message || "Failed to query site availability templates.",
            recovery: "Ensure local app/data/wmn-data.json is present and has correct formatting."
        });
    }

    // Scrapers
    const scraped = data.scraped_data || {};
    const scrapersList = [
        { key: "instagram", name: "Instagram Scraper" },
        { key: "facebook", name: "Facebook Scraper" },
        { key: "tiktok", name: "TikTok Scraper" },
        { key: "linkedin", name: "LinkedIn Scraper" },
        { key: "rocketreach", name: "RocketReach Enrichment" }
    ];

    scrapersList.forEach(s => {
        const sd = scraped[s.key];
        if (sd) {
            if (sd.success || sd.status === "completed" || sd.status === "success") {
                items.push({
                    name: s.name,
                    status: "OK",
                    details: `Data fetched successfully (${sd.source || 'Apify'}).`,
                    recovery: null
                });
            } else {
                warningsCount++;
                items.push({
                    name: s.name,
                    status: "WARNING",
                    details: sd.error || "Empty response or selector mismatch.",
                    recovery: "Check APIFY_API_TOKEN configuration, verify target profile actually exists, or check Apify Actor status."
                });
            }
        } else {
            warningsCount++;
            items.push({
                name: s.name,
                status: "NOT_RUN",
                details: "Scraper did not execute or returned no data.",
                recovery: "Ensure APIFY_API_TOKEN is configured in backend/.env file."
            });
        }
    });

    // Dorking
    const dork = data.dorking_results || {};
    if (dork.status === "success" || dork.status === "completed") {
        items.push({
            name: "Google Dorking Engine",
            status: "OK",
            details: `Found ${dork.results_count || (dork.results || []).length || 0} search results via SerpAPI.`,
            recovery: null
        });
    } else {
        warningsCount++;
        items.push({
            name: "Google Dorking Engine",
            status: "WARNING",
            details: dork.error || "SerpAPI rate limit or connection issue.",
            recovery: "Check SERPAPI_KEY in backend/.env file."
        });
    }

    // Telegram CTI
    const cti = data.telegram_cti || {};
    if (cti.status === "success") {
        items.push({
            name: "Telegram CTI Breach Lookup",
            status: "OK",
            details: `Queried identifiers. Found ${cti.total_records || 0} leak records.`,
            recovery: null
        });
    } else if (cti.status === "not_configured") {
        warningsCount++;
        items.push({
            name: "Telegram CTI Breach Lookup",
            status: "DISABLED",
            details: "TELEGRAM_CTI_API_KEY is not configured.",
            recovery: "Add a valid LeakOSINT API token as TELEGRAM_CTI_API_KEY in .env."
        });
    } else {
        errorsCount++;
        items.push({
            name: "Telegram CTI Breach Lookup",
            status: "ERROR",
            details: cti.error || "Subscription expired or API server 502/outage.",
            recovery: "Verify CTI token. If message is 502, retry scan shortly as the leakosintapi.com server is temporarily down."
        });
    }

    // HiTek SQLite DB
    const hitek = data.internal_database_matches || {};
    if (hitek.status === "success") {
        items.push({
            name: "HiTek Offline Database",
            status: "OK",
            details: `Found ${hitek.matches?.length || 0} local matches.`,
            recovery: null
        });
    } else {
        items.push({
            name: "HiTek Offline Database",
            status: "NOT_RUN",
            details: "Local SQLite matches database is offline or not found.",
            recovery: "Check if DBs/hi-tek/hitek.db exists in backend workspace."
        });
    }

    // Render HTML
    let html = `<div style="display:flex; flex-direction:column; gap:8px;">`;
    items.forEach(item => {
        let statusColor = "var(--text-muted)";
        let statusBg = "rgba(255,255,255,0.03)";
        if (item.status === "OK") {
            statusColor = "var(--status-success)";
            statusBg = "rgba(40, 167, 69, 0.1)";
        } else if (item.status === "WARNING" || item.status === "DISABLED") {
            statusColor = "var(--risk-medium)";
            statusBg = "rgba(255, 193, 7, 0.1)";
        } else if (item.status === "ERROR") {
            statusColor = "var(--risk-high)";
            statusBg = "rgba(220, 53, 69, 0.1)";
        }

        html += `
            <div style="background:var(--bg-panel); border:1px solid var(--border-divider); border-radius:6px; padding:10px; font-family:'JetBrains Mono', monospace; font-size:10px; line-height:1.4;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                    <span style="font-weight:600; color:var(--text-primary);">${escapeHTML(item.name)}</span>
                    <span style="color:${statusColor}; background:${statusBg}; padding:1px 5px; border-radius:3px; font-weight:700; font-size:8px; border:1px solid ${statusColor};">${item.status}</span>
                </div>
                <div style="color:var(--text-secondary); margin-bottom:4px;">${escapeHTML(item.details)}</div>
                ${item.recovery ? `
                    <div style="margin-top:6px; padding:6px; background:rgba(20,163,199,0.05); border-left:2px solid var(--accent-cyan); color:var(--accent-cyan); font-size:9px;">
                        <strong>RECOVERY PLAN:</strong> ${escapeHTML(item.recovery)}
                    </div>
                ` : ''}
            </div>
        `;
    });
    html += `</div>`;
    body.innerHTML = html;

    // Update Badge
    if (errorsCount > 0) {
        summaryBadge.textContent = `${errorsCount} ERRORS · ${warningsCount} WARNINGS`;
        summaryBadge.style.color = "var(--risk-high)";
        body.style.display = "block";
    } else if (warningsCount > 0) {
        summaryBadge.textContent = `${warningsCount} WARNINGS`;
        summaryBadge.style.color = "var(--risk-medium)";
    } else {
        summaryBadge.textContent = "ALL PIPELINES OPERATIONAL (OK)";
        summaryBadge.style.color = "var(--status-success)";
    }
}

function toggleDiagnosticsPanel() {
    const body = document.getElementById("diagnostics-body");
    if (body) {
        body.style.display = body.style.display === "none" ? "block" : "none";
    }
}
window.toggleDiagnosticsPanel = toggleDiagnosticsPanel;


function renderMediaGallery(data) {
    const card = document.getElementById("card-media-gallery");
    const body = document.getElementById("media-gallery-body");
    const badge = document.getElementById("media-gallery-badge");
    if (!card || !body) return;

    const scraped = data.scraped_data || {};
    const mediaItems = [];

    // Profile photos
    const platforms = ["instagram", "linkedin", "tiktok", "twitter", "facebook"];
    platforms.forEach(plat => {
        const info = scraped[plat] || {};
        const pic = info.profile_pic_url || info.profile_pic_hd || (info.basic_info && (info.basic_info.profile_picture_url || info.basic_info.profile_pic_url));
        if (pic) {
            mediaItems.push({
                url: pic,
                source: plat.toUpperCase(),
                type: "Profile Photo",
                caption: `Official profile photo resolved on ${plat.toUpperCase()}`,
                link: info.url || info.profile_url || (info.basic_info && info.basic_info.profile_url) || "#"
            });
        }
    });

    // Instagram posts
    if (scraped.instagram && Array.isArray(scraped.instagram.posts)) {
        scraped.instagram.posts.forEach(post => {
            if (post.display_url) {
                mediaItems.push({
                    url: post.display_url,
                    source: "INSTAGRAM",
                    type: post.media_type || "Post Image",
                    caption: post.caption || "Instagram media post",
                    link: post.url || "#",
                    likes: post.like_count,
                    comments: post.comment_count
                });
            }
        });
    }

    // Facebook cover photo & post media
    if (scraped.facebook) {
        const fb = scraped.facebook;
        if (fb.cover_image_url) {
            mediaItems.push({
                url: fb.cover_image_url,
                source: "FACEBOOK",
                type: "Cover Photo",
                caption: `Facebook cover photo for ${fb.page_name || fb.username || ''}`,
                link: fb.url || "#"
            });
        }
        if (Array.isArray(fb.posts)) {
            fb.posts.forEach(post => {
                if (Array.isArray(post.media)) {
                    post.media.forEach(m => {
                        const imgUri = m.thumbnail || (m.photo_image && m.photo_image.uri) || (m.image && m.image.uri) || (m.placeholder_image && m.placeholder_image.uri);
                        if (imgUri) {
                            mediaItems.push({
                                url: imgUri,
                                source: "FACEBOOK",
                                type: "Post Media",
                                caption: post.text || "Facebook post photo",
                                link: post.url || m.url || "#",
                                likes: post.like_count,
                                comments: post.comment_count
                            });
                        }
                    });
                }
            });
        }
    }

    if (badge) badge.textContent = `${mediaItems.length} FILES`;

    if (mediaItems.length === 0) {
        card.style.display = "none";
        body.innerHTML = "";
        return;
    }

    card.style.display = "block";

    let html = `
        <div style="display:grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap:12px;">
    `;

    mediaItems.forEach(item => {
        const likesHTML = (item.likes != null && !isNaN(item.likes)) ? `❤️ ${Number(item.likes).toLocaleString()} ` : '';
        const commentsHTML = (item.comments != null && !isNaN(item.comments)) ? `💬 ${Number(item.comments).toLocaleString()}` : '';
        const proxyUrl = `${API_BASE}/api/v1/investigation/proxy_image?url=${encodeURIComponent(item.url)}`;
        
        html += `
            <div style="background:var(--bg-elevated); border:1px solid var(--border-divider); border-radius:6px; overflow:hidden; display:flex; flex-direction:column; position:relative;">
                <a href="${item.url}" target="_blank" rel="noopener" style="display:block; height:120px; width:100%; background:var(--bg-panel); overflow:hidden;">
                    <img src="${item.url}" referrerpolicy="no-referrer" style="width:100%; height:100%; object-fit:cover; display:block;" onerror="if(!this.dataset.triedProxy){this.dataset.triedProxy='true';this.src='${proxyUrl}';}else{this.style.display='none';this.parentElement.style.display='flex';this.parentElement.style.alignItems='center';this.parentElement.style.justifyContent='center';this.parentElement.innerHTML='<span style=\\'color:var(--text-muted); font-size:9px; text-align:center;\\'>Image<br>unavailable</span>';}">
                </a>
                <div style="position:absolute; top:6px; left:6px; background:rgba(0,0,0,0.75); border:1px solid var(--accent-cyan); border-radius:3px; padding:2px 5px; font-size:7px; font-weight:700; color:var(--accent-cyan); font-family:monospace; letter-spacing:0.05em;">
                    ${escapeHTML(item.source)}
                </div>
                <div style="padding:8px; display:flex; flex-direction:column; flex:1; justify-content:space-between; font-size:9px; line-height:1.3;">
                    <div style="color:var(--text-primary); max-height:36px; overflow:hidden; text-overflow:ellipsis; display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; margin-bottom:4px;" title="${escapeHTML(item.caption)}">
                        ${escapeHTML(item.caption)}
                    </div>
                    <div style="display:flex; justify-content:space-between; align-items:center; border-top:1px solid var(--border-divider); padding-top:4px; margin-top:4px; color:var(--text-muted); font-size:8px;">
                        <span>${escapeHTML(item.type)}</span>
                        <span>${likesHTML}${commentsHTML}</span>
                    </div>
                </div>
            </div>
        `;
    });

    html += `</div>`;
    body.innerHTML = html;
}


