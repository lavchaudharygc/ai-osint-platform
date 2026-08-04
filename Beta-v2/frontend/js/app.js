/**
 * UP Police Cyber Cell — OSINT SOC Engine (Beta-v2) Frontend Core
 */

const API_BASE = "http://127.0.0.1:8010";
let currentInvestigationData = null;

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
    email: "📧 EMAIL",
    phone: "📱 PHONE",
    domain: "🌐 DOMAIN",
    name: "🔍 FULL NAME",
    username: "👤 USERNAME",
};

function detectInputType(value) {
    const badge = document.getElementById("input-kind-badge");
    if (!badge) return;
    if (!value.trim()) { badge.style.display = "none"; return; }
    const { kind } = classifyInput(value);
    badge.textContent = KIND_LABELS[kind] || kind.toUpperCase();
    badge.style.display = "inline-block";
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

/* ---------- Main Investigation Execution ---------- */
async function executeScan() {
    const usernameInput = document.getElementById("target-username").value.trim();
    if (!usernameInput) {
        alert("PLEASE ENTER A TARGET USERNAME / IDENTIFIER.");
        return;
    }

    const { kind } = classifyInput(usernameInput);
    const emailVal = document.getElementById("provider-email").value.trim();
    const phoneVal = document.getElementById("provider-phone").value.trim();

    const payload = {
        username: usernameInput,
        email: emailVal || null,
        phone_number: phoneVal || null,
        cache_mode: "use",
    };

    // UI Loading state
    document.getElementById("results-empty-state").style.display = "none";
    document.getElementById("results-workspace").style.display = "block";

    logConsole(`[SYS] OSINT DISPATCH — TARGET: ${usernameInput} (${kind.toUpperCase()})`);
    logConsole("[NET] PROBING WHATSMYNAME 700+ SITE TEMPLATES...");

    const heartbeatMsgs = [
        "[SYS] Probing active platform presences...",
        "[NET] Querying SignalHire candidate API for LinkedIn...",
        "[SYS] Verifying email MX deliverability records...",
        "[NET] Executing Google search dork queries via SerpAPI...",
        "[SYS] Querying Telegram CTI leak databases...",
        "[NET] Running AI behavioral classification engine...",
        "[SYS] Synthesizing Consolidated Identity Profile..."
    ];
    let msgIdx = 0;
    const heartbeat = setInterval(() => {
        if (msgIdx < heartbeatMsgs.length) logConsole(heartbeatMsgs[msgIdx++]);
    }, 2500);

    try {
        const res = await fetch(`${API_BASE}/api/v1/investigation/username`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        clearInterval(heartbeat);

        if (!res.ok) {
            throw new Error(`API Error HTTP ${res.status}`);
        }

        const data = await res.json();
        currentInvestigationData = data;

        logConsole(`[SYS] ENVELOPE RECEIVED — CASE ID: ${data.investigation_id}`);
        logConsole("[SYS] RENDERING HIGH-DENSITY SOC WORKSPACE...");

        renderResults(data);
    } catch (err) {
        clearInterval(heartbeat);
        logConsole(`[ERR] SCAN INTERRUPTED: ${err.message}`);
        alert(`OSINT Scan Interrupted: ${err.message}`);
    }
}

/* ---------- Rendering Engine ---------- */
function renderResults(data) {
    renderConsolidatedIdentity(data.consolidated_identity);
    renderAiPersonality(data.ai_personality);
    renderWmnMatrix(data.wmn_results);
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
            <div style="font-size:11px; font-weight:600; color:var(--text-muted); margin-bottom:4px;">DISCOVERED PROFILE LINKS</div>
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
            <td style="font-weight:600; color:var(--accent-cyan);">${escapeHTML(h.site)}</td>
            <td><span class="tag-chip">${escapeHTML(h.category)}</span></td>
            <td class="mono" style="color:var(--status-success);">FOUND (${h.ms}ms)</td>
            <td class="mono"><a href="${escapeHTML(h.url)}" target="_blank" style="color:var(--accent-cyan); text-decoration:none;">${escapeHTML(h.url)} ↗</a></td>
        </tr>
    `).join("");

    body.innerHTML = `
        <table class="soc-table">
            <thead>
                <tr><th>Platform</th><th>Category</th><th>Probe Status</th><th>Profile URL</th></tr>
            </thead>
            <tbody>${rows}</tbody>
        </table>
    `;
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
            <td><span class="tag-chip">${escapeHTML(r.category)}</span></td>
            <td><a href="${escapeHTML(r.url)}" target="_blank" style="color:var(--text-primary); font-weight:600; text-decoration:none;">${escapeHTML(r.title)} ↗</a><br><span class="mono" style="font-size:10px; color:var(--text-muted);">${escapeHTML(r.domain)}</span></td>
            <td style="color:var(--text-secondary); font-size:11px;">${escapeHTML(r.snippet)}</td>
            <td class="mono" style="font-size:10px; color:var(--accent-cyan);">${escapeHTML(r.query)}</td>
        </tr>
    `).join("");

    body.innerHTML = `
        <table class="soc-table">
            <thead>
                <tr><th>Category</th><th>Title / Domain</th><th>Snippet Preview</th><th>Query Used</th></tr>
            </thead>
            <tbody>${rows}</tbody>
        </table>
    `;
}

// 5. Telegram CTI Breach Intelligence
function renderTelegramCTI(cti) {
    const body = document.getElementById("telegram-cti-body");
    const badge = document.getElementById("cti-records-badge");
    if (!body) return;
    const records = cti?.total_records || 0;

    if (badge) badge.textContent = `${records} COMPROMISED RECORDS`;

    if (!records) {
        body.innerHTML = "<div style='color:var(--status-success); font-size:12px;'>No breach records found in leak databases.</div>";
        return;
    }

    const results = cti?.results || [];
    let rows = "";
    results.forEach(res => {
        const raw = res.raw || {};
        const dbs = raw.results || [];
        dbs.forEach(db => {
            const dbName = db.database || "Leak DB";
            (db.data || []).forEach(item => {
                rows += `
                    <tr>
                        <td style="font-weight:600; color:var(--risk-critical);">${escapeHTML(dbName)}</td>
                        <td class="mono">${escapeHTML(item.email || item.username || item.phone || "-")}</td>
                        <td class="mono" style="color:var(--risk-medium);">${escapeHTML(item.password || item.pass || "*****")}</td>
                        <td class="mono" style="font-size:10px;">${escapeHTML(JSON.stringify(item).slice(0, 80))}</td>
                    </tr>
                `;
            });
        });
    });

    body.innerHTML = `
        <table class="soc-table">
            <thead>
                <tr><th>Database</th><th>Compromised Subject</th><th>Leak Payload / Pass</th><th>Raw Details</th></tr>
            </thead>
            <tbody>${rows || "<tr><td colspan='4'>No records mapped.</td></tr>"}</tbody>
        </table>
    `;
}

// 6. Platform Dossiers
function renderPlatformDossiers(scraped) {
    const body = document.getElementById("platform-dossiers-body");
    if (!body) return;
    if (!scraped || Object.keys(scraped).length === 0) {
        body.innerHTML = "<div style='color:var(--text-muted);'>No platform dossier data cached.</div>";
        return;
    }

    let cardsHTML = "";

    // Instagram Dossier
    if (scraped.instagram) {
        const ig = scraped.instagram;
        const tagsHTML = (ig.post_hashtags || []).map(t => `<span class="tag-chip interest">#${escapeHTML(t)}</span>`).join("");
        cardsHTML += `
            <div style="background:var(--bg-elevated); border:1px solid var(--border-divider); border-radius:6px; padding:12px; margin-bottom:12px;">
                <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
                    <span style="font-weight:600; color:var(--accent-cyan);">📸 INSTAGRAM DOSSIER</span>
                    <span class="mono" style="font-size:11px;">@${escapeHTML(ig.username)}</span>
                </div>
                <div style="font-size:13px; margin-bottom:6px;"><strong>Name:</strong> ${escapeHTML(ig.full_name || "N/A")} | <strong>Followers:</strong> ${ig.follower_count || 0}</div>
                <div style="font-size:12px; color:var(--text-secondary); margin-bottom:8px;">${escapeHTML(ig.bio || "No bio.")}</div>
                <div>
                    <div style="font-size:10px; font-weight:600; color:var(--text-muted); margin-bottom:4px;">POST HASHTAGS EXRACTED</div>
                    <div>${tagsHTML || "<span style='color:var(--text-muted); font-size:11px;'>No hashtags extracted.</span>"}</div>
                </div>
            </div>
        `;
    }

    // LinkedIn SignalHire Dossier
    if (scraped.linkedin) {
        const li = scraped.linkedin;
        cardsHTML += `
            <div style="background:var(--bg-elevated); border:1px solid var(--border-divider); border-radius:6px; padding:12px; margin-bottom:12px;">
                <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
                    <span style="font-weight:600; color:var(--accent-cyan);">💼 LINKEDIN (SIGNALHIRE ENRICHMENT)</span>
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
            <div style="background:var(--bg-elevated); border:1px solid var(--border-divider); border-radius:6px; padding:12px; margin-bottom:12px;">
                <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
                    <span style="font-weight:600; color:var(--accent-cyan);">📘 FACEBOOK PAGE DOSSIER</span>
                    <span class="mono" style="font-size:11px;">${escapeHTML(fb.page_name || fb.username)}</span>
                </div>
                <div style="font-size:13px; margin-bottom:6px;"><strong>Page Title:</strong> ${escapeHTML(fb.title || fb.page_name)}</div>
                <div style="font-size:12px; color:var(--text-secondary);">${escapeHTML(fb.bio || "Public Facebook page.")}</div>
            </div>
        `;
    }

    body.innerHTML = cardsHTML || "<div style='color:var(--text-muted);'>No dossier details.</div>";
}
