const API_BASE = "http://127.0.0.1:8010";
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
    // Sidebar toggle for mobile responsiveness and desktop collapsing
    const sidebarToggle = document.getElementById("sidebar-toggle");
    const sidebar = document.getElementById("sidebar");
    const dashboard = document.getElementById("dashboard");
    
    if (sidebarToggle && sidebar && dashboard) {
        sidebarToggle.addEventListener("click", () => {
            if (window.innerWidth <= 768) {
                sidebar.classList.toggle("open");
            } else {
                dashboard.classList.toggle("collapsed");
            }
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

    // Reindex Hi-Tek button
    const btnReindex = document.getElementById("btn-reindex-hitek");
    if (btnReindex) {
        btnReindex.addEventListener("click", async () => {
            btnReindex.disabled = true;
            btnReindex.innerText = "INDEXING INITIATED...";
            try {
                const resp = await fetch(`${API_BASE}/api/v1/investigation/hitek/index`, { method: "POST" });
                if (resp.ok) {
                    alert("Indexing started in the background. Check diagnostics for progress.");
                    // Poll every 2 seconds
                    const pollInterval = setInterval(async () => {
                        await updateHiTekDiagnostics();
                        const statusEl = document.getElementById("diag-hitek-index-status");
                        if (statusEl && statusEl.innerText !== "INDEXING") {
                            clearInterval(pollInterval);
                            btnReindex.disabled = false;
                            btnReindex.innerText = "REBUILD INDEX";
                        }
                    }, 2000);
                } else {
                    alert("Failed to start indexing.");
                    btnReindex.disabled = false;
                    btnReindex.innerText = "REBUILD INDEX";
                }
            } catch (e) {
                alert(`Error: ${e.message}`);
                btnReindex.disabled = false;
                btnReindex.innerText = "REBUILD INDEX";
            }
        });
    }
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
                
                // Initialize Hi-Tek Diagnostics status
                updateHiTekDiagnostics();
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
    } else if (tabId === "diagnostics") {
        updateHiTekDiagnostics();
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

    // Render placeholder pulsing skeleton cards in the results workspace
    renderSkeletonDossier();

    // Set up a dynamic log heartbeat during network wait
    const progressMessages = [
        "[SYS] Probing registry databases...",
        "[NET] Performing DNS profile matching...",
        "[SYS] Initiating Google Dorking pipelines...",
        "[NET] Querying Apify social graph nodes...",
        "[SYS] Aggregating MTProto metadata indices...",
        "[NET] Running entity correlation models...",
        "[SYS] Formatting secondary identity matrices...",
        "[NET] Still negotiating backend resources...",
        "[SYS] Extracting cross-link matches...",
        "[NET] final stages of OSINT assembly..."
    ];
    let msgIdx = 0;
    const heartbeatInterval = setInterval(() => {
        if (msgIdx < progressMessages.length) {
            logLine(progressMessages[msgIdx++], 0);
        } else {
            logLine("[SYS] Heavy processing, waiting for endpoint completion...", 0);
        }
    }, 4000);

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
                correlation_depth: depth,
                filter_hitek: document.getElementById("filter-hitek") ? document.getElementById("filter-hitek").checked : true
            })
        });

        clearInterval(heartbeatInterval);

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
        clearInterval(heartbeatInterval);
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

    // Legcay Subject Profile details elements have been removed from the HTML as they are now rendered dynamically inside platform dossier cards

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

    // Dynamic AI Risk Analysis text report
    const riskAnalysisSection = document.getElementById("risk-analysis-text-section");
    const riskAnalysisContent = document.getElementById("risk-analysis-text-content");
    const riskErrorNotice = document.getElementById("risk-error-notice");
    const riskErrorMessage = document.getElementById("risk-error-message");

    if (risk.ai_risk_analysis) {
        const riskSuccess = risk.ai_risk_analysis.success;
        if (riskSuccess === false) {
            if (riskErrorNotice && riskErrorMessage) {
                riskErrorMessage.innerText = `${risk.ai_risk_analysis.error || "Unknown Error"} ${risk.ai_risk_analysis.details ? ' - ' + risk.ai_risk_analysis.details : ''}`;
                riskErrorNotice.style.display = "block";
            }
            if (riskAnalysisSection) riskAnalysisSection.style.display = "none";
        } else {
            if (riskErrorNotice) riskErrorNotice.style.display = "none";
            const textAnalysis = risk.ai_risk_analysis.analysis;
            if (textAnalysis && textAnalysis.trim() && textAnalysis !== "Configure GROQ_API_KEY for AI risk assessment.") {
                if (riskAnalysisSection && riskAnalysisContent) {
                    riskAnalysisContent.innerText = textAnalysis.trim();
                    riskAnalysisSection.style.display = "block";
                }
            } else {
                if (riskAnalysisSection) riskAnalysisSection.style.display = "none";
            }
        }
    } else {
        if (riskErrorNotice) riskErrorNotice.style.display = "none";
        if (riskAnalysisSection) riskAnalysisSection.style.display = "none";
    }

    // AI Analysis Panel
    const ai = data.ai_correlation_result || {};
    const parsedAI = (ai.ai_analysis && ai.ai_analysis.parsed) ? ai.ai_analysis.parsed : ai.parsed;
    const aiDecisionEl = document.getElementById("ai-decision-badge");
    const aiConf = document.getElementById("ai-confidence");
    const aiSum = document.getElementById("ai-summary");
    const aiReasonsSection = document.getElementById("ai-reasons-section");
    const aiReasonsList = document.getElementById("ai-reasons-list");
    const aiStepsSection = document.getElementById("ai-steps-section");
    const aiStepsList = document.getElementById("ai-steps-list");
    const aiPlatforms = document.getElementById("ai-associated-platforms");
    const aiErrorNotice = document.getElementById("ai-error-notice");
    const aiErrorMessage = document.getElementById("ai-error-message");


    // Render AI execution failure details if success is false
    if (ai.ai_analysis && ai.ai_analysis.success === false) {
        if (aiErrorNotice && aiErrorMessage) {
            aiErrorMessage.innerText = `${ai.ai_analysis.error || "Unknown Error"} ${ai.ai_analysis.details ? ' - ' + ai.ai_analysis.details : ''}`;
            aiErrorNotice.style.display = "block";
        }
    } else {
        if (aiErrorNotice) aiErrorNotice.style.display = "none";
    }

    if (aiConf) {
        const confidenceVal = parsedAI ? (parsedAI.confidence || 0) : Math.round((ai.confidence || 0.65) * 100);
        aiConf.innerText = `Confidence Index: ${confidenceVal}%`;
    }
    const aiEngineStatus = document.getElementById("ai-engine-status");
    if (aiEngineStatus) {
        const modelUsed = (ai.ai_analysis && ai.ai_analysis.model_used) || ai.model_used || "rules_fallback";
        const isGroq = (ai.ai_analysis && ai.ai_analysis.success === true) || (modelUsed !== "rules_fallback");
        if (isGroq) {
            aiEngineStatus.innerText = "completed with groq";
            aiEngineStatus.className = "risk-indicator-badge risk-low";
        } else {
            aiEngineStatus.innerText = "rules fallback";
            aiEngineStatus.className = "risk-indicator-badge risk-medium";
        }
    }
    if (aiSum) {
        aiSum.innerText = ai.summary || "Rule-based placeholder correlation pending AI provider configuration.";
    }

    if (aiDecisionEl && parsedAI) {
        aiDecisionEl.innerText = parsedAI.decision || "UNKNOWN";
        aiDecisionEl.className = "risk-indicator-badge";
        const dec = (parsedAI.decision || "").toLowerCase();
        if (dec.includes("definitely") || dec.includes("very likely") || dec.includes("highly")) {
            aiDecisionEl.classList.add("risk-high");
        } else if (dec.includes("probably") || dec.includes("possibly") || dec.includes("moderate")) {
            aiDecisionEl.classList.add("risk-medium");
        } else {
            aiDecisionEl.classList.add("risk-low");
        }
    } else if (aiDecisionEl) {
        aiDecisionEl.innerText = "PENDING";
        aiDecisionEl.className = "risk-indicator-badge risk-medium";
    }

    if (parsedAI && parsedAI.reasons && parsedAI.reasons.length > 0) {
        if (aiReasonsSection && aiReasonsList) {
            aiReasonsList.innerHTML = parsedAI.reasons.map(r => `<li>${r}</li>`).join("");
            aiReasonsSection.style.display = "block";
        }
    } else {
        if (aiReasonsSection) aiReasonsSection.style.display = "none";
    }

    if (parsedAI && parsedAI.next_steps && parsedAI.next_steps.length > 0) {
        if (aiStepsSection && aiStepsList) {
            aiStepsList.innerHTML = parsedAI.next_steps.map(s => `<li>${s}</li>`).join("");
            aiStepsSection.style.display = "block";
        }
    } else {
        if (aiStepsSection) aiStepsSection.style.display = "none";
    }

    if (aiPlatforms) {
        aiPlatforms.innerHTML = "";
        const plats = ai.matching_platforms || [];
        if (plats.length > 0) {
            plats.forEach(plat => {
                const platData = data.scraped_data ? data.scraped_data[plat.toLowerCase()] : null;
                let profilePic = null;
                if (platData) {
                    profilePic = platData.profile_pic_hd || platData.profile_pic_url || (platData.profile && (platData.profile.profile_pic_hd || platData.profile.profile_pic_url));
                }
                
                if (profilePic && !profilePic.startsWith("data:")) {
                    profilePic = `${API_BASE}/api/v1/investigation/proxy-image?url=${encodeURIComponent(profilePic)}`;
                }
                
                const capsule = document.createElement("a");
                capsule.href = platData?.url || (data.cross_platform_matches?.find(m => m.platform.toLowerCase() === plat.toLowerCase())?.url) || "#";
                capsule.target = "_blank";
                capsule.className = "profile-capsule";
                capsule.style.cssText = "display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px 4px 6px; background: rgba(255, 255, 255, 0.03); border: 1px solid var(--border-glow); border-radius: 20px; color: var(--text-primary); text-decoration: none; font-size: 0.75rem; transition: all 0.2s; cursor: pointer; margin-right: 6px; margin-bottom: 6px;";
                
                capsule.onmouseover = () => {
                    capsule.style.borderColor = "var(--accent-blue)";
                    capsule.style.background = "rgba(0, 188, 212, 0.05)";
                };
                capsule.onmouseout = () => {
                    capsule.style.borderColor = "var(--border-glow)";
                    capsule.style.background = "rgba(255, 255, 255, 0.03)";
                };

                const imgHtml = profilePic
                    ? `<img src="${profilePic}" style="width: 18px; height: 18px; border-radius: 50%; object-fit: cover;" onerror="this.style.display='none'; this.parentNode.innerHTML='<span style=\'font-size:0.65rem; font-weight:bold; color:var(--accent-gold);\'>${plat.substring(0,2).toUpperCase()}</span>';">`
                    : `<span style="font-size: 0.65rem; font-weight: bold; color: var(--accent-gold);">${plat.substring(0,2).toUpperCase()}</span>`;
                
                capsule.innerHTML = `
                    ${imgHtml}
                    <span style="font-weight: 600;">${plat}</span>
                `;
                aiPlatforms.appendChild(capsule);
            });
        } else {
            aiPlatforms.innerHTML = `<span style="font-size:0.75rem; font-style:italic; color:var(--text-secondary);">No indicators found</span>`;
        }
    }

    // Render rich platform intelligence dossier cards
    renderPlatformDossier(data);

    // Internal Database Matches rendering
    const dbMatches = data.internal_database_matches || {};
    const dbCountEl = document.getElementById("internal-matches-count");
    const dbResultsEl = document.getElementById("internal-database-results");

    const byUsername = dbMatches.by_username || [];
    const byPhone = dbMatches.by_phone || [];
    const byEmail = dbMatches.by_email || [];
    const byName = dbMatches.by_name || [];
    const byLocation = dbMatches.by_location || [];
    const allItems = [...byUsername, ...byPhone, ...byEmail, ...byName, ...byLocation];
    const uniqueItems = [];
    const seen = new Set();
    for (const item of allItems) {
        const signature = `${item.name || item.username}-${item.phone}-${item.email}-${item.location || item.address}`;
        if (!seen.has(signature)) {
            seen.add(signature);
            uniqueItems.push(item);
        }
    }
    const totalDbCount = uniqueItems.length;

    if (dbCountEl) {
        dbCountEl.innerText = `Matches Resolved: ${totalDbCount}`;
    }

    if (dbResultsEl) {
        dbResultsEl.innerHTML = "";
        
        // Show Hi-Tek filter info if applicable
        if (dbMatches.hitek_filtered && (dbMatches.hitek_filter_name || (dbMatches.hitek_filter_locations && dbMatches.hitek_filter_locations.length > 0))) {
            const filterDiv = document.createElement("div");
            filterDiv.className = "hitek-filter-info-banner";
            filterDiv.style.cssText = "font-size:0.75rem; background:rgba(0,180,255,0.08); border:1px solid rgba(0,180,255,0.2); padding:6px 10px; border-radius:4px; margin-bottom:8px; display:flex; flex-direction:column; gap:2px; color:var(--text-primary);";
            
            let namePart = dbMatches.hitek_filter_name ? `Name: <strong style="color:var(--accent-blue);">${dbMatches.hitek_filter_name}</strong>` : "";
            let locPart = (dbMatches.hitek_filter_locations && dbMatches.hitek_filter_locations.length > 0) 
                ? `Locations: <strong style="color:var(--accent-blue);">${dbMatches.hitek_filter_locations.join(", ")}</strong>` 
                : "";
            
            let parts = [namePart, locPart].filter(Boolean).join(" | ");
            filterDiv.innerHTML = `<div>🛡️ Hi-Tek DB filtered by profile parameters:</div><div style="font-size:0.7rem; color:var(--text-secondary); margin-top:2px;">${parts}</div>`;
            dbResultsEl.appendChild(filterDiv);
        }

        if (totalDbCount === 0) {
            dbResultsEl.innerHTML = `<span style="font-size:0.8rem; font-style:italic; color:var(--text-secondary); text-align:center; padding:10px;">No internal registry matches found.</span>`;
        } else {
            const table = document.createElement("table");
            table.className = "compact-db-table";
            table.innerHTML = `
                <colgroup>
                    <col style="width: 25%;">
                    <col style="width: 25%;">
                    <col style="width: 22%;">
                    <col style="width: 28%;">
                </colgroup>
                <thead>
                    <tr>
                        <th>Identity Info</th>
                        <th>Mobile/Email</th>
                        <th>Registry/Source</th>
                        <th>Location Address</th>
                    </tr>
                </thead>
                <tbody></tbody>
            `;
            const tbody = table.querySelector("tbody");
            
            uniqueItems.forEach(item => {
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td>
                        <div style="font-weight:600; color:var(--accent-blue);">${item.name || item.username || "Unknown"}</div>
                        <div style="font-size:0.7rem; color:var(--text-secondary); margin-top:2px;">${item.alternate_username || "N/A"}</div>
                    </td>
                    <td>
                        <div style="font-family: 'Share Tech Mono', monospace;">📞 ${item.phone || "N/A"}</div>
                        <div style="font-size:0.7rem; color:var(--text-secondary); margin-top:2px;">✉️ ${item.email || "N/A"}</div>
                    </td>
                    <td>
                        <div style="font-size:0.75rem;">🏛️ ${item.platform || "Local Registry"}</div>
                        <div style="font-size:0.65rem; color:var(--text-secondary); margin-top:2px; max-width:180px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${item.data_source || 'Manual Entry'}">${item.data_source || "Manual Entry"}</div>
                    </td>
                    <td class="addr-col" title="${item.location || item.address || 'N/A'}">
                        📍 ${item.location || item.address || "N/A"}
                    </td>
                `;
                tbody.appendChild(tr);
            });
            dbResultsEl.appendChild(table);
        }
    }

    // Hashtag Link Analysis rendering
    const hashData = data.hashtag_analysis || {};
    const hashStatusEl = document.getElementById("hashtag-analysis-status");
    const extractedTagsEl = document.getElementById("extracted-hashtags-list");
    const connectionsListEl = document.getElementById("hashtag-connections-list");

    const analyzedTags = hashData.hashtags_analyzed || [];
    const potentialConns = hashData.potential_connections || [];

    if (hashStatusEl) {
        hashStatusEl.innerText = analyzedTags.length > 0 ? "Lookup Completed" : "No Hashtags Found";
    }

    if (extractedTagsEl) {
        extractedTagsEl.innerHTML = "";
        if (analyzedTags.length === 0) {
            extractedTagsEl.innerHTML = `<span style="font-size:0.75rem; font-style:italic; color:var(--text-secondary);">None extracted</span>`;
        } else {
            analyzedTags.forEach(tag => {
                const pill = document.createElement("span");
                pill.className = "tag-pill";
                pill.innerText = `#${tag}`;
                extractedTagsEl.appendChild(pill);
            });
        }
    }

    if (connectionsListEl) {
        connectionsListEl.innerHTML = "";
        if (potentialConns.length === 0) {
            connectionsListEl.innerHTML = `<span style="font-size:0.8rem; font-style:italic; color:var(--text-secondary); text-align:center; padding:10px;">No multiple-hashtag connection links identified on Twitter/X.</span>`;
        } else {
            potentialConns.forEach(conn => {
                const tagsString = conn.hashtags ? conn.hashtags.map(t => `#${t}`).join(", ") : "";
                const card = document.createElement("div");
                card.className = "connection-card";
                card.innerHTML = `
                    <div style="display:flex; flex-direction:column; gap:4px;">
                        <span style="font-weight:600; color:var(--accent-gold);">@id:${conn.user || "unknown"}</span>
                        <span style="font-size:0.7rem; color:var(--text-secondary);">Shared tags: ${tagsString}</span>
                    </div>
                    <div style="text-align:right;">
                        <span class="system-badge" style="background:rgba(255, 215, 0, 0.08); border-color:rgba(255, 215, 0, 0.2); color:var(--accent-gold);">${conn.frequency} Overlaps</span>
                    </div>
                `;
                connectionsListEl.appendChild(card);
            });
        }
    }



    // Google Dorking Results rendering
    const dorking = data.dorking_results || {};
    const dorkCountEl = document.getElementById("dorking-results-count");
    const dorkContainerEl = document.getElementById("dorking-results-container");

    if (dorkContainerEl) {
        dorkContainerEl.innerHTML = "";
        
        if (dorking.status === "not_configured") {
            if (dorkCountEl) {
                dorkCountEl.innerText = "Search Providers Not Configured";
                dorkCountEl.style.color = "var(--accent-crimson)";
            }
            
            // Build prepared queries view
            const warningEl = document.createElement("div");
            warningEl.style.cssText = "background:rgba(255, 51, 102, 0.08); border:1px solid rgba(255, 51, 102, 0.2); padding:10px 12px; border-radius:6px; font-size:0.8rem; color:var(--text-primary); line-height:1.4;";
            warningEl.innerHTML = `
                <div style="font-weight:600; color:var(--accent-crimson); margin-bottom:4px; display:flex; align-items:center; gap:6px;">
                    <span>⚠️ Google Dorking Service Offline</span>
                </div>
                <div style="font-size:0.75rem; color:var(--text-secondary);">
                    Configure <code style="font-family:monospace; background:rgba(255,255,255,0.05); padding:1px 3px; border-radius:3px;">SERPAPI_KEY</code>, <code style="font-family:monospace; background:rgba(255,255,255,0.05); padding:1px 3px; border-radius:3px;">BRIGHTDATA_SERP_API_KEY</code>, or <code style="font-family:monospace; background:rgba(255,255,255,0.05); padding:1px 3px; border-radius:3px;">APIFY_API_TOKEN</code>, or manually run these prepared dork queries in Google:
                </div>
            `;
            dorkContainerEl.appendChild(warningEl);
            
            const queriesList = dorking.queries || [];
            if (queriesList.length > 0) {
                const queriesContainer = document.createElement("div");
                queriesContainer.style.cssText = "display:flex; flex-direction:column; gap:6px; margin-top:8px;";
                
                queriesList.forEach(q => {
                    const row = document.createElement("div");
                    row.style.cssText = "display:flex; justify-content:space-between; align-items:center; background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.05); padding:6px 10px; border-radius:4px; font-size:0.75rem; font-family:'Share Tech Mono', monospace;";
                    
                    const catBadge = document.createElement("span");
                    catBadge.className = "tag-pill";
                    catBadge.style.cssText = "font-size:0.6rem; padding:1px 5px; text-transform:uppercase;";
                    catBadge.innerText = q.category.replace(/_/g, ' ');
                    
                    const queryText = document.createElement("span");
                    queryText.style.cssText = "flex:1; margin-left:10px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:var(--accent-gold);";
                    queryText.innerText = q.query;
                    
                    const btnCopy = document.createElement("button");
                    btnCopy.style.cssText = "background:transparent; border:1px solid rgba(255,215,0,0.3); color:var(--accent-gold); font-size:0.65rem; padding:2px 6px; border-radius:3px; cursor:pointer;";
                    btnCopy.innerText = "COPY";
                    btnCopy.onclick = () => {
                        navigator.clipboard.writeText(q.query);
                        btnCopy.innerText = "COPIED!";
                        setTimeout(() => { btnCopy.innerText = "COPY"; }, 1500);
                    };
                    
                    row.appendChild(catBadge);
                    row.appendChild(queryText);
                    row.appendChild(btnCopy);
                    queriesContainer.appendChild(row);
                });
                dorkContainerEl.appendChild(queriesContainer);
            }
        } else {
            const results = dorking.results || [];
            
            // Filter out social platform dorks from the general discovery card
            const socialDomains = ["instagram.com", "twitter.com", "x.com", "t.me", "telegram.me", "linkedin.com", "reddit.com", "facebook.com", "github.com", "youtube.com", "pinterest.com"];
            const generalResults = results.filter(r => {
                const url = (r.url || "").toLowerCase();
                return !socialDomains.some(d => url.includes(d));
            });

            if (dorkCountEl) {
                dorkCountEl.innerText = `Results: ${generalResults.length} General Hits`;
                dorkCountEl.style.color = "var(--accent-blue)";
            }
            
            if (generalResults.length === 0) {
                dorkContainerEl.innerHTML = `<span style="font-size:0.8rem; font-style:italic; color:var(--text-secondary); text-align:center; padding:15px;">Google search indexing returned 0 matching general items.</span>`;
            } else {
                // Group general results by category
                const generalGrouped = {};
                generalResults.forEach(r => {
                    const cat = r.category || "general";
                    if (!generalGrouped[cat]) generalGrouped[cat] = [];
                    generalGrouped[cat].push(r);
                });
                
                Object.keys(generalGrouped).forEach(cat => {
                    const catResults = generalGrouped[cat] || [];
                    if (catResults.length === 0) return;
                    
                    const catHeader = document.createElement("div");
                    catHeader.style.cssText = "font-size:0.75rem; text-transform:uppercase; color:var(--text-secondary); font-weight:600; border-bottom:1px solid rgba(255,255,255,0.05); padding-bottom:4px; margin-top:8px; display:flex; justify-content:space-between;";
                    catHeader.innerHTML = `<span>📂 Category: ${cat.replace(/_/g, ' ')}</span> <span class="mono blue-text" style="font-size:0.7rem;">${catResults.length} hits</span>`;
                    dorkContainerEl.appendChild(catHeader);
                    
                    catResults.forEach(r => {
                        const card = document.createElement("div");
                        card.style.cssText = "background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.05); padding:10px 12px; border-radius:6px; display:flex; flex-direction:column; gap:4px;";
                        
                        card.innerHTML = `
                            <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:8px;">
                                <a href="${r.url}" target="_blank" style="font-size:0.85rem; font-weight:600; color:var(--accent-blue); text-decoration:none; line-height:1.3; hover:text-decoration:underline;">
                                    ${r.title || "No Title"}
                                </a>
                                <span class="system-badge" style="font-size:0.6rem; padding:1px 5px; flex-shrink:0; background:rgba(0,180,255,0.08); border-color:rgba(0,180,255,0.2); color:var(--accent-blue);">${r.domain}</span>
                            </div>
                            <div style="font-size:0.75rem; color:var(--text-primary); line-height:1.4; margin-top:2px;">
                                ${r.snippet || "No description cached."}
                            </div>
                            <div style="font-size:0.65rem; color:var(--text-secondary); font-family:monospace; margin-top:4px; display:flex; gap:10px;">
                                <span><strong>Query:</strong> ${r.query}</span>
                                ${r.position ? `<span><strong>Rank:</strong> #${r.position}</span>` : ""}
                            </div>
                        `;
                        dorkContainerEl.appendChild(card);
                    });
                });
            }
        }
    }
}

function renderInstagramPosts(igPosts) {
    const row = document.getElementById("instagram-posts-row");
    if (!row) return;

    if (!igPosts || !igPosts.configured) {
        row.style.display = "none";
        return;
    }

    row.style.display = "";

    const badge = document.getElementById("posts-count-badge");
    const posts = igPosts.posts || igPosts.reels || [];
    const hashtags = igPosts.all_hashtags || [];

    if (badge) {
        if (igPosts.error) {
            badge.innerText = `Error: ${igPosts.error}`;
            badge.style.color = "var(--accent-crimson)";
        } else {
            badge.innerText = `${posts.length} posts · ${hashtags.length} hashtags`;
            badge.style.color = "";
        }
    }

    // Hashtag Cloud
    const hashContainer = document.getElementById("ig-posts-hashtags");
    if (hashContainer) {
        hashContainer.innerHTML = "";
        if (hashtags.length === 0) {
            hashContainer.innerHTML = `<span style="color:var(--text-secondary); font-size:0.8rem;">No hashtags found</span>`;
        } else {
            hashtags.forEach(tag => {
                const pill = document.createElement("span");
                pill.className = "tag-pill";
                pill.style.cssText = "cursor:default; font-size:0.72rem; padding:2px 8px;";
                pill.innerText = `#${tag}`;
                hashContainer.appendChild(pill);
            });
        }
    }

    // Posts Feed
    const feed = document.getElementById("ig-posts-feed");
    if (!feed) return;
    feed.innerHTML = "";

    if (posts.length === 0) {
        feed.innerHTML = `<div style="color:var(--text-secondary); font-size:0.82rem; padding:10px 0;">${igPosts.error ? igPosts.error : "No posts retrieved."}</div>`;
        return;
    }

    posts.forEach(post => {
        const card = document.createElement("div");
        card.style.cssText = "background:rgba(255,255,255,0.025); border:1px solid rgba(255,255,255,0.06); border-radius:8px; padding:12px 14px; display:flex; flex-direction:column; gap:6px;";

        const dateStr = post.taken_at ? new Date(post.taken_at * 1000).toLocaleString() : "Unknown date";
        const mediaIcon = post.product_type === "clips" ? "🎬" : (post.media_type === "carousel" ? "🎠" : "🖼️");
        const caption = (post.caption || "").trim().substring(0, 200);
        const tags = (post.hashtags || []).slice(0, 8).map(t => `<span style="color:var(--accent-blue); font-size:0.7rem;">#${String(t).replace(/^#/, "")}</span>`).join(" ");
        const mentions = (post.mentions || []).slice(0, 5).map(m => `<span style="color:var(--accent-gold); font-size:0.7rem;">@${String(m).replace(/^@/, "")}</span>`).join(" ");
        const location = post.location && typeof post.location === "object" ? post.location.name || "" : "";

        card.innerHTML = `
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="font-size:0.75rem; color:var(--text-secondary);">${mediaIcon} ${dateStr}</span>
                <div style="display:flex; gap:10px; font-size:0.72rem; color:var(--text-secondary);">
                    ${post.like_count != null ? `<span>❤️ ${Number(post.like_count).toLocaleString()}</span>` : ""}
                    ${post.comment_count != null ? `<span>💬 ${Number(post.comment_count).toLocaleString()}</span>` : ""}
                    ${post.play_count != null ? `<span>▶️ ${Number(post.play_count).toLocaleString()}</span>` : ""}
                    ${post.url ? `<a href="${post.url}" target="_blank" rel="noopener" style="color:var(--accent-blue); text-decoration:none;">Open ↗</a>` : ""}
                </div>
            </div>
            ${caption ? `<div style="font-size:0.82rem; color:var(--text-primary); line-height:1.5;">${caption}${(post.caption||"").length > 200 ? "…" : ""}</div>` : ""}
            ${tags ? `<div style="display:flex; flex-wrap:wrap; gap:4px;">${tags}</div>` : ""}
            ${mentions ? `<div style="display:flex; flex-wrap:wrap; gap:4px;">${mentions}</div>` : ""}
            ${location ? `<div style="font-size:0.7rem; color:var(--text-secondary);">📍 ${location}</div>` : ""}
        `;
        feed.appendChild(card);
    });
}

// Helper to return platform-specific SVG vector icons
function getPlatformSVG(platform) {
    const svgs = {
        instagram: `<svg class="svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="20" rx="5" ry="5"></rect><path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z"></path><line x1="17.5" y1="6.5" x2="17.51" y2="6.5"></line></svg>`,
        twitter: `<svg class="svg-icon" viewBox="0 0 24 24" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>`,
        telegram: `<svg class="svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/></svg>`,
        linkedin: `<svg class="svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-2-2 2 2 0 0 0-2 2v7h-4v-7a6 6 0 0 1 6-6z"></path><rect x="2" y="9" width="4" height="12"></rect><circle cx="4" cy="4" r="2"></circle></svg>`,
        facebook: `<svg class="svg-icon" viewBox="0 0 24 24" fill="currentColor"><path d="M22 12.06C22 6.5 17.52 2 12 2S2 6.5 2 12.06C2 17.08 5.66 21.25 10.44 22v-7.03H7.9v-2.91h2.54V9.85c0-2.52 1.5-3.91 3.78-3.91 1.09 0 2.23.2 2.23.2v2.46H15.2c-1.24 0-1.63.77-1.63 1.56v1.9h2.78l-.44 2.91h-2.34V22C18.34 21.25 22 17.08 22 12.06z"/></svg>`,
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
    let profilePic = pData.profile_pic_hd || pData.profile_pic_url;
    if (profilePic && !profilePic.startsWith("data:")) {
        profilePic = `${API_BASE}/api/v1/investigation/proxy-image?url=${encodeURIComponent(profilePic)}`;
    }
    const risk = data.risk_assessment || { level: "low", score: 0, factors: [] };
    const score = risk.score !== undefined ? risk.score : 0;
    const ai = data.ai_correlation_result || { confidence: 0.65, summary: "", matching_platforms: [] };
    const matches = data.cross_platform_matches || [];
    
    const currentDate = new Date().toLocaleDateString('en-GB', { day: '2-digit', month: '2-digit', year: 'numeric' });
    const timeStr = pData.scraped_at || data.timestamp || new Date().toISOString();
    const formattedScrapeDate = timeStr.replace("T", " ").substring(0, 19);

    // De-duplicate and generate internal DB matches rows
    const dbMatches = data.internal_database_matches || {};
    const byUsername = dbMatches.by_username || [];
    const byPhone = dbMatches.by_phone || [];
    const byEmail = dbMatches.by_email || [];
    const byName = dbMatches.by_name || [];
    const byLocation = dbMatches.by_location || [];
    const allDbMatches = [...byUsername, ...byPhone, ...byEmail, ...byName, ...byLocation];
    
    const uniqueDbMatches = [];
    const seenDb = new Set();
    allDbMatches.forEach(item => {
        const sig = `${item.name || item.username}-${item.phone}-${item.email}-${item.location || item.address}`;
        if (!seenDb.has(sig)) {
            seenDb.add(sig);
            uniqueDbMatches.push(item);
        }
    });

    let dbMatchesRows = "";
    if (uniqueDbMatches.length > 0) {
        uniqueDbMatches.forEach(item => {
            dbMatchesRows += `
            <tr>
                <td><strong>${item.name || item.username || "N/A"}</strong></td>
                <td>${item.alternate_username || "N/A"}</td>
                <td>${item.phone || "N/A"}</td>
                <td>${item.email || "N/A"}</td>
                <td>${item.data_source || "N/A"}</td>
            </tr>`;
        });
    } else {
        dbMatchesRows = `<tr><td colspan="5" style="text-align: center; color: #555;">No records matched in internal user registry.</td></tr>`;
    }

    let hitekFilterNote = "";
    if (dbMatches.hitek_filtered && (dbMatches.hitek_filter_name || (dbMatches.hitek_filter_locations && dbMatches.hitek_filter_locations.length > 0))) {
        let parts = [];
        if (dbMatches.hitek_filter_name) parts.push(`Name: ${dbMatches.hitek_filter_name}`);
        if (dbMatches.hitek_filter_locations && dbMatches.hitek_filter_locations.length > 0) parts.push(`Locations: ${dbMatches.hitek_filter_locations.join(", ")}`);
        hitekFilterNote = `<p style="font-size: 9pt; color: #004d80; background: #eef7fc; border: 1px solid #bce1f7; padding: 6px 10px; border-radius: 4px; margin-bottom: 8px; font-family: sans-serif;">
            <strong>Hi-Tek DB Filtering:</strong> Matches refined using profile parameters (${parts.join(" | ")})
        </p>`;
    }

    // Hashtag Linkage tables
    const hashData = data.hashtag_analysis || {};
    const analyzedTags = hashData.hashtags_analyzed || [];
    const potentialConns = hashData.potential_connections || [];
    
    let hashtagsString = analyzedTags.length > 0 ? analyzedTags.map(t => `#${t}`).join(", ") : "None detected.";
    let hashtagConnectionsRows = "";
    if (potentialConns.length > 0) {
        potentialConns.forEach(conn => {
            hashtagConnectionsRows += `
            <tr>
                <td><strong>@id:${conn.user}</strong></td>
                <td>${conn.frequency} Overlaps</td>
                <td>${conn.hashtags ? conn.hashtags.map(t => `#${t}`).join(", ") : ""}</td>
            </tr>`;
        });
    } else {
        hashtagConnectionsRows = `<tr><td colspan="3" style="text-align: center; color: #555;">No multiple-hashtag connection links identified on Twitter/X network.</td></tr>`;
    }

    // Dorking Results
    const dorking = data.dorking_results || {};
    let dorkingRows = "";
    if (dorking.status === "not_configured") {
        dorkingRows = `<tr><td colspan="4" style="text-align: center; color: #555;">Google Dorking search providers were not configured during run.</td></tr>`;
    } else {
        const dResults = dorking.results || [];
        if (dResults.length > 0) {
            dResults.forEach(r => {
                dorkingRows += `
                <tr>
                    <td><strong>${r.category.toUpperCase().replace(/_/g, ' ')}</strong></td>
                    <td><a href="${r.url}" target="_blank" style="color: #004d80; text-decoration: underline;">${r.title || "Link"}</a><br><span style="font-size: 0.75rem; color: #666;">${r.domain}</span></td>
                    <td style="font-size: 0.8rem; line-height: 1.3;">${r.snippet || ""}</td>
                    <td style="font-family: monospace; font-size: 0.75rem;">${r.query}</td>
                </tr>`;
            });
        } else {
            dorkingRows = `<tr><td colspan="4" style="text-align: center; color: #555;">No organic results resolved via Google Dorking.</td></tr>`;
        }
    }



    // AI Parsing Details
    const parsedAI = (ai.ai_analysis && ai.ai_analysis.parsed) ? ai.ai_analysis.parsed : ai.parsed;
    let aiDecisionText = parsedAI ? (parsedAI.decision || "UNKNOWN") : "UNKNOWN";
    let aiConfidencePercent = parsedAI ? (parsedAI.confidence || 65) : Math.round((ai.confidence || 0.65) * 100);
    
    let aiReasonsHTML = "";
    let aiStepsHTML = "";
    if (parsedAI && parsedAI.reasons && parsedAI.reasons.length > 0) {
        aiReasonsHTML = parsedAI.reasons.map(r => `<li>${r}</li>`).join("");
    } else {
        aiReasonsHTML = "<li>Baseline identity overlap matching rules applied.</li>";
    }
    if (parsedAI && parsedAI.next_steps && parsedAI.next_steps.length > 0) {
        aiStepsHTML = parsedAI.next_steps.map(s => `<li>${s}</li>`).join("");
    } else {
        aiStepsHTML = "<li>Manually verify other account attributes, matching photos, and locations.</li>";
    }

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
    <p>This document files the open-source intelligence findings gathered regarding online handle alias <strong>${pData.username}</strong>. Scans resolved active profiles across online grids with a consolidated threat rating of <strong>${risk.level.toUpperCase()}</strong>. Detailed evidence and platform parameters are cataloged in section 4.</p>
    
    <div class="section-title">2. INCIDENT OVERVIEW</div>
    <p>An automated reconnaissance protocol was instantiated on ${currentDate} under active request reference case ${caseId}. The objective was to search, map, and assess online footprint correlations for the subject handle to check for risk indices, impersonations, or illegal activity.</p>
    
    <div class="section-title">3. PROFILE ANALYSIS</div>
    <h4>3.1 Primary Profile - ${pData.platform.toUpperCase()}</h4>
    <table>
        <tr><td>Username</td><td>${pData.username}</td></tr>
        <tr><td>Display Name</td><td>${pData.full_name || "NOT SPECIFIED"}</td></tr>
        <tr><td>Account Status</td><td>${data.status.toUpperCase()}</td></tr>
        <tr><td>Bio</td><td>${pData.bio || "No biography details cached."}</td></tr>
        <tr><td>Followers</td><td>${pData.follower_count || "UNKNOWN"}</td></tr>
        <tr><td>Following</td><td>${pData.following_count || "UNKNOWN"}</td></tr>
        <tr><td>Profile Pic HD</td><td>${pData.profile_pic_hd ? "Available" : "Not Available"}</td></tr>
        ${profilePic ? `<tr><td>Profile Photo</td><td><img src="${profilePic}" style="width:100px; height:100px; border-radius:50%; object-fit:cover; border:1px solid #333;" onerror="this.style.display='none';"></td></tr>` : ""}
    </table>
    
    <h4>3.2 Content Analysis</h4>
    <p>No anomalous content flags or illegal activity alerts observed on target timeline. Secondary posts examination is pending legal warrant verification.</p>
    
    <h4>3.3 Internal Database Registry Matches</h4>
    ${hitekFilterNote}
    <table>
        <thead>
            <tr>
                <th>Username</th>
                <th>Alternate Username</th>
                <th>Phone Number</th>
                <th>Email Address</th>
                <th>Registry Source</th>
            </tr>
        </thead>
        <tbody>
            ${dbMatchesRows}
        </tbody>
    </table>
    
    <div class="section-title">4. CROSS-PLATFORM CORRELATION</div>
    <h4>4.1 Social Network Presence Index</h4>
    <table>
        <tr>
            <th>Platform</th>
            <th>Username</th>
            <th>Confidence</th>
            <th>Key Evidence</th>
        </tr>
        ${matchesRows}
    </table>

    <h4>4.2 Hashtag Reverse Lookup Analysis</h4>
    <p><strong>Extracted Hashtags from Primary Profile:</strong> ${hashtagsString}</p>
    <table>
        <thead>
            <tr>
                <th>Matched Twitter User</th>
                <th>Overlapping Frequency</th>
                <th>Overlapping Hashtags</th>
            </tr>
        </thead>
        <tbody>
            ${hashtagConnectionsRows}
        </tbody>
    </table>

    <h4>4.3 Google Dorking Discovery Results</h4>
    <table>
        <thead>
            <tr>
                <th style="width: 15%;">Category</th>
                <th style="width: 25%;">Title / Source</th>
                <th style="width: 40%;">Description Snippet</th>
                <th style="width: 20%;">Query Used</th>
            </tr>
        </thead>
        <tbody>
            ${dorkingRows}
        </tbody>
    </table>
    
    <div class="section-title">5. AI CORRELATION ANALYSIS</div>
    <div class="evidence-box">
        <strong>Correlation Decision:</strong> <span style="font-weight:bold; color:red;">${aiDecisionText}</span> (AI Confidence: ${aiConfidencePercent}%)<br><br>
        <strong>Identity Consolidation:</strong>
        <p>${ai.summary || "Rule-based placeholder correlation pending AI provider configuration."}</p>
        
        <strong>Key Correlation Reasons:</strong>
        <ul>
            ${aiReasonsHTML}
        </ul>

        <strong>Recommended Forensic Next Steps:</strong>
        <ul>
            ${aiStepsHTML}
        </ul>
    </div>
    
    <div class="section-title">6. RISK ASSESSMENT</div>
    <p><strong>Risk Level:</strong> <span class="finding-${risk.level}">${risk.level.toUpperCase()}</span> (Threat Score: ${score}%)</p>
    
    <div class="evidence-box">
        <strong>AI Risk Analysis Narrative:</strong>
        <p style="white-space: pre-wrap; font-family: monospace; font-size: 10pt;">${risk.ai_risk_analysis?.analysis || "Configure GROQ_API_KEY to enable narrative risk report details."}</p>
    </div>

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

// Poll / fetch Hi-Tek status
async function updateHiTekDiagnostics() {
    try {
        const resp = await fetch(`${API_BASE}/api/v1/investigation/hitek/status`);
        if (resp.ok) {
            const status = await resp.json();
            const csvStatusEl = document.getElementById("diag-hitek-csv-status");
            const indexStatusEl = document.getElementById("diag-hitek-index-status");
            const recordsEl = document.getElementById("diag-hitek-records");
            
            if (csvStatusEl) {
                if (status.folder_exists) {
                    if (status.csv_files.length > 0) {
                        const valid = status.csv_files.every(f => f.valid_headers);
                        csvStatusEl.innerText = `${status.csv_files.length} CSV file(s) found (${valid ? 'Configured' : 'Mismatched headers'})`;
                        csvStatusEl.style.color = valid ? "#00ff66" : "#ffcc00";
                    } else {
                        csvStatusEl.innerText = "No CSV files found";
                        csvStatusEl.style.color = "#ff3366";
                    }
                } else {
                    csvStatusEl.innerText = "Folder missing";
                    csvStatusEl.style.color = "#ff3366";
                }
            }
            
            if (indexStatusEl) {
                indexStatusEl.innerText = status.index_status.toUpperCase();
                if (status.index_status === "completed") {
                    indexStatusEl.style.color = "#00ff66";
                } else if (status.index_status === "indexing") {
                    indexStatusEl.style.color = "#ffcc00";
                } else {
                    indexStatusEl.style.color = "#ff3366";
                }
            }
            
            if (recordsEl) {
                recordsEl.innerText = status.total_records.toLocaleString();
            }
        }
    } catch (e) {
        console.error("Failed to fetch Hi-Tek diagnostics:", e);
    }
}



// Render dynamic Platform Dossier Cards (IdCrawl-style)
function renderPlatformDossier(data) {
    const container = document.getElementById("platform-dossier-container");
    if (!container) return;
    container.innerHTML = "";

    const matches = data.cross_platform_matches || [];
    const pData = data.platform_data || {};
    const primaryPlatform = pData.platform;
    const dorking = data.dorking_results || {};
    const dorkResults = dorking.results || [];
    const searchedUsername = pData.username || document.getElementById("target-username")?.value || "";

    // Helper to check if a dorking result belongs to a platform
    const getPlatformDorks = (platform) => {
        const domainMap = {
            instagram: ["instagram.com"],
            twitter: ["twitter.com", "x.com"],
            telegram: ["t.me", "telegram.me"],
            linkedin: ["linkedin.com"],
            reddit: ["reddit.com"],
            facebook: ["facebook.com"],
            github: ["github.com"],
            youtube: ["youtube.com"],
            pinterest: ["pinterest.com"]
        };
        const domains = domainMap[platform] || [];
        return dorkResults.filter(r => {
            const url = (r.url || "").toLowerCase();
            return domains.some(d => url.includes(d));
        });
    };

    matches.forEach(match => {
        const isPrimary = match.platform === primaryPlatform;
        const exists = match.exists;
        const card = document.createElement("div");
        card.className = `platform-intel-card ${isPrimary ? 'status-primary' : (exists ? 'status-found' : 'status-absent')}`;

        const svgIcon = getPlatformSVG(match.platform);
        const badgeText = exists ? "Profile found" : "Profile absent";
        const badgeClass = exists ? "match-badge match-found" : "match-badge match-absent";
        const codeText = match.status_code ? `HTTP ${match.status_code}` : (exists ? "RESOLVED" : "TIMEOUT");

        // Filter dorks and posts
        const platformDorks = getPlatformDorks(match.platform);
        let hasExtraContent = false;
        let collapsibleId = `collapse-${match.platform}`;
        
        const preScraped = data.scraped_data ? data.scraped_data[match.platform.toLowerCase()] : null;
        const activeProfileData = isPrimary ? (pData && pData.success !== false ? pData : preScraped) : preScraped;
        const isExpandedByDefault = exists && activeProfileData && activeProfileData.success !== false && activeProfileData.status !== "error" && !activeProfileData.error;
        
        const isInstagramWithPosts = match.platform === "instagram" && data.instagram_posts && data.instagram_posts.posts && data.instagram_posts.posts.length > 0;
        const isScrapable = ["twitter", "reddit", "linkedin", "facebook", "telegram"].includes(match.platform.toLowerCase());
        
        if (exists && (isPrimary || platformDorks.length > 0 || isInstagramWithPosts || isScrapable)) {
            hasExtraContent = true;
        }

        const btnRotation = isExpandedByDefault ? "transform: rotate(180deg);" : "";
        let headerActionHTML = "";
        if (hasExtraContent) {
            headerActionHTML = `
                <div class="platform-intel-toggle-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px; height:14px; transition: transform 0.2s; ${btnRotation}"><polyline points="6 9 12 15 18 9"></polyline></svg>
                </div>
            `;
        }

        // Header section HTML
        let html = `
            <div class="platform-intel-header" ${hasExtraContent ? `style="cursor: pointer;" onclick="togglePlatformCardCollapse('${collapsibleId}', this, '${match.platform}', '${searchedUsername}')"` : ""}>
                <div class="platform-intel-title-group">
                    <span style="display:flex; align-items:center;">${svgIcon}</span>
                    <span class="platform-intel-name">${match.platform}</span>
                </div>
                <div class="platform-intel-badges">
                    <span class="${badgeClass}">${badgeText}</span>
                    <span class="platform-code" style="font-size:0.7rem; opacity:0.8;">${codeText}</span>
                    ${headerActionHTML}
                </div>
            </div>
        `;

        if (exists) {
            let profileHTML = "";
            
            // Build the card body matching the screenshot layout
            if (activeProfileData && activeProfileData.success !== false) {
                const name = activeProfileData.full_name || activeProfileData.name || searchedUsername;
                const handle = activeProfileData.username || activeProfileData.screen_name || searchedUsername;
                const bio = activeProfileData.bio || activeProfileData.description || "";
                const followers = activeProfileData.follower_count !== undefined ? activeProfileData.follower_count : (activeProfileData.followers || 0);
                const following = activeProfileData.following_count !== undefined ? activeProfileData.following_count : (activeProfileData.following || 0);
                const postCount = activeProfileData.post_count !== undefined ? activeProfileData.post_count : (activeProfileData.posts_count || activeProfileData.statuses_count || 0);
                const website = activeProfileData.website || activeProfileData.profile_url || match.url;

                let profilePic = activeProfileData.profile_pic_hd || activeProfileData.profile_pic_url;
                if (profilePic && !profilePic.startsWith("data:")) {
                    profilePic = `${API_BASE}/api/v1/investigation/proxy-image?url=${encodeURIComponent(profilePic)}`;
                }

                const avatarHTML = profilePic
                    ? `<img src="${profilePic}" style="width:100%; height:100%; object-fit:cover; border-radius:50%;" onerror="this.parentNode.innerHTML='<span class=\'scraped-profile-avatar-placeholder\'>${match.platform.substring(0,2).toUpperCase()}</span>';">`
                    : `<span class="scraped-profile-avatar-placeholder">${match.platform.substring(0,2).toUpperCase()}</span>`;

                let followersText = followers ? `${Number(followers).toLocaleString()} followers` : "";
                if (following) followersText += ` · ${Number(following).toLocaleString()} following`;
                if (postCount) followersText += ` · ${Number(postCount).toLocaleString()} posts`;

                profileHTML = `
                    <div class="scraped-profile-row" style="display: flex; gap: 15px; margin-top: 15px; align-items: start;">
                        <div class="scraped-profile-avatar-container" style="width: 70px; height: 70px; border-radius: 50%; overflow: hidden; display: flex; align-items: center; justify-content: center; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); flex-shrink: 0;">
                            ${avatarHTML}
                        </div>
                        <div class="scraped-profile-info" style="display: flex; flex-direction: column; gap: 4px; flex-grow: 1;">
                            <div class="scraped-profile-title" style="font-size: 0.95rem; font-weight: 700; color: var(--text-primary); display: flex; align-items: center; gap: 5px;">
                                <span class="display-name">${name}</span>
                                <span class="handle" style="color: var(--text-secondary); font-weight: normal; font-size: 0.85rem;">- @${handle}</span>
                            </div>
                            ${bio ? `<div class="scraped-profile-bio" style="font-size: 0.8rem; color: var(--text-secondary); line-height: 1.4; white-space: pre-line;">${bio}</div>` : ""}
                            ${website ? `<div class="scraped-profile-website" style="font-size: 0.78rem; display: flex; align-items: center; gap: 4px;"><span style="opacity: 0.6;">🔗</span> <a href="${website}" target="_blank" style="color: var(--accent-blue); text-decoration: none; word-break: break-all;">${website}</a></div>` : ""}
                            ${followersText ? `<div class="scraped-profile-followers" style="font-size: 0.78rem; color: var(--text-secondary); font-weight: 600; margin-top: 2px;">${followersText}</div>` : ""}
                        </div>
                    </div>
                `;
            } else if (match.platform === "telegram" && match.public_evidence) {
                const ev = match.public_evidence;
                const members = ev.page_extra && ev.page_extra.participants_count ? ev.page_extra.participants_count : 0;
                profileHTML = `
                    <div class="scraped-profile-row" style="display: flex; gap: 15px; margin-top: 15px; align-items: start;">
                        <div class="scraped-profile-avatar-container" style="width: 70px; height: 70px; border-radius: 50%; overflow: hidden; display: flex; align-items: center; justify-content: center; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); flex-shrink: 0;">
                            <span class="scraped-profile-avatar-placeholder">TG</span>
                        </div>
                        <div class="scraped-profile-info" style="display: flex; flex-direction: column; gap: 4px; flex-grow: 1;">
                            <div class="scraped-profile-title" style="font-size: 0.95rem; font-weight: 700; color: var(--text-primary); display: flex; align-items: center; gap: 5px;">
                                <span class="display-name">${ev.full_name || "Private/Group"}</span>
                                <span class="handle" style="color: var(--text-secondary); font-weight: normal; font-size: 0.85rem;">- Entity Type: ${(ev.entity_type || "invite_link").toUpperCase()}</span>
                            </div>
                            <div class="scraped-profile-bio" style="font-size: 0.8rem; color: var(--text-secondary);">Bio Present: ${ev.bio_present.toString().toUpperCase()}</div>
                            ${members ? `<div class="scraped-profile-followers" style="font-size: 0.78rem; color: var(--text-secondary); font-weight: 600;">${Number(members).toLocaleString()} members</div>` : ""}
                            <div style="font-size: 0.78rem; margin-top: 2px;">
                                <a href="${match.url}" target="_blank" style="color: var(--accent-blue); text-decoration: none; font-weight: 600;">Open Public Channel/Invite Link ↗</a>
                            </div>
                        </div>
                    </div>
                `;
            } else {
                // Secondary found profile with URL (not scraped yet)
                profileHTML = `
                    <div class="scraped-profile-row placeholder-row" style="display: flex; gap: 15px; margin-top: 15px; align-items: center;">
                        <div class="scraped-profile-avatar-container" style="width: 70px; height: 70px; border-radius: 50%; overflow: hidden; display: flex; align-items: center; justify-content: center; background: rgba(255,255,255,0.02); border: 1px dashed rgba(255,255,255,0.15); flex-shrink: 0;">
                            <span style="font-size: 1.2rem; color: var(--text-secondary); font-weight: 600;">?</span>
                        </div>
                        <div class="scraped-profile-info" style="display: flex; flex-direction: column; gap: 4px; flex-grow: 1;">
                            <div class="scraped-profile-title" style="font-size: 0.95rem; font-weight: 700; color: var(--text-primary); display: flex; align-items: center; gap: 5px;">
                                <span class="display-name">@${searchedUsername}</span>
                            </div>
                            <div class="scraped-profile-bio" style="font-size: 0.8rem; color: var(--text-secondary);">Public profile found. Scrape details to load bio, stats, and timeline.</div>
                            <div style="font-size: 0.78rem; display: flex; gap: 10px; align-items: center; margin-top: 2px;">
                                <a href="${match.url}" target="_blank" style="color: var(--accent-blue); text-decoration: none; font-weight: 600;">Open Profile ↗</a>
                            </div>
                        </div>
                    </div>
                `;
            }

            html += profileHTML;

            // Collapsible details section (posts and dorks)
            if (hasExtraContent) {
                let postsHTML = "";
                let dorksHTML = "";

                if (isInstagramWithPosts) {
                    const igPosts = data.instagram_posts;
                    const posts = igPosts.posts || [];
                    postsHTML = `
                        <div style="margin-top:15px; border-top:1px solid rgba(255,255,255,0.05); padding-top:15px;">
                            <div class="platform-intel-section-title">Recent Instagram Feed (${posts.length} posts)</div>
                            <div style="display:flex; flex-direction:column; gap:10px; max-height:300px; overflow-y:auto; padding-right:5px;">
                    `;
                    posts.forEach(post => {
                        const dateStr = post.taken_at ? new Date(post.taken_at * 1000).toLocaleString() : "Unknown date";
                        const mediaIcon = post.product_type === "clips" ? "🎬" : (post.media_type === "carousel" ? "Carousel 🎠" : "Photo 🖼️");
                        const caption = (post.caption || "").trim().substring(0, 150);
                        postsHTML += `
                            <div style="background:rgba(255,255,255,0.015); border:1px solid rgba(255,255,255,0.04); border-radius:6px; padding:10px; font-size:0.8rem; display:flex; flex-direction:column; gap:4px;">
                                <div style="display:flex; justify-content:space-between; align-items:center;">
                                    <span style="font-size:0.7rem; color:var(--text-secondary);">${mediaIcon} · ${dateStr}</span>
                                    <span style="font-size:0.7rem; color:var(--accent-blue);">❤️ ${post.like_count || 0} 💬 ${post.comment_count || 0}</span>
                                </div>
                                ${caption ? `<div style="color:var(--text-primary); line-height:1.4;">${caption}${post.caption.length > 150 ? '...' : ''}</div>` : ""}
                            </div>
                        `;
                    });
                    postsHTML += `</div></div>`;
                }

                if (platformDorks.length > 0) {
                    dorksHTML = `
                        <div style="margin-top:15px; border-top:1px solid rgba(255,255,255,0.05); padding-top:15px;">
                            <div class="platform-intel-section-title">Correlated Web Discovery Mentions (${platformDorks.length})</div>
                            <div style="display:flex; flex-direction:column; gap:8px; max-height:200px; overflow-y:auto; padding-right:5px;">
                    `;
                    platformDorks.forEach(dork => {
                        dorksHTML += `
                            <div style="background:rgba(255,255,255,0.015); border:1px solid rgba(255,255,255,0.04); border-radius:6px; padding:8px 10px; font-size:0.8rem; display:flex; flex-direction:column; gap:2px;">
                                <a href="${dork.url}" target="_blank" style="color:var(--accent-blue); text-decoration:none; font-weight:600; line-height:1.3;">${dork.title || "Web Match"}</a>
                                <div style="color:var(--text-secondary); font-size:0.75rem; line-height:1.4;">${dork.snippet || ""}</div>
                            </div>
                        `;
                    });
                    dorksHTML += `</div></div>`;
                }

                let scrapedDetailsHTML = "";
                if (preScraped) {
                    const tempDiv = document.createElement("div");
                    renderScrapedDetails(match.platform, preScraped, tempDiv, searchedUsername, true);
                    scrapedDetailsHTML = tempDiv.innerHTML;
                }

                const initialStatus = preScraped ? "scraped" : (isPrimary ? "scraped" : "not_scraped");
                const expandedClass = isExpandedByDefault ? "expanded" : "";
                html += `
                    <div id="${collapsibleId}" class="platform-intel-collapsible ${expandedClass}" data-scraped-status="${initialStatus}">
                        ${scrapedDetailsHTML}
                        ${postsHTML}
                        ${dorksHTML}
                    </div>
                `;
            }
        } else {
            // Absent profile state
            html += `
                <div style="font-size:0.8rem; color:var(--text-secondary); font-style:italic; margin-top:10px;">
                    No public footprint detected on ${match.platform} for username "${searchedUsername}".
                </div>
            `;
        }

        card.innerHTML = html;
        container.appendChild(card);
    });
}

// Collapsible Toggle Helper
function togglePlatformCardCollapse(id, btn, platform, username) {
    const el = document.getElementById(id);
    if (!el) return;
    const isExpanded = el.classList.contains("expanded");
    
    // Close or open
    if (isExpanded) {
        el.classList.remove("expanded");
        btn.querySelector("span").innerText = "Show Details";
        btn.querySelector("svg").style.transform = "rotate(0deg)";
    } else {
        el.classList.add("expanded");
        btn.querySelector("span").innerText = "Hide Details";
        btn.querySelector("svg").style.transform = "rotate(180deg)";
        
        // Auto-scrape on expand if not yet scraped
        const status = el.getAttribute("data-scraped-status");
        if (status === "not_scraped" && platform && username) {
            scrapePlatformOnDemand(platform, username, id, btn);
        }
    }
}

// Static Collapsible Toggle Helper
function toggleStaticCardCollapse(id, btn) {
    const el = document.getElementById(id);
    if (!el) return;
    const collapsible = el.querySelector(".platform-intel-collapsible");
    if (!collapsible) return;
    
    const isExpanded = collapsible.classList.contains("expanded");
    const span = btn.querySelector("span");
    const svg = btn.querySelector("svg");
    
    if (isExpanded) {
        collapsible.classList.remove("expanded");
        if (span) span.innerText = "Show Details";
        if (svg) svg.style.transform = "rotate(0deg)";
    } else {
        collapsible.classList.add("expanded");
        if (span) span.innerText = "Hide Details";
        if (svg) svg.style.transform = "rotate(180deg)";
    }
}

// Deep Scan Trigger Helper
function triggerDeepScanFor(platform, username) {
    const platEl = document.getElementById("target-platform");
    const userEl = document.getElementById("target-username");
    if (platEl) platEl.value = platform;
    if (userEl) userEl.value = username;
    triggerInvestigation();
}

// Render pulsing skeleton cards in results workspace
function renderSkeletonDossier() {
    const container = document.getElementById("platform-dossier-container");
    if (!container) return;
    container.innerHTML = "";
    
    const platforms = ["instagram", "twitter", "reddit", "telegram", "linkedin", "github"];
    platforms.forEach(plat => {
        const card = document.createElement("div");
        card.className = "platform-intel-card skeleton-card skeleton-pulse";
        
        card.innerHTML = `
            <div class="platform-intel-header">
                <div class="platform-intel-title-group" style="width: 100%; display: flex; align-items: center; justify-content: space-between;">
                    <div style="display:flex; align-items:center; gap:10px; width:45%;">
                        <div class="skeleton-circle" style="width:20px; height:20px; background:rgba(255,255,255,0.06);"></div>
                        <div class="skeleton-block" style="width:70%; height:12px; background:rgba(255,255,255,0.06);"></div>
                    </div>
                    <div class="skeleton-block" style="width:65px; height:18px; background:rgba(255,255,255,0.06); border-radius:12px;"></div>
                </div>
            </div>
            <div class="platform-intel-profile" style="grid-template-columns: 80px 1fr;">
                <div class="skeleton-circle" style="width:80px; height:80px; background:rgba(255,255,255,0.06);"></div>
                <div style="display:flex; flex-direction:column; gap:10px;">
                    <div style="display:flex; gap:15px;">
                        <div class="skeleton-block" style="width:120px; height:10px; background:rgba(255,255,255,0.06);"></div>
                        <div class="skeleton-block" style="width:140px; height:10px; background:rgba(255,255,255,0.06);"></div>
                    </div>
                    <div class="skeleton-block" style="width:100%; height:32px; background:rgba(255,255,255,0.06);"></div>
                </div>
            </div>
        `;
        container.appendChild(card);
    });
}

// On-demand scraper trigger to fetch platform details
async function scrapePlatformOnDemand(platform, username, collapsibleId, btn) {
    const el = document.getElementById(collapsibleId);
    if (!el) return;
    
    el.setAttribute("data-scraped-status", "loading");
    
    // Render inline pulsing skeletons
    el.innerHTML = `
        <div style="margin-top:15px; border-top:1px solid rgba(255,255,255,0.05); padding-top:15px;">
            <div class="platform-intel-section-title">Querying Apify Portal Scraper...</div>
            <div class="skeleton-pulse" style="display:flex; flex-direction:column; gap:8px; margin-top:8px;">
                <div class="skeleton-block" style="width:50%; height:12px; background:rgba(255,255,255,0.05);"></div>
                <div class="skeleton-block" style="width:100%; height:10px; background:rgba(255,255,255,0.05);"></div>
                <div class="skeleton-block" style="width:90%; height:10px; background:rgba(255,255,255,0.05);"></div>
                <div class="skeleton-block" style="width:40%; height:10px; background:rgba(255,255,255,0.05);"></div>
            </div>
        </div>
    `;

    try {
        let endpoint = "";
        let body = {};
        
        const plat = platform.toLowerCase();
        if (plat === "twitter") {
            endpoint = `${API_BASE}/api/v1/apify/twitter/profile`;
            body = { username: username, max_items: 5 };
        } else if (plat === "reddit") {
            endpoint = `${API_BASE}/api/v1/apify/reddit/collect`;
            body = { urls: [`https://www.reddit.com/user/${username}/`] };
        } else if (plat === "linkedin") {
            endpoint = `${API_BASE}/api/v1/apify/linkedin/bulk`;
            body = { action: "get-profiles", keywords: [`https://www.linkedin.com/in/${username}`], query_mode: "url", limit: 1 };
        } else if (plat === "facebook") {
            endpoint = `${API_BASE}/api/v1/apify/facebook/posts`;
            body = { urls: [`https://www.facebook.com/${username}`], results_limit: 5 };
        } else if (plat === "telegram") {
            endpoint = `${API_BASE}/api/v1/investigation/username`;
            body = { username: username, platform: "telegram", case_id: currentCaseId, correlation_depth: 1, filter_hitek: false };
        } else {
            throw new Error("No targeted Apify scraper configured for " + platform);
        }

        const response = await fetch(endpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body)
        });

        if (!response.ok) {
            throw new Error(`Scraper returned status code: ${response.status}`);
        }

        const resData = await response.json();
        el.setAttribute("data-scraped-status", "success");
        renderScrapedDetails(platform, resData, el, username);

    } catch (err) {
        el.setAttribute("data-scraped-status", "error");
        el.innerHTML = `
            <div style="margin-top:15px; border-top:1px solid rgba(255,255,255,0.05); padding-top:15px; color:var(--accent-crimson); font-size:0.8rem;">
                ⚠️ Scraper Engine Offline or Limit Exceeded: ${err.message}
            </div>
        `;
    }
}

// Render dynamic details received from target platform scraper
function renderScrapedDetails(platform, data, container, username, excludeProfileCard) {
    container.innerHTML = "";
    const plat = platform.toLowerCase();

    // Helpers
    const esc = s => (s || "").replace(/</g, "&lt;").replace(/>/g, "&gt;");

    // Handle failed scraper execution, empty dataset, or API errors
    if (data && (data.success === false || data.status === "empty_dataset" || data.status === "error" || data.error)) {
        let errorMsg = "";
        if (data.error) {
            errorMsg = typeof data.error === "object" ? (data.error.message || JSON.stringify(data.error)) : String(data.error);
        }
        const msg = errorMsg || (data.run && data.run.status_message) || data.status_message || "Empty dataset returned (Apify quota limit exceeded or profile private/absent).";
        container.innerHTML = `
            <div style="margin-top:15px; border-top:1px solid rgba(255,255,255,0.05); padding-top:15px; color:var(--accent-crimson); font-size:0.8rem; line-height:1.4;">
                <div style="font-weight:600; margin-bottom:4px; display:flex; align-items:center; gap:6px;">
                    <span>⚠️ Scraper Execution Notice</span>
                </div>
                <div style="opacity:0.9; background:rgba(255,51,102,0.05); border:1px solid rgba(255,51,102,0.15); padding:8px 10px; border-radius:4px;">
                    ${esc(msg)}
                </div>
            </div>
        `;
        return;
    }

    const fmtNum = n => Number(n || 0).toLocaleString();
    const fmtDate = (v, unix) => {
        if (!v) return "";
        const d = unix ? new Date(v * 1000) : new Date(v);
        return isNaN(d) ? String(v) : d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }) + " · " + d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
    };

    const truncate = (s, n) => { s = (s || "").trim(); return s.length > n ? s.substring(0, n) + "…" : s; };

    const sectionHeader = (icon, title, count) => `
        <div class="scraped-section-header">
            <span class="scraped-section-icon">${icon}</span>
            <span class="scraped-section-label">${title}</span>
            ${count !== undefined ? `<span class="scraped-section-count">${count}</span>` : ""}
        </div>`;

    const statTile = (label, value, accent) => `
        <div class="scraped-stat-tile${accent ? ' accent-' + accent : ''}">
            <span class="scraped-stat-value">${value}</span>
            <span class="scraped-stat-label">${label}</span>
        </div>`;

    const feedCard = (meta, body, footer) => `
        <div class="scraped-feed-item">
            ${meta ? `<div class="scraped-feed-meta">${meta}</div>` : ""}
            ${body ? `<div class="scraped-feed-body">${body}</div>` : ""}
            ${footer ? `<div class="scraped-feed-footer">${footer}</div>` : ""}
        </div>`;

    let html = `<div class="scraped-details-wrapper">`;

    if (plat === "twitter") {
        const profile = Array.isArray(data) ? data[0] : (data.profile || data || {});
        const tweets = data.tweets || (Array.isArray(data) ? data : []);
        const bio = profile.description || profile.bio || "";
        const followers = profile.followers_count || profile.followers || 0;
        const following = profile.friends_count || profile.following || 0;
        const tweetCount = profile.statuses_count || 0;
        const joined = profile.created_at ? fmtDate(profile.created_at) : "";

        let profilePic = profile.profile_pic_hd || profile.profile_pic_url;
        if (profilePic && !profilePic.startsWith("data:")) {
            profilePic = `${API_BASE}/api/v1/investigation/proxy-image?url=${encodeURIComponent(profilePic)}`;
        }

        if (!excludeProfileCard) {
            html += sectionHeader("👤", "Profile Intelligence");
            html += `<div class="scraped-profile-card">`;
            html += `  <div class="scraped-profile-header">`;
            html += `    <div class="scraped-profile-avatar-container">`;
            if (profilePic) {
                html += `      <img src="${profilePic}" class="scraped-profile-avatar" onerror="this.style.display='none'; this.parentNode.innerHTML='<span class=\'scraped-profile-avatar-placeholder\'>TW</span>';">`;
            } else {
                html += `      <span class="scraped-profile-avatar-placeholder">TW</span>`;
            }
            html += `    </div>`;
            html += `    <div class="scraped-profile-identity">`;
            if (profile.name) {
                html += `      <span class="scraped-profile-name">${esc(profile.name)}</span>`;
            }
            html += `      <span class="scraped-profile-handle">@${esc(profile.screen_name || username)}</span>`;
            if (profile.verified) {
                html += `      <span class="scraped-verified-badge" style="width:fit-content; margin-top:2px;">✓ Verified</span>`;
            }
            html += `    </div>`;
            html += `  </div>`;
            if (bio) html += `<div class="scraped-profile-bio">${esc(bio)}</div>`;
            html += `<div class="scraped-stats-grid">`;
            html += statTile("Followers", fmtNum(followers), "blue");
            html += statTile("Following", fmtNum(following));
            if (tweetCount) html += statTile("Tweets", fmtNum(tweetCount));
            html += `</div>`;
            if (joined) html += `<div class="scraped-profile-meta-line">Joined ${joined}</div>`;
            html += `</div>`;
        }

        const validTweets = tweets.filter(t => t.full_text || t.text);
        if (validTweets.length > 0) {
            html += sectionHeader("💬", "Recent Tweets", validTweets.length);
            html += `<div class="scraped-feed-list">`;
            validTweets.slice(0, 5).forEach(tweet => {
                const dateStr = fmtDate(tweet.created_at);
                const likes = tweet.favorite_count || 0;
                const rts = tweet.retweet_count || 0;
                html += feedCard(
                    dateStr ? `<span class="scraped-feed-date">${dateStr}</span>` : "",
                    esc(truncate(tweet.full_text || tweet.text, 280)),
                    `<span class="scraped-engagement">❤️ ${fmtNum(likes)}</span><span class="scraped-engagement">🔁 ${fmtNum(rts)}</span>`
                );
            });
            html += `</div>`;
        }
    } else if (plat === "reddit") {
        const comments = data.comments || (Array.isArray(data) ? data.filter(i => i.dataType === "comment") : []);
        const posts = data.posts || (Array.isArray(data) ? data.filter(i => i.dataType === "post") : []);
        const user = data.user || {};
        const linkKarma = user.link_karma || 0;
        const commentKarma = user.comment_karma || 0;
        const cakeDay = user.created_utc ? fmtDate(user.created_utc, true) : "";

        if (!excludeProfileCard) {
            html += sectionHeader("👤", "Redditor Profile");
            html += `<div class="scraped-profile-card">`;
            html += `  <div class="scraped-profile-header">`;
            html += `    <div class="scraped-profile-avatar-container" style="border-color:#ff4500; background:rgba(255,69,0,0.05);">`;
            html += `      <span class="scraped-profile-avatar-placeholder" style="color:#ff4500;">RD</span>`;
            html += `    </div>`;
            html += `    <div class="scraped-profile-identity">`;
            html += `      <span class="scraped-profile-name">u/${esc(user.name || username)}</span>`;
            html += `      <span class="scraped-profile-handle" style="color:#ff4500;">Reddit Account</span>`;
            html += `    </div>`;
            html += `  </div>`;
            html += `<div class="scraped-stats-grid">`;
            html += statTile("Post Karma", fmtNum(linkKarma), "blue");
            html += statTile("Comment Karma", fmtNum(commentKarma));
            html += statTile("Total", fmtNum(linkKarma + commentKarma), "gold");
            html += `</div>`;
            if (cakeDay) html += `<div class="scraped-profile-meta-line">Cake Day: ${cakeDay}</div>`;
            html += `</div>`;
        }

        if (posts.length > 0) {
            html += sectionHeader("📝", "Submissions", posts.length);
            html += `<div class="scraped-feed-list">`;
            posts.slice(0, 5).forEach(p => {
                const dateStr = fmtDate(p.created_utc, true);
                html += feedCard(
                    `<span class="scraped-feed-tag">r/${esc(p.subreddit || "?")}</span>${dateStr ? `<span class="scraped-feed-date">${dateStr}</span>` : ""}`,
                    `<strong>${esc(p.title || "Untitled")}</strong>${p.selftext ? `<div class="scraped-feed-excerpt">${esc(truncate(p.selftext, 200))}</div>` : ""}`,
                    `<span class="scraped-engagement">⬆ ${fmtNum(p.score || 0)}</span><span class="scraped-engagement">💬 ${fmtNum(p.num_comments || 0)}</span>`
                );
            });
            html += `</div>`;
        }

        if (comments.length > 0) {
            html += sectionHeader("💬", "Comment Activity", comments.length);
            html += `<div class="scraped-feed-list">`;
            comments.slice(0, 5).forEach(c => {
                const dateStr = fmtDate(c.created_utc, true);
                html += feedCard(
                    `<span class="scraped-feed-tag">r/${esc(c.subreddit || "?")}</span>${dateStr ? `<span class="scraped-feed-date">${dateStr}</span>` : ""}`,
                    esc(truncate(c.body || "", 200)),
                    c.score !== undefined ? `<span class="scraped-engagement">⬆ ${fmtNum(c.score)}</span>` : ""
                );
            });
            html += `</div>`;
        }
    } else if (plat === "linkedin") {
        const profile = Array.isArray(data) ? data[0] : (data.profile || data);
        if (profile) {
            const headline = profile.headline || profile.title || "";
            const summary = profile.summary || "";
            const location = profile.location || profile.geoLocationName || "";
            const connections = profile.connectionsCount || profile.connections || 0;

            let profilePic = profile.profile_pic_hd || profile.profile_pic_url;
            if (profilePic && !profilePic.startsWith("data:")) {
                profilePic = `${API_BASE}/api/v1/investigation/proxy-image?url=${encodeURIComponent(profilePic)}`;
            }

            if (!excludeProfileCard) {
                html += sectionHeader("👤", "Professional Profile");
                html += `<div class="scraped-profile-card">`;
                html += `  <div class="scraped-profile-header">`;
                html += `    <div class="scraped-profile-avatar-container" style="border-color:#0077b5;">`;
                if (profilePic) {
                    html += `      <img src="${profilePic}" class="scraped-profile-avatar" onerror="this.style.display='none'; this.parentNode.innerHTML='<span class=\'scraped-profile-avatar-placeholder\' style=\'color:#0077b5;\'>LN</span>';">`;
                } else {
                    html += `      <span class="scraped-profile-avatar-placeholder" style="color:#0077b5;">LN</span>`;
                }
                html += `    </div>`;
                html += `    <div class="scraped-profile-identity">`;
                html += `      <span class="scraped-profile-name">${esc(profile.fullName || profile.name || username)}</span>`;
                if (headline) {
                    html += `      <span class="scraped-profile-handle" style="color:#0077b5; font-family:inherit; font-size:0.75rem; font-weight:normal;">${esc(headline)}</span>`;
                }
                html += `    </div>`;
                html += `  </div>`;
                if (summary) html += `<div class="scraped-profile-bio">${esc(truncate(summary, 300))}</div>`;
                html += `<div class="scraped-stats-grid">`;
                if (connections) html += statTile("Connections", fmtNum(connections), "blue");
                if (location) html += statTile("Location", esc(location));
                html += `</div>`;
                html += `</div>`;
            }

            const positions = profile.positions || profile.experience || [];
            if (positions.length > 0) {
                html += sectionHeader("💼", "Experience", positions.length);
                html += `<div class="scraped-feed-list">`;
                positions.slice(0, 4).forEach(pos => {
                    html += feedCard(
                        `<span class="scraped-feed-tag">${esc(pos.companyName || pos.company || "Company")}</span>${pos.dateRange || pos.timePeriod ? `<span class="scraped-feed-date">${esc(pos.dateRange || pos.timePeriod || "")}</span>` : ""}`,
                        `<strong>${esc(pos.title || "Role")}</strong>${pos.description ? `<div class="scraped-feed-excerpt">${esc(truncate(pos.description, 200))}</div>` : ""}`,
                        ""
                    );
                });
                html += `</div>`;
            }
        } else {
            html += `<div class="scraped-empty-state">No rich LinkedIn profile payload returned.</div>`;
        }
    } else if (plat === "facebook") {
        const posts = Array.isArray(data) ? data : (data.posts || []);
        let profilePic = data.profile_pic_hd || data.profile_pic_url;
        if (profilePic && !profilePic.startsWith("data:")) {
            profilePic = `${API_BASE}/api/v1/investigation/proxy-image?url=${encodeURIComponent(profilePic)}`;
        }

        if (!excludeProfileCard) {
            html += sectionHeader("👤", "Facebook Page Profile");
            html += `<div class="scraped-profile-card">`;
            html += `  <div class="scraped-profile-header">`;
            html += `    <div class="scraped-profile-avatar-container" style="border-color:#1877f2;">`;
            if (profilePic) {
                html += `      <img src="${profilePic}" class="scraped-profile-avatar" onerror="this.style.display='none'; this.parentNode.innerHTML='<span class=\'scraped-profile-avatar-placeholder\' style=\'color:#1877f2;\'>FB</span>';">`;
            } else {
                html += `      <span class="scraped-profile-avatar-placeholder" style="color:#1877f2;">FB</span>`;
            }
            html += `    </div>`;
            html += `    <div class="scraped-profile-identity">`;
            html += `      <span class="scraped-profile-name">${esc(username)}</span>`;
            html += `      <span class="scraped-profile-handle" style="color:#1877f2;">Facebook Entity</span>`;
            html += `    </div>`;
            html += `  </div>`;
            html += `</div>`;
        }

        if (posts.length > 0) {
            html += sectionHeader("📰", "Public Posts", posts.length);
            html += `<div class="scraped-feed-list">`;
            posts.slice(0, 5).forEach(post => {
                const dateStr = post.time || post.date || "";
                const likes = post.likes || post.reactions || 0;
                html += feedCard(
                    dateStr ? `<span class="scraped-feed-date">${esc(dateStr)}</span>` : "",
                    esc(truncate(post.text || post.message || "", 300)),
                    likes ? `<span class="scraped-engagement">👍 ${fmtNum(likes)}</span>` : ""
                );
            });
            html += `</div>`;
        } else {
            html += `<div class="scraped-empty-state">No public Facebook posts returned.</div>`;
        }
    } else if (plat === "telegram") {
        const td = data.platform_data || data;
        let profilePic = td.profile_pic_hd || td.profile_pic_url;
        if (profilePic && !profilePic.startsWith("data:")) {
            profilePic = `${API_BASE}/api/v1/investigation/proxy-image?url=${encodeURIComponent(profilePic)}`;
        }

        if (!excludeProfileCard) {
            html += sectionHeader("👤", "Telegram Channel Details");
            html += `<div class="scraped-profile-card">`;
            html += `  <div class="scraped-profile-header">`;
            html += `    <div class="scraped-profile-avatar-container" style="border-color:#24a1de;">`;
            if (profilePic) {
                html += `      <img src="${profilePic}" class="scraped-profile-avatar" onerror="this.style.display='none'; this.parentNode.innerHTML='<span class=\'scraped-profile-avatar-placeholder\' style=\'color:#24a1de;\'>TG</span>';">`;
            } else {
                html += `      <span class="scraped-profile-avatar-placeholder" style="color:#24a1de;">TG</span>`;
            }
            html += `    </div>`;
            html += `    <div class="scraped-profile-identity">`;
            if (td.full_name) {
                html += `      <span class="scraped-profile-name">${esc(td.full_name)}</span>`;
            }
            html += `      <span class="scraped-profile-handle">@${esc(td.username || username)}</span>`;
            html += `    </div>`;
            html += `  </div>`;
            if (td.bio) html += `<div class="scraped-profile-bio">${esc(td.bio)}</div>`;
            html += `</div>`;
        }
    } else if (plat === "instagram") {
        const profile = data;
        const bio = profile.bio || profile.biography || "";
        const followers = profile.follower_count !== undefined ? profile.follower_count : (profile.followers || 0);
        const following = profile.following_count !== undefined ? profile.following_count : (profile.following || 0);
        const postCount = profile.post_count !== undefined ? profile.post_count : (profile.posts_count || 0);

        let profilePic = profile.profile_pic_hd || profile.profile_pic_url;
        if (profilePic && !profilePic.startsWith("data:")) {
            profilePic = `${API_BASE}/api/v1/investigation/proxy-image?url=${encodeURIComponent(profilePic)}`;
        }

        if (!excludeProfileCard) {
            html += sectionHeader("👤", "Instagram Profile Details");
            html += `<div class="scraped-profile-card">`;
            html += `  <div class="scraped-profile-header">`;
            html += `    <div class="scraped-profile-avatar-container" style="border-color:#e1306c; background:rgba(225,48,108,0.05);">`;
            if (profilePic) {
                html += `      <img src="${profilePic}" class="scraped-profile-avatar" onerror="this.style.display='none'; this.parentNode.innerHTML='<span class=\'scraped-profile-avatar-placeholder\' style=\'color:#e1306c;\'>IG</span>';">`;
            } else {
                html += `      <span class="scraped-profile-avatar-placeholder" style="color:#e1306c;">IG</span>`;
            }
            html += `    </div>`;
            html += `    <div class="scraped-profile-identity">`;
            if (profile.full_name) {
                html += `      <span class="scraped-profile-name">${esc(profile.full_name)}</span>`;
            }
            html += `      <span class="scraped-profile-handle" style="color:#e1306c;">@${esc(profile.username || username)}</span>`;
            if (profile.is_verified) {
                html += `      <span class="scraped-verified-badge" style="width:fit-content; margin-top:2px;">✓ Verified</span>`;
            }
            html += `    </div>`;
            html += `  </div>`;
            if (bio) html += `<div class="scraped-profile-bio">${esc(bio)}</div>`;
            html += `<div class="scraped-stats-grid">`;
            html += statTile("Followers", fmtNum(followers), "blue");
            html += statTile("Following", fmtNum(following));
            html += statTile("Posts", fmtNum(postCount), "gold");
            html += `</div>`;
            html += `</div>`;
        }

        // Render hashtags if present in the global response
        const igPosts = currentInvestigationData && currentInvestigationData.instagram_posts;
        if (igPosts && !igPosts.error) {
            const hashtags = igPosts.all_hashtags || [];

            if (hashtags.length > 0) {
                html += sectionHeader("🏷️", "Post Hashtags", hashtags.length);
                html += `<div style="display:flex; flex-wrap:wrap; gap:6px; margin: 10px 0 15px 0;">`;
                hashtags.forEach(tag => {
                    html += `<span class="tag-pill" style="cursor:default; font-size:0.72rem; padding:3px 8px; background:rgba(0,188,212,0.05); border:1px solid rgba(0,188,212,0.15); border-radius:4px; color:var(--accent-blue);">#${tag}</span>`;
                });
                html += `</div>`;
            }
        }
    } else {
        html += sectionHeader("📦", "Raw Data Payload");
        html += `<pre class="scraped-raw-payload">${esc(JSON.stringify(data, null, 2))}</pre>`;
    }

    html += `</div>`;
    container.innerHTML = html;
}

