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

    const steps = [
        { p: 12, msg: "Initializing WhatsMyName 700+ cross-platform probe engine..." },
        { p: 28, msg: "Scraping public profiles (Instagram, Facebook, TikTok)..." },
        { p: 45, msg: "Querying SignalHire candidate enrichment API for LinkedIn..." },
        { p: 62, msg: "Executing Google Search Dorking queries via SerpAPI..." },
        { p: 78, msg: "Searching Telegram CTI darkweb & leak databases..." },
        { p: 90, msg: "Running AI multi-source behavioral classifier..." },
        { p: 98, msg: "Synthesizing Consolidated Identity & associated accounts matrix..." },
    ];

    let stepIdx = 0;
    let currentPct = 0;

    clearInterval(progressInterval);
    progressInterval = setInterval(() => {
        if (stepIdx < steps.length) {
            const targetPct = steps[stepIdx].p;
            if (currentPct < targetPct) {
                currentPct += 1;
                if (bar) bar.style.width = currentPct + "%";
                if (pct) pct.textContent = currentPct + "%";
            } else {
                if (text) text.textContent = steps[stepIdx].msg;
                logConsole(`[PROBE] ${steps[stepIdx].msg}`);
                stepIdx++;
            }
        }
    }, 180);
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
    renderAiPersonality(data.ai_personality);
    renderWmnMatrix(data.wmn_results);
    renderAssociatedAccounts(data.associated_accounts);
    renderGoogleDorking(data.dorking_results);
    renderTelegramCTI(data.telegram_cti);
    renderPlatformDossiers(data.scraped_data);
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

    body.innerHTML = `
        <table class="soc-table" style="margin-bottom:12px;">
            <tr><td style="width:25%; color:var(--text-muted);">Likely Full Name</td><td><strong>${escapeHTML(ci.likely_name || "N/A")}</strong></td></tr>
            <tr><td style="color:var(--text-muted);">Location</td><td>${escapeHTML(ci.location || "N/A")}</td></tr>
            <tr><td style="color:var(--text-muted);">Behavioral Category</td><td><span class="tag-chip interest">${escapeHTML(ci.profession || "N/A")}</span></td></tr>
        </table>
        <div style="margin-bottom:8px;">
            <div style="font-size:11px; font-weight:600; color:var(--text-muted); margin-bottom:4px;">VERIFIED &amp; PATTERN-CHECKED EMAILS</div>
            <div>${emailsHTML || "<span style='color:var(--text-muted);'>None</span>"}</div>
        </div>
        <div>
            <div style="font-size:11px; font-weight:600; color:var(--text-muted); margin-bottom:4px;">DISCOVERED PROFILE LINKS (${(ci.links || []).length} DISCOVERED)</div>
            <div>${linksHTML || "<span style='color:var(--text-muted);'>None</span>"}</div>
        </div>
    `;
}

// 2. AI Behavioral Profile
function renderAiPersonality(ap) {
    const body = document.getElementById("ai-personality-body");
    const catBadge = document.getElementById("ai-category-badge");
    if (!body) return;
    if (!ap) { body.innerHTML = "<div style='color:var(--text-muted);'>No AI profile data available.</div>"; return; }

    if (catBadge) {
        catBadge.textContent = `${ap.primaryCategory || "Unclassified"} · ${ap.confidence || 0}%`;
    }

    const traitsHTML = (ap.traits || []).map(t => `<span class="tag-chip">${escapeHTML(t)}</span>`).join("");
    const interestsHTML = (ap.interests || []).map(i => `<span class="tag-chip interest">${escapeHTML(i)}</span>`).join("");

    const riskFlagsHTML = (ap.riskFlags || []).map(f => `
        <span class="risk-badge ${f.severity || 'low'}">${f.severity ? f.severity.toUpperCase() : 'LOW'}: ${escapeHTML(f.label)}</span>
    `).join("");

    body.innerHTML = `
        <div style="font-size:13px; color:var(--text-primary); margin-bottom:14px; line-height:1.6;">${escapeHTML(ap.summary)}</div>
        <div style="margin-bottom:10px;">
            <div style="font-size:11px; color:var(--text-muted); font-weight:600; margin-bottom:4px;">BEHAVIORAL TRAITS</div>
            <div>${traitsHTML || "<span style='color:var(--text-muted);'>None</span>"}</div>
        </div>
        <div style="margin-bottom:10px;">
            <div style="font-size:11px; color:var(--text-muted); font-weight:600; margin-bottom:4px;">DETECTED INTERESTS</div>
            <div>${interestsHTML || "<span style='color:var(--text-muted);'>None</span>"}</div>
        </div>
        <div>
            <div style="font-size:11px; color:var(--text-muted); font-weight:600; margin-bottom:4px;">RISK FLAGS</div>
            <div>${riskFlagsHTML || "<span style='color:var(--status-success); font-size:12px;'>No risk flags identified.</span>"}</div>
        </div>
    `;
}

// 3. WhatsMyName Probe Matrix
function renderWmnMatrix(wmn) {
    const body = document.getElementById("wmn-matrix-body");
    const badge = document.getElementById("wmn-count-badge");
    if (!body) return;
    const hits = wmn?.hits || [];

    if (badge) badge.textContent = `${hits.length} FOUND / ${wmn?.scanned || 0} SCANNED`;

    if (!hits.length) {
        body.innerHTML = "<div style='color:var(--text-muted); font-size:12px;'>No WMN template hits found.</div>";
        return;
    }

    const rows = hits.map(h => `
        <tr>
            <td style="font-weight:600; color:var(--accent-cyan); white-space:nowrap;">${escapeHTML(h.site)}</td>
            <td><span class="tag-chip">${escapeHTML(h.category)}</span></td>
            <td class="mono" style="color:var(--status-success); white-space:nowrap;">FOUND &nbsp;${h.ms}ms</td>
            <td class="mono"><a href="${escapeHTML(h.url)}" target="_blank" style="color:var(--accent-cyan); text-decoration:none; word-break:break-all;">${escapeHTML(h.url)} &#x2197;</a></td>
        </tr>
    `).join("");

    body.innerHTML = `<div class="table-scroll">
        <table class="soc-table">
            <thead><tr><th>Platform</th><th>Category</th><th>Probe Status</th><th>Profile URL</th></tr></thead>
            <tbody>${rows}</tbody>
        </table></div>`;
}

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

    // LinkedIn SignalHire Dossier
    if (scraped.linkedin) {
        const li = scraped.linkedin;
        cardsHTML += `
            <div style="background:var(--bg-elevated); border:1px solid var(--border-divider); border-radius:6px; padding:14px; margin-bottom:14px;">
                <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
                    <span style="font-weight:600; color:var(--accent-cyan);">LINKEDIN (SIGNALHIRE ENRICHMENT)</span>
                    <span class="mono" style="font-size:11px;">${escapeHTML(li.url || "")}</span>
                </div>
                <div style="font-size:13px; margin-bottom:6px;"><strong>Candidate Name:</strong> ${escapeHTML(li.full_name || "N/A")} | <strong>Company:</strong> ${escapeHTML(li.company || "N/A")}</div>
                <div style="font-size:12px; color:var(--text-secondary); margin-bottom:6px;"><strong>Headline:</strong> ${escapeHTML(li.headline || "N/A")} | <strong>Location:</strong> ${escapeHTML(li.location || "N/A")}</div>
                <div style="font-size:12px;">
                    <strong>Emails:</strong> ${(li.emails || []).map(e => `<span class="tag-chip interest">${escapeHTML(e)}</span>`).join("") || "None"}
                </div>
            </div>
        `;
    }

    // Facebook Dossier
    if (scraped.facebook) {
        const fb = scraped.facebook;
        cardsHTML += `
            <div style="background:var(--bg-elevated); border:1px solid var(--border-divider); border-radius:6px; padding:14px; margin-bottom:14px;">
                <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
                    <span style="font-weight:600; color:var(--accent-cyan);">FACEBOOK PAGE DOSSIER</span>
                    <span class="mono" style="font-size:11px;">${escapeHTML(fb.page_name || fb.username)}</span>
                </div>
                <div style="font-size:13px; margin-bottom:6px;"><strong>Page Title:</strong> ${escapeHTML(fb.title || fb.page_name)}</div>
                <div style="font-size:12px; color:var(--text-secondary);">${escapeHTML(fb.bio || "Public Facebook page.")}</div>
            </div>
        `;
    }

    body.innerHTML = cardsHTML || "<div style='color:var(--text-muted);'>No dossier details.</div>";
}
