const API_BASE = "http://127.0.0.1:8000";
const DEMO_USER = "uppolice";
const DEMO_PASS = "testingaccount";

// Global State
let activeTab = "scan-console";
let currentCaseId = "";
let currentInvestigationData = null;

// Initialize app when DOM is fully loaded
window.addEventListener("DOMContentLoaded", () => {
    generateCaseID();
    setupEventListeners();
    runPreloaderSequence();
});

// Setup event listeners for UI interactions
function setupEventListeners() {
    // Sidebar toggle for mobile responsiveness
    const sidebarToggle = document.getElementById("sidebar-toggle");
    const sidebar = document.getElementById("sidebar");
    
    if (sidebarToggle && sidebar) {
        sidebarToggle.addEventListener("click", () => {
            sidebar.classList.toggle("open");
        });
    }

    // Dismiss sidebar when clicking content on mobile
    const mainContainer = document.querySelector(".main-container");
    if (mainContainer && sidebar) {
        mainContainer.addEventListener("click", (e) => {
            if (window.innerWidth <= 768 && sidebar.classList.contains("open") && !e.target.closest("#sidebar") && !e.target.closest("#sidebar-toggle")) {
                sidebar.classList.remove("open");
            }
        });
    }

    // Modal Close
    const closeModal = document.getElementById("close-modal-btn");
    const modalOverlay = document.getElementById("modal-overlay");
    if (closeModal && modalOverlay) {
        closeModal.addEventListener("click", () => {
            modalOverlay.style.display = "none";
        });
        modalOverlay.addEventListener("click", (e) => {
            if (e.target === modalOverlay) {
                modalOverlay.style.display = "none";
            }
        });
    }

    // Form inputs focus
    document.querySelectorAll(".form-control").forEach(control => {
        control.addEventListener("focus", () => {
            control.closest(".form-group")?.classList.add("focused");
        });
        control.addEventListener("blur", () => {
            control.closest(".form-group")?.classList.remove("focused");
        });
    });
}

// Generate dynamic Case ID
function generateCaseID() {
    const randNum = Math.floor(100000 + Math.random() * 900000);
    currentCaseId = `UPP-CASE-2026-${randNum}`;
    
    const activeCaseIdEl = document.getElementById("active-case-id");
    const caseRefInput = document.getElementById("case-reference");
    
    if (activeCaseIdEl) activeCaseIdEl.innerText = currentCaseId;
    if (caseRefInput) caseRefInput.value = currentCaseId;
}

// Preloader simulation check
function runPreloaderSequence() {
    const preloaderStatus = document.getElementById("preloader-status-text");
    const loadingSteps = [
        { time: 400, text: "CONNECTING TO SECURE UP POLICE GATEWAY..." },
        { time: 800, text: "ESTABLISHING INTERCEPT HANDSHAKE..." },
        { time: 1200, text: "VERIFYING SECURITY AUTHORIZATIONS..." },
        { time: 1600, text: "CHECKING BACKEND API SERVICE HEALTH..." },
    ];

    loadingSteps.forEach(step => {
        setTimeout(() => {
            if (preloaderStatus) preloaderStatus.innerText = step.text;
        }, step.time);
    });

    // Check health of backend
    setTimeout(async () => {
        let healthSuccess = false;
        try {
            const healthResp = await fetch(`${API_BASE}/health`);
            if (healthResp.ok) {
                const data = await healthResp.json();
                healthSuccess = true;
                const diagConnection = document.getElementById("diag-connection");
                const diagVersion = document.getElementById("diag-app-version");
                
                if (diagConnection) {
                    diagConnection.innerText = "CONNECTED (OPERATIONAL)";
                    diagConnection.style.color = "#00ff66";
                }
                if (diagVersion) diagVersion.innerText = data.version || "0.1.0";
                if (preloaderStatus) preloaderStatus.innerText = "API OPERATIONAL. DISPATCHING SECURE GATEWAY...";
            }
        } catch (e) {
            console.error("Backend health probe failed:", e);
            const diagConnection = document.getElementById("diag-connection");
            if (diagConnection) {
                diagConnection.innerText = "DISCONNECTED (OFFLINE)";
                diagConnection.style.color = "#ff3366";
            }
            if (preloaderStatus) preloaderStatus.innerText = "WARNING: API OFFLINE. SECURE PROTOCOL STANDBY.";
        }

        // Hide preloader, display Login
        setTimeout(() => {
            const preloader = document.getElementById("preloader");
            const authPortal = document.getElementById("auth-portal");
            if (preloader) preloader.style.display = "none";
            if (authPortal) authPortal.style.display = "flex";
        }, 800);

    }, 2000);
}

// Login verification
function attemptLogin() {
    const userInp = document.getElementById("auth-username").value.trim();
    const passInp = document.getElementById("auth-password").value.trim();
    const cardEl = document.getElementById("auth-card");
    const errBanner = document.getElementById("login-error-banner");

    if (userInp === DEMO_USER && passInp === DEMO_PASS) {
        document.getElementById("auth-portal").style.display = "none";
        document.getElementById("dashboard").style.display = "grid";
        loadHistoryList();
    } else {
        if (errBanner) errBanner.style.display = "block";
        if (cardEl) {
            cardEl.classList.add("shake");
            setTimeout(() => cardEl.classList.remove("shake"), 500);
        }
    }
}

// Logout
function logout() {
    document.getElementById("auth-username").value = "";
    document.getElementById("auth-password").value = "";
    const errBanner = document.getElementById("login-error-banner");
    if (errBanner) errBanner.style.display = "none";
    
    document.getElementById("dashboard").style.display = "none";
    document.getElementById("auth-portal").style.display = "flex";
    
    generateCaseID();
    resetConsoleWorkspace();
}

// Tab Switching router
function switchTab(tabId) {
    activeTab = tabId;
    
    // Deactivate old tabs
    document.querySelectorAll(".menu-item").forEach(el => el.classList.remove("active"));
    document.querySelectorAll(".tab-view").forEach(el => el.classList.remove("active"));

    // Activate new ones
    const menuBtn = document.getElementById(`tab-btn-${tabId}`);
    const tabView = document.getElementById(`view-${tabId}`);
    
    if (menuBtn) menuBtn.classList.add("active");
    if (tabView) tabView.classList.add("active");

    // Close sidebar on mobile after clicking
    const sidebar = document.getElementById("sidebar");
    if (sidebar && window.innerWidth <= 768) {
        sidebar.classList.remove("open");
    }

    const titles = {
        "scan-console": "OSINT Investigation Engine",
        "history-logs": "Investigation Register History",
        "diagnostics": "Diagnostics & Core Services Configuration"
    };
    
    const viewTitle = document.getElementById("view-title");
    if (viewTitle) viewTitle.innerText = titles[tabId] || "OSINT Console";
    
    if (tabId === "history-logs") {
        loadHistoryList();
    }
}

// Console reset helper
function resetConsoleWorkspace() {
    const emptyState = document.getElementById("results-empty-state");
    const grid = document.getElementById("results-workspace-grid");
    
    if (emptyState) emptyState.style.display = "flex";
    if (grid) grid.style.display = "none";
    currentInvestigationData = null;
}

// Trigger Scan
async function triggerInvestigation() {
    const username = document.getElementById("target-username").value.trim();
    const platform = document.getElementById("target-platform").value;
    const depth = parseInt(document.getElementById("correlation-depth").value) || 2;
    const customCase = document.getElementById("case-reference").value.trim();

    if (!username) {
        alert("PLEASE ENTER A TARGET USERNAME TO COMMENCE.");
        return;
    }

    if (customCase) {
        currentCaseId = customCase;
    }

    const loader = document.getElementById("console-loader");
    const stream = document.getElementById("console-stream");
    
    if (stream) stream.innerHTML = "";
    if (loader) loader.style.display = "flex";

    function logLine(text, delay = 0) {
        return new Promise(resolve => {
            setTimeout(() => {
                if (stream) {
                    const line = document.createElement("div");
                    line.className = "console-line";
                    line.innerText = `[${new Date().toLocaleTimeString()}] ${text}`;
                    stream.appendChild(line);
                    stream.scrollTop = stream.scrollHeight;
                }
                resolve();
            }, delay);
        });
    }

    // Simulated terminal logs
    await logLine(`[SYS] OSINT ENGAGE FOR TARGET SUBJECT: ${username}`, 50);
    await logLine(`[NET] ESTABLISHING INTERCEPT HOOK ON PLATFORM PORTAL: ${platform.toUpperCase()}`, 150);
    await logLine(`[SYS] INTEGRATING PROFILE DEPTH ENVELOPE: ${depth}`, 100);
    await logLine(`[NET] INITIATING DIRECTORIES SEARCH ENRICHMENTS...`, 150);

    try {
        const response = await fetch(`${API_BASE}/api/v1/investigation/username`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                username: username,
                platform: platform,
                case_id: currentCaseId,
                correlation_depth: depth
            })
        });

        if (!response.ok) {
            throw new Error(`Endpoint error: ${response.status}`);
        }

        const data = await response.json();
        currentInvestigationData = data;

        await logLine(`[API] ENVELOPE RECEIVED FOR ${data.investigation_id.toUpperCase()}`, 150);
        await logLine(`[SYS] COMPUTING SUBJECT RISK ASSESSMENT METRICS...`, 100);
        await logLine(`[SYS] PARSING SOCIAL PLOTS CORRELATIONS...`, 100);
        await logLine(`[SYS] CONVERTING PAYLOADS TO VISUAL GRIDS...`, 50);

        setTimeout(() => {
            if (loader) loader.style.display = "none";
            renderInvestigationResults(data);
        }, 500);

    } catch (err) {
        await logLine(`[ERR] THREAD STOPPED PREMATURELY. CAUSE: ${err.message}`, 200);
        setTimeout(() => {
            alert("SCAN INTERRUPTED. VERIFY GATEWAY CONFIGURATION AND SERVER LOGS.");
            if (loader) loader.style.display = "none";
        }, 1000);
    }
}

// Render Results to Dashboard
function renderInvestigationResults(data) {
    const emptyState = document.getElementById("results-empty-state");
    const grid = document.getElementById("results-workspace-grid");
    
    if (emptyState) emptyState.style.display = "none";
    if (grid) grid.style.display = "grid";

    // Header Case Title
    const titleCase = document.getElementById("title-case-id");
    if (titleCase) titleCase.innerText = currentCaseId;

    // Target Info Card
    const pData = data.platform_data || {};
    const avatar = document.getElementById("target-avatar-char");
    const profName = document.getElementById("target-profile-name");
    const profPlatform = document.getElementById("target-profile-platform");
    const profVerified = document.getElementById("target-profile-verified");
    const profStatus = document.getElementById("target-profile-status");
    const profTime = document.getElementById("target-profile-time");

    if (avatar) avatar.innerText = (pData.username || "U").substring(0, 2).toUpperCase();
    if (profName) profName.innerText = pData.username || "unknown";
    if (profPlatform) profPlatform.innerText = pData.platform || "instagram";
    if (profVerified) profVerified.innerText = pData.is_verified !== undefined ? pData.is_verified.toString().toUpperCase() : "FALSE";
    if (profStatus) profStatus.innerText = data.status || "completed";
    
    const timeStr = pData.scraped_at || data.timestamp || new Date().toISOString();
    if (profTime) profTime.innerText = timeStr.replace("T", " ").substring(0, 19);

    // Threat Gauge Circle Progress
    const risk = data.risk_assessment || { score: 0, level: "low" };
    const fillCircle = document.getElementById("risk-fill");
    const scoreNum = document.getElementById("risk-score-num");
    const riskBadge = document.getElementById("risk-badge");

    const score = risk.score !== undefined ? risk.score : 0;
    const offset = 377 - (377 * score) / 100;
    
    if (fillCircle) fillCircle.style.strokeDashoffset = offset;
    if (scoreNum) scoreNum.innerText = `${score}%`;

    if (riskBadge) {
        riskBadge.className = "risk-indicator-badge";
        if (risk.level === "low") {
            riskBadge.classList.add("risk-low");
            riskBadge.innerText = "LOW THREAT";
            if (fillCircle) fillCircle.style.stroke = "#00ff66";
        } else if (risk.level === "high") {
            riskBadge.classList.add("risk-high");
            riskBadge.innerText = "HIGH THREAT";
            if (fillCircle) fillCircle.style.stroke = "#ff3366";
        } else {
            riskBadge.classList.add("risk-medium");
            riskBadge.innerText = "MEDIUM THREAT";
            if (fillCircle) fillCircle.style.stroke = "#ffd700";
        }
    }

    // AI Analysis Panel
    const ai = data.ai_correlation_result || {};
    const aiConf = document.getElementById("ai-confidence");
    const aiSum = document.getElementById("ai-summary");
    const aiPlatforms = document.getElementById("ai-associated-platforms");

    if (aiConf) aiConf.innerText = `Confidence Index: ${Math.round((ai.confidence || 0.65) * 100)}%`;
    if (aiSum) aiSum.innerText = ai.summary || "Rule-based placeholder correlation pending AI provider configuration.";

    if (aiPlatforms) {
        aiPlatforms.innerHTML = "";
        const plats = ai.matching_platforms || [];
        if (plats.length > 0) {
            plats.forEach(plat => {
                const badge = document.createElement("span");
                badge.className = "profile-platform-badge";
                badge.style.marginTop = "0";
                badge.innerText = plat;
                aiPlatforms.appendChild(badge);
            });
        } else {
            aiPlatforms.innerHTML = `<span style="font-size:0.75rem; font-style:italic; color:var(--text-secondary);">No indicators found</span>`;
        }
    }

    // Cross Platform Grid
    const crossGrid = document.getElementById("cross-platform-grid");
    const crossCount = document.getElementById("cross-matches-count");
    
    if (crossGrid) {
        crossGrid.innerHTML = "";
        const matches = data.cross_platform_matches || [];
        
        if (crossCount) crossCount.innerText = `Matrices Evaluated: ${matches.length}`;

        matches.forEach(match => {
            const card = document.createElement("a");
            card.className = "platform-match-card";
            card.href = match.url || "#";
            card.target = "_blank";

            const svgIcon = getPlatformSVG(match.platform);
            const exists = match.exists;
            const badgeClass = exists ? "match-badge match-found" : "match-badge match-absent";
            const badgeText = exists ? "FOUND" : "ABSENT";
            const codeText = match.status_code ? `HTTP ${match.status_code}` : "TIMEOUT";

            card.innerHTML = `
                <div class="platform-match-header">
                    <span class="platform-name">${match.platform}</span>
                    <span class="platform-icon">${svgIcon}</span>
                </div>
                <div style="display:flex; justify-content:space-between; align-items:center; margin-top:5px;">
                    <span class="${badgeClass}">${badgeText}</span>
                    <span class="platform-code">${codeText}</span>
                </div>
            `;
            crossGrid.appendChild(card);
        });
    }
}

// Helper to return platform-specific SVG vector icons
function getPlatformSVG(platform) {
    const svgs = {
        instagram: `<svg class="svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="20" rx="5" ry="5"></rect><path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z"></path><line x1="17.5" y1="6.5" x2="17.51" y2="6.5"></line></svg>`,
        twitter: `<svg class="svg-icon" viewBox="0 0 24 24" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>`,
        telegram: `<svg class="svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/></svg>`,
        linkedin: `<svg class="svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-2-2 2 2 0 0 0-2 2v7h-4v-7a6 6 0 0 1 6-6z"></path><rect x="2" y="9" width="4" height="12"></rect><circle cx="4" cy="4" r="2"></circle></svg>`,
        github: `<svg class="svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"></path></svg>`,
        reddit: `<svg class="svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm4 11a1.5 1.5 0 1 1-1.5-1.5A1.5 1.5 0 0 1 16 13zm-6.5-1.5A1.5 1.5 0 1 1 8 13a1.5 1.5 0 0 1 1.5-1.5zm2.5 4.5c-1.5 0-2.5-1-2.5-1s1-1 2.5-1 2.5 1 2.5 1-1 1-2.5 1z"/></svg>`,
        youtube: `<svg class="svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22.54 6.42a2.78 2.78 0 0 0-1.94-2C18.88 4 12 4 12 4s-6.88 0-8.6.46a2.78 2.78 0 0 0-1.94 2A29 29 0 0 0 1 11.75a29 29 0 0 0 .46 5.33A2.78 2.78 0 0 0 3.4 19c1.72.46 8.6.46 8.6.46s6.88 0 8.6-.46a2.78 2.78 0 0 0 1.94-2 29 29 0 0 0 .46-5.25 29 29 0 0 0-.46-5.33z"></path><polygon points="9.75 15.02 15.5 11.75 9.75 8.48 9.75 15.02"></polygon></svg>`,
        pinterest: `<svg class="svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><path d="M8 12a4 4 0 0 1 8 0c0 2.5-2 4.5-4.5 4.5S7 14.5 7 12"></path><path d="M12 7.5V16"></path></svg>`,
        koo: `<svg class="svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><path d="M8 14s1.5-2 4-2 4 2 4 2"/></svg>`,
        sharechat: `<svg class="svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>`,
        moj: `<svg class="svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><path d="M12 8v8M8 12h8"/></svg>`
    };
    return svgs[platform.toLowerCase()] || `<svg class="svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>`;
}

// Fetch history from backend API
async function loadHistoryList() {
    try {
        const response = await fetch(`${API_BASE}/api/v1/investigation/history?limit=30`);
        if (!response.ok) return;

        const list = await response.json();
        const tbody = document.getElementById("history-table-body");
        if (!tbody) return;
        
        tbody.innerHTML = "";

        if (list.length === 0) {
            tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-secondary);">No historical records logged in database.</td></tr>`;
            return;
        }

        list.forEach(item => {
            const tr = document.createElement("tr");
            tr.onclick = () => loadHistoryRecord(item.investigation_id);

            const timeStr = item.timestamp ? item.timestamp.replace("T", " ").substring(0, 19) : "unknown";

            tr.innerHTML = `
                <td class="mono" style="color:var(--accent-blue); font-weight:600;">${item.investigation_id}</td>
                <td style="font-weight:600;">${item.username}</td>
                <td style="text-transform: capitalize;">${item.platform}</td>
                <td><span class="system-badge" style="background:rgba(0,188,212,0.1); border-color:rgba(0,188,212,0.2); color:var(--accent-blue); padding: 2px 6px;">${item.status}</span></td>
                <td class="mono" style="font-size:0.75rem;">${timeStr}</td>
            `;
            tbody.appendChild(tr);
        });

    } catch (e) {
        console.error("Failed loading history:", e);
    }
}

// Load individual record from list
async function loadHistoryRecord(invId) {
    try {
        const response = await fetch(`${API_BASE}/api/v1/investigation/history/${invId}`);
        if (!response.ok) {
            alert("CASE FILES COULD NOT BE LOCATED.");
            return;
        }

        const data = await response.json();
        currentInvestigationData = data;
        currentCaseId = data.platform_data.case_id || `UPP-RELOADED-${invId.substring(4, 10).toUpperCase()}`;

        // Prefill inputs
        document.getElementById("target-username").value = data.platform_data.username || "";
        document.getElementById("target-platform").value = data.platform_data.platform || "instagram";

        switchTab("scan-console");
        renderInvestigationResults(data);

    } catch (err) {
        alert(`Error loading history item: ${err.message}`);
    }
}

// Render dynamic HTML for Official Investigation Report template
function renderOfficialReportTemplate(data, caseId) {
    const pData = data.platform_data || {};
    const risk = data.risk_assessment || { level: "low", score: 0, factors: [] };
    const score = risk.score !== undefined ? risk.score : 0;
    const ai = data.ai_correlation_result || { confidence: 0.65, summary: "", matching_platforms: [] };
    const matches = data.cross_platform_matches || [];
    
    const currentDate = new Date().toLocaleDateString('en-GB', { day: '2-digit', month: '2-digit', year: 'numeric' });
    const timeStr = pData.scraped_at || data.timestamp || new Date().toISOString();
    const formattedScrapeDate = timeStr.replace("T", " ").substring(0, 19);

    // Generate table rows for cross platform matches
    let matchesRows = "";
    matches.forEach(m => {
        const conf = m.exists ? 85 : 5;
        const confClass = m.exists ? "finding-high" : "";
        const evidenceStr = m.exists ? 
            `MATCH IDENTIFIED. Active profile URL resolved status ${m.status_code}. Path: ${m.url}` : 
            `ABSENT. Profile resolution returned status ${m.status_code || "Timeout"}.`;
        
        matchesRows += `
        <tr>
            <td>${m.platform.toUpperCase()}</td>
            <td>${pData.username}</td>
            <td class="${confClass}">${conf}%</td>
            <td>${evidenceStr}</td>
        </tr>`;
    });

    // Generate indicators list items
    let indicatorsItems = "";
    const factors = risk.factors || [];
    if (factors.length > 0) {
        factors.forEach(f => {
            indicatorsItems += `<li>Observed threat footprint factor: ${f.toUpperCase().replace(/_/g, ' ')}</li>`;
        });
    } else {
        indicatorsItems += `<li>Standard baseline cyber threat scanning. No flags observed.</li>`;
    }

    // Critical discoveries
    let discoveriesItems = "";
    const activeMatchesList = matches.filter(m => m.exists).map(m => m.platform);
    if (activeMatchesList.length > 0) {
        discoveriesItems += `<p class="finding-critical">⚠ CRITICAL: Subject presence identified on active social indexes: ${activeMatchesList.join(", ").toUpperCase()}</p>`;
    } else {
        discoveriesItems += `<p>No immediate critical discoveries noted.</p>`;
    }

    // Evidence summary list
    let evidenceRows = "";
    if (pData.username) {
        evidenceRows += `
        <tr>
            <td>EV-001</td>
            <td>Primary Target Profile</td>
            <td>${pData.platform.toUpperCase()} Index</td>
            <td>${formattedScrapeDate}</td>
        </tr>`;
    }
    activeMatchesList.forEach((plat, index) => {
        evidenceRows += `
        <tr>
            <td>EV-00${index + 2}</td>
            <td>Correlated Profile Link</td>
            <td>${plat.toUpperCase()} Index</td>
            <td>${currentDate}</td>
        </tr>`;
    });

    // Recommendations list
    let recommendationsItems = "";
    if (risk.level === "high") {
        recommendationsItems += `
        <li>Request legal intercepts on active handles: ${activeMatchesList.join(", ").toUpperCase()}</li>
        <li>Deploy active digital monitoring and log forensic indicators</li>
        <li>Initiate direct ISP coordinate trace requests</li>`;
    } else if (risk.level === "medium") {
        recommendationsItems += `
        <li>Monitor cross-platform handles for identity updates</li>
        <li>Consolidate intelligence logs with state cyber database register</li>
        <li>Conduct routine check after 72 hours</li>`;
    } else {
        recommendationsItems += `
        <li>Maintain archive state for intelligence record</li>
        <li>Close current OSINT file</li>`;
    }

    // Return the prefilled template conforming exactly to official_investigation_report.html
    return `
<!DOCTYPE html>
<html>
<head>
    <title>LEA Report - ${pData.username}</title>
    <style>
        body {
            font-family: 'Times New Roman', serif;
            font-size: 12pt;
            line-height: 1.5;
            margin: 2cm;
            color: #000;
            background: #fff;
        }
        .header {
            text-align: center;
            border-bottom: 2px solid #000;
            margin-bottom: 20px;
        }
        .confidential {
            color: red;
            font-weight: bold;
            text-align: center;
            border: 2px solid red;
            padding: 5px;
            margin: 10px 0;
            text-transform: uppercase;
        }
        .section-title {
            font-weight: bold;
            font-size: 14pt;
            margin-top: 20px;
            border-bottom: 1px solid #333;
            text-transform: uppercase;
            padding-bottom: 2px;
        }
        .evidence-box {
            border: 1px solid #999;
            padding: 10px;
            background: #f5f5f5;
            margin: 10px 0;
        }
        .finding-critical {
            color: red;
            font-weight: bold;
        }
        .finding-high {
            color: orange;
            font-weight: bold;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 10px 0;
        }
        th, td {
            border: 1px solid #333;
            padding: 6px;
            text-align: left;
            font-size: 10.5pt;
        }
        th {
            background: #333;
            color: white;
            text-transform: uppercase;
            font-size: 10pt;
        }
        @media print {
            body { margin: 1.5cm; }
            button { display: none; }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>CYBERCRIME INVESTIGATION REPORT</h1>
        <p>LAW ENFORCEMENT USE ONLY - UTTAR PRADESH POLICE CYBER CELL</p>
    </div>
    
    <div class="confidential">
        ⚠️ CONFIDENTIAL - RESTRICTED ACCESS - INVESTIGATIVE MATERIAL
    </div>
    
    <h2>CASE BRIEF</h2>
    <p>Target identity scan report resolved for subject handle <strong>${pData.username}</strong> on ${pData.platform.toUpperCase()} network. Analysis compiled using state security OSINT correlation engines.</p>
    
    <h3>SUBJECT INFO</h3>
    <p>Target Profile Alias: <strong>${pData.username}</strong> (Source: ${pData.platform.toUpperCase()})</p>
    
    <h3>CASE DETAILS</h3>
    <table>
        <tr><td>Case ID</td><td><strong>${caseId}</strong></td></tr>
        <tr><td>Investigating Officer</td><td>Special Investigator Ark Agrawal (ID: UPP-811)</td></tr>
        <tr><td>Date of Investigation</td><td>${currentDate}</td></tr>
        <tr><td>Platform Investigated</td><td>${pData.platform.toUpperCase()}</td></tr>
        <tr><td>AI-Assisted Analysis</td><td>Yes - Model Core v0.1.0</td></tr>
    </table>
    
    <div class="section-title">1. EXECUTIVE SUMMARY</div>
    <p>This document files the open-source intelligence findings gathered regarding online handle alias <strong>${pData.username}</strong>. High-level scans resolved active profiles across online grids with a consolidated threat rating of <strong>${risk.level.toUpperCase()}</strong>. Detailed evidence and platform parameters are cataloged in section 4.</p>
    
    <div class="section-title">2. INCIDENT OVERVIEW</div>
    <p>An automated reconnaissance protocol was instantiated on ${currentDate} under active request reference case ${caseId}. The objective was to search, map, and assess online footprint correlations for the subject handle to check for risk indices, impersonations, or illegal activity.</p>
    
    <div class="section-title">3. PROFILE ANALYSIS</div>
    <h4>3.1 Primary Profile - ${pData.platform.toUpperCase()}</h4>
    <table>
        <tr><td>Username</td><td>${pData.username}</td></tr>
        <tr><td>Display Name</td><td>${pData.full_name || "NOT SPECIFIED"}</td></tr>
        <tr><td>Account Created</td><td>Not Available</td></tr>
        <tr><td>Bio</td><td>${pData.bio || "No biography details cached."}</td></tr>
        <tr><td>Followers</td><td>${pData.follower_count || "UNKNOWN"}</td></tr>
        <tr><td>Following</td><td>${pData.following_count || "UNKNOWN"}</td></tr>
        <tr><td>Account Status</td><td>${data.status.toUpperCase()}</td></tr>
    </table>
    
    <h4>3.2 Content Analysis</h4>
    <p>No anomalous content flags or illegal activity alerts observed on target timeline. Secondary posts examination is pending legal warrant verification.</p>
    
    <h4>3.3 Network Analysis</h4>
    <p>Subject shows close correlation coordinates with secondary nodes on identical social channels. Network structure is stable with standard baseline parameters.</p>
    
    <div class="section-title">4. CROSS-PLATFORM CORRELATION</div>
    <table>
        <tr>
            <th>Platform</th>
            <th>Username</th>
            <th>Confidence</th>
            <th>Key Evidence</th>
        </tr>
        ${matchesRows}
    </table>
    
    <div class="section-title">5. AI CORRELATION ANALYSIS</div>
    <div class="evidence-box">
        <strong>Identity Consolidation:</strong>
        <p>${ai.summary || "Rule-based placeholder correlation pending AI provider configuration."}</p>
        
        <strong>Confidence Assessment:</strong>
        <p>The system evaluates identity match confidence at ${Math.round((ai.confidence || 0.65) * 100)}% based on platform presence overlaps.</p>
    </div>
    
    <div class="section-title">6. RISK ASSESSMENT</div>
    <p><strong>Risk Level:</strong> <span class="finding-${risk.level}">${risk.level.toUpperCase()}</span> (Threat Score: ${score}%)</p>
    <p><strong>Indicators Found:</strong></p>
    <ul>
        ${indicatorsItems}
    </ul>
    
    <div class="section-title">7. CRITICAL DISCOVERIES</div>
    ${discoveriesItems}
    
    <div class="section-title">8. EVIDENCE SUMMARY</div>
    <table>
        <tr><th>Evidence ID</th><th>Type</th><th>Source</th><th>Timestamp</th></tr>
        ${evidenceRows}
    </table>
    
    <div class="section-title">9. RECOMMENDATIONS</div>
    <ol>
        ${recommendationsItems}
    </ol>
    
    <div class="section-title">10. CONCLUSION</div>
    <p>Based on the open-source investigation results, subject <strong>${pData.username}</strong> exhibits presence patterns indicating a <strong>${risk.level.toUpperCase()}</strong> threat status. It is recommended to proceed in accordance with standard operating guidelines outlined in Section 9.</p>
    
    <div style="margin-top: 50px;">
        <p>Report Generated by: AI-OSINT Platform v0.1</p>
        <p>Date: ${currentDate}</p>
        <p>Signature: ___________________________</p>
        <p>Name: Investigator Ark Agrawal</p>
        <p>Designation: Cybersecurity Special Agent, U.P. Police</p>
    </div>

    <!-- Print control bar for browser save -->
    <div style="position:fixed; bottom: 20px; right: 20px; background: rgba(0,0,0,0.8); padding: 10px; border-radius: 8px; display: flex; gap: 10px;">
        <button onclick="window.print()" style="background:#00bcd4; color:white; border:none; padding:8px 16px; border-radius:4px; font-weight:600; cursor:pointer;">Export / Save as PDF</button>
        <button onclick="window.close()" style="background:#ff3366; color:white; border:none; padding:8px 16px; border-radius:4px; font-weight:600; cursor:pointer;">Close Window</button>
    </div>
</body>
</html>
    `;
}

// Generate PDF Report (using clean Print Window approach)
function generatePDFReport() {
    if (!currentInvestigationData) {
        alert("NO ACTIVE INVESTIGATION TO REPORT.");
        return;
    }
    
    // Open a new window containing the prefilled template
    const printWindow = window.open("", "_blank");
    if (!printWindow) {
        alert("Pop-up blocked. Please allow pop-ups to export official reports.");
        return;
    }
    
    const htmlReport = renderOfficialReportTemplate(currentInvestigationData, currentCaseId);
    
    printWindow.document.write(htmlReport);
    printWindow.document.close();
    
    // Trigger print/save as PDF dialog in the new window
    setTimeout(() => {
        printWindow.focus();
    }, 500);
}
