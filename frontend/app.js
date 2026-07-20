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

    // Reset our 4 new cards
    const assocCount = document.getElementById("associated-accounts-count");
    const assocResults = document.getElementById("associated-accounts-results");
    if (assocCount) assocCount.innerText = "0 Accounts Found";
    if (assocResults) assocResults.innerHTML = "";

    const secretCount = document.getElementById("secret-profiles-count");
    const secretResults = document.getElementById("secret-profiles-results");
    if (secretCount) secretCount.innerText = "0 Aliases Found";
    if (secretResults) secretResults.innerHTML = "";

    const personalityStatus = document.getElementById("personality-profile-status");
    const personalityResults = document.getElementById("personality-profile-results");
    if (personalityStatus) personalityStatus.innerText = "Not Analyzed";
    if (personalityResults) personalityResults.innerHTML = "";

    const telegramIntelStatus = document.getElementById("telegram-intel-status");
    const telegramIntelResults = document.getElementById("telegram-intel-results");
    if (telegramIntelStatus) telegramIntelStatus.innerText = "No Data";
    if (telegramIntelResults) telegramIntelResults.innerHTML = "";
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

    // Immediately hide empty standby state & show skeleton workspace grid on button click
    const emptyState = document.getElementById("results-empty-state");
    const grid = document.getElementById("results-workspace-grid");
    if (emptyState) emptyState.style.display = "none";
    if (grid) grid.style.display = "grid";

    // Render pulsing skeleton loaders across all 6 main section containers
    renderSkeletonDossier();

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
        const plats = [...(ai.matching_platforms || [])];
        
        // Ensure Telegram handle is included if Telegram intelligence shows account exists
        const tgData = (data.scraped_data && data.scraped_data.telegram) || {};
        const hasTg = tgData.username || tgData.exists || (data.cross_platform_matches && data.cross_platform_matches.some(m => m.platform.toLowerCase() === "telegram" && m.exists));
        if (hasTg && !plats.some(p => p.toLowerCase() === "telegram")) {
            plats.push("telegram");
        }

        if (plats.length > 0) {
            plats.forEach(plat => {
                const platLower = plat.toLowerCase();
                const platData = data.scraped_data ? data.scraped_data[platLower] : null;
                let profilePic = null;
                if (platData) {
                    profilePic = platData.profile_pic_hd || platData.profile_pic_url || (platData.profile && (platData.profile.profile_pic_hd || platData.profile.profile_pic_url));
                }
                
                if (profilePic && !profilePic.startsWith("data:")) {
                    profilePic = `${API_BASE}/api/v1/investigation/proxy-image?url=${encodeURIComponent(profilePic)}`;
                }
                
                const handleUsername = (platData && platData.username) || (platLower === "telegram" && tgData.username ? tgData.username : null);
                
                const capsule = document.createElement("a");
                capsule.href = platData?.url || (data.cross_platform_matches?.find(m => m.platform.toLowerCase() === platLower)?.url) || (platLower === "telegram" && handleUsername ? `https://t.me/${handleUsername}` : "#");
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
                    <span style="font-weight: 600; text-transform: uppercase;">${plat}</span>
                    ${handleUsername ? `<span style="font-size:0.7rem; color:var(--accent-blue); font-family:'Share Tech Mono',monospace;">@${handleUsername}</span>` : ""}
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
                dorkContainerEl.innerHTML = `<div style="font-size:0.8rem; font-style:italic; color:var(--text-secondary); text-align:center; padding:10px 15px;">Google search indexing returned 0 matching general items.</div>`;
                
                const queriesList = dorking.queries || [];
                if (queriesList.length > 0) {
                    const manualDorksDiv = document.createElement("div");
                    manualDorksDiv.style.cssText = "margin-top:10px; border-top:1px solid rgba(255,255,255,0.05); padding-top:10px;";
                    manualDorksDiv.innerHTML = `<div style="font-size:0.75rem; color:var(--text-secondary); margin-bottom:8px;">You can manually search these prepared dork queries in Google:</div>`;
                    const queriesContainer = document.createElement("div");
                    queriesContainer.style.cssText = "display:flex; flex-direction:column; gap:6px;";
                    
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
                    manualDorksDiv.appendChild(queriesContainer);
                    dorkContainerEl.appendChild(manualDorksDiv);
                }
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

    // 1. Associated Accounts rendering
    const assocCountEl = document.getElementById("associated-accounts-count");
    const assocResultsEl = document.getElementById("associated-accounts-results");
    const assocAccounts = (data.reverse_lookup_results && data.reverse_lookup_results.associated_accounts) || [];
    if (assocCountEl) {
        assocCountEl.innerText = `${assocAccounts.length} Accounts Found`;
    }
    if (assocResultsEl) {
        assocResultsEl.innerHTML = "";
        if (assocAccounts.length === 0) {
            assocResultsEl.innerHTML = `<span style="font-size:0.8rem; font-style:italic; color:var(--text-secondary); text-align:center; padding:10px;">No associated accounts detected.</span>`;
        } else {
            assocAccounts.forEach(acc => {
                const card = document.createElement("div");
                card.style.cssText = "background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.05); padding:10px 12px; border-radius:6px; display:flex; justify-content:space-between; align-items:center; gap:8px;";
                card.innerHTML = `
                    <div style="display:flex; flex-direction:column; gap:4px;">
                        <span style="font-weight:600; color:var(--accent-blue);">@${acc.username}</span>
                        <span style="font-size:0.7rem; color:var(--text-secondary);">Source: ${acc.source} · Platform: ${acc.platform}</span>
                        ${acc.evidence ? `<span style="font-size:0.7rem; color:var(--text-primary); margin-top:2px; font-style:italic;">Evidence: "${acc.evidence}"</span>` : ""}
                    </div>
                    <div style="text-align:right; flex-shrink:0;">
                        <span class="system-badge" style="background:rgba(0,188,212,0.08); border-color:rgba(0,188,212,0.2); color:var(--accent-blue);">${typeof acc.confidence === 'string' ? acc.confidence : Math.round(acc.confidence * 100) + '%'} Match</span>
                    </div>
                `;
                assocResultsEl.appendChild(card);
            });
        }
    }

    // 2. Secret Profiles → Guessed Emails (per front-end sketch)
    const secretCountEl = document.getElementById("secret-profiles-count");
    const secretResultsEl = document.getElementById("secret-profiles-results");
    // Pull emails from intelligence_report (pattern-generated by email_guesser)
    const guessedEmails = (
        data.intelligence_report &&
        data.intelligence_report.executive_summary &&
        data.intelligence_report.executive_summary.contact_information &&
        data.intelligence_report.executive_summary.contact_information.emails
    ) || [];
    if (secretCountEl) {
        secretCountEl.innerText = guessedEmails.length > 0
            ? `${guessedEmails.length} Patterns Generated`
            : "0 Emails Generated";
    }
    if (secretResultsEl) {
        secretResultsEl.innerHTML = "";
        if (guessedEmails.length === 0) {
            secretResultsEl.innerHTML = `<span style="font-size:0.8rem; font-style:italic; color:var(--text-secondary); text-align:center; padding:10px;">No email patterns generated.</span>`;
        } else {
            // Warn: these are guesses, not verified
            const warning = document.createElement("div");
            warning.style.cssText = "background:rgba(255,165,0,0.08); border:1px solid rgba(255,165,0,0.25); border-radius:6px; padding:8px 12px; font-size:0.72rem; color:#ffa500; margin-bottom:6px;";
            warning.innerHTML = `⚠️ <strong>Unverified</strong> — algorithmically guessed from username pattern. Not confirmed real addresses.`;
            secretResultsEl.appendChild(warning);

            guessedEmails.forEach((email, i) => {
                const confidence = Math.max(95 - i * 10, 40); // descending: 95, 85, 75…
                let badgeStyle = "background:rgba(255,165,0,0.08); border-color:rgba(255,165,0,0.25); color:#ffa500;";
                if (confidence >= 85) {
                    badgeStyle = "background:rgba(0,255,100,0.08); border-color:rgba(0,255,100,0.25); color:#00ff66;";
                } else if (confidence >= 65) {
                    badgeStyle = "background:rgba(255,215,0,0.08); border-color:rgba(255,215,0,0.25); color:var(--accent-gold);";
                }
                const card = document.createElement("div");
                card.style.cssText = "background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.05); padding:10px 12px; border-radius:6px; display:flex; justify-content:space-between; align-items:center; gap:8px;";
                card.innerHTML = `
                    <div style="display:flex; align-items:center; gap:8px; min-width:0;">
                        <span style="font-size:1rem;">📧</span>
                        <span style="font-family:'Share Tech Mono',monospace; font-size:0.82rem; color:var(--text-primary); overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${email}</span>
                    </div>
                    <div style="display:flex; align-items:center; gap:8px; flex-shrink:0;">
                        <span class="system-badge" style="${badgeStyle} font-size:0.65rem;">${confidence}% guess</span>
                        <button onclick="navigator.clipboard.writeText('${email}').then(()=>{this.textContent='✓ Copied';setTimeout(()=>{this.textContent='📋 Copy'},1500)})" style="background:rgba(0,188,212,0.1); border:1px solid rgba(0,188,212,0.25); color:var(--accent-blue); padding:3px 8px; border-radius:4px; font-size:0.7rem; cursor:pointer;">📋 Copy</button>
                    </div>
                `;
                secretResultsEl.appendChild(card);
            });
        }
    }

    // 3. Personality Profile rendering
    const personalityStatusEl = document.getElementById("personality-profile-status");
    const personalityResultsEl = document.getElementById("personality-profile-results");
    const profileType = (data.reverse_lookup_results && data.reverse_lookup_results.profile_type) || {};
    
    const pReport = data.intelligence_report || {};
    const pSections = pReport.intelligence_sections || {};
    const hashIntel = pSections.hashtag_intelligence || {};
    const keyDisc = hashIntel.key_discoveries || {};
    const traits = keyDisc.personality_indicators || [];

    if (personalityStatusEl) {
        personalityStatusEl.innerText = profileType.primary_type ? "Analysis Completed" : "Not Classified";
    }
    if (personalityResultsEl) {
        personalityResultsEl.innerHTML = "";
        if (!profileType.primary_type) {
            personalityResultsEl.innerHTML = `<span style="font-size:0.8rem; font-style:italic; color:var(--text-secondary); text-align:center; padding:10px;">Insufficient indicators to classify personality/interests.</span>`;
        } else {
            let html = `
                <div style="display:flex; flex-direction:column; gap:8px; background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.05); padding:12px; border-radius:6px;">
                    <div>
                        <span style="font-size:0.75rem; text-transform:uppercase; color:var(--text-secondary); font-weight:600;">Dominant Profile Type:</span>
                        <div style="font-size:0.95rem; font-weight:700; color:var(--accent-gold); margin-top:2px;">${profileType.primary_type.replace(/_/g, ' ').toUpperCase()} (${Math.round(profileType.confidence * 100)}% Confidence)</div>
                    </div>
                    ${profileType.description ? `<div style="font-size:0.8rem; color:var(--text-primary); line-height:1.4;">${profileType.description}</div>` : ""}
                    ${profileType.professional_field ? `<div style="font-size:0.78rem; color:var(--text-secondary);"><strong>Professional Field:</strong> ${profileType.professional_field}</div>` : ""}
                </div>
            `;

            const interests = profileType.interests || [];
            if (interests.length > 0) {
                html += `
                    <div style="margin-top:10px;">
                        <div style="font-size:0.75rem; text-transform:uppercase; color:var(--text-secondary); font-weight:600; margin-bottom:6px;">Interest Fingerprint</div>
                        <div style="display:flex; flex-wrap:wrap; gap:6px;">
                `;
                interests.forEach(interest => {
                    html += `<span class="tag-pill" style="font-size:0.72rem; padding:3px 8px; background:rgba(0,188,212,0.05); border:1px solid rgba(0,188,212,0.15); border-radius:4px; color:var(--accent-blue);">${interest}</span>`;
                });
                html += `</div></div>`;
            }

            if (traits.length > 0) {
                html += `
                    <div style="margin-top:10px;">
                        <div style="font-size:0.75rem; text-transform:uppercase; color:var(--text-secondary); font-weight:600; margin-bottom:6px;">Personality Trait Indicators</div>
                        <div style="display:flex; flex-direction:column; gap:6px;">
                `;
                traits.forEach(t => {
                    html += `
                        <div style="background:rgba(255,255,255,0.015); border:1px solid rgba(255,255,255,0.03); border-radius:4px; padding:6px 10px; font-size:0.75rem; display:flex; justify-content:space-between; align-items:center;">
                            <span style="font-weight:600; color:var(--text-primary);">${t.trait} (${t.category})</span>
                            <span class="system-badge" style="font-size:0.6rem; padding:1px 5px; background:rgba(0,180,255,0.08); border-color:rgba(0,180,255,0.2); color:var(--accent-blue);">${t.confidence} Match</span>
                        </div>
                    `;
                });
                html += `</div></div>`;
            }

            personalityResultsEl.innerHTML = html;
        }
    }

    // 4. Telegram Intelligence rendering
    const tgIntelStatusEl = document.getElementById("telegram-intel-status");
    const tgIntelResultsEl = document.getElementById("telegram-intel-results");
    const tgData = (data.scraped_data && data.scraped_data.telegram) || {};
    
    if (tgIntelStatusEl) {
        tgIntelStatusEl.innerText = tgData.exists ? "Active Account/Channel" : (tgData.exists === false ? "No Account Found" : "No Data");
    }
    if (tgIntelResultsEl) {
        tgIntelResultsEl.innerHTML = "";
        if (!tgData.username) {
            tgIntelResultsEl.innerHTML = `<span style="font-size:0.8rem; font-style:italic; color:var(--text-secondary); text-align:center; padding:10px;">No Telegram intelligence cached for this target username.</span>`;
        } else {
            let mtprotoHTML = "";
            if (tgData.mtproto_status) {
                const ms = tgData.mtproto_status;
                mtprotoHTML = `
                    <div style="background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.05); padding:10px 12px; border-radius:6px; font-size:0.78rem; margin-top:10px;">
                        <span style="font-size:0.7rem; text-transform:uppercase; color:var(--text-secondary); font-weight:600; display:block; margin-bottom:4px;">MTProto API Access Diagnostics:</span>
                        <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px;">
                            <div>MTProto Enabled: <span style="font-weight:600; color:${ms.enabled ? 'var(--accent-blue)' : 'var(--text-secondary)'};">${ms.enabled ? 'YES' : 'NO'}</span></div>
                            <div>Auth Dependency: <span style="font-weight:600; color:${ms.dependency_available ? 'var(--accent-blue)' : 'var(--accent-crimson)'};">${ms.dependency_available ? 'AVAILABLE' : 'MISSING'}</span></div>
                            <div>Credentials Configured: <span style="font-weight:600; color:${ms.credentials_configured ? 'var(--accent-blue)' : 'var(--text-secondary)'};">${ms.credentials_configured ? 'YES' : 'NO'}</span></div>
                            <div>Session File: <span style="font-weight:600; color:${ms.session_file_present ? 'var(--accent-blue)' : 'var(--text-secondary)'};">${ms.session_file_present ? 'FOUND' : 'NOT FOUND'}</span></div>
                        </div>
                    </div>
                `;
            }

            let signalsHTML = "";
            if (tgData.verification_signals) {
                const vs = tgData.verification_signals;
                signalsHTML = `
                    <div style="display:flex; gap:6px; flex-wrap:wrap; margin-top:8px;">
                        <span class="system-badge" style="background:${vs.is_verified ? 'rgba(0,188,212,0.08)' : 'rgba(255,255,255,0.03)'}; border-color:${vs.is_verified ? 'rgba(0,188,212,0.2)' : 'rgba(255,255,255,0.08)'}; color:${vs.is_verified ? 'var(--accent-blue)' : 'var(--text-secondary)'};">Verified Badge: ${vs.is_verified ? 'YES' : 'NO'}</span>
                        <span class="system-badge" style="background:${vs.is_scam ? 'rgba(255,51,102,0.08)' : 'rgba(255,255,255,0.03)'}; border-color:${vs.is_scam ? 'rgba(255,51,102,0.2)' : 'rgba(255,255,255,0.08)'}; color:${vs.is_scam ? 'var(--accent-crimson)' : 'var(--text-secondary)'};">Scam Signal: ${vs.is_scam ? 'YES' : 'NO'}</span>
                        <span class="system-badge" style="background:${vs.is_fake ? 'rgba(255,51,102,0.08)' : 'rgba(255,255,255,0.03)'}; border-color:${vs.is_fake ? 'rgba(255,51,102,0.2)' : 'rgba(255,255,255,0.08)'}; color:${vs.is_fake ? 'var(--accent-crimson)' : 'var(--text-secondary)'};">Fake Signal: ${vs.is_fake ? 'YES' : 'NO'}</span>
                    </div>
                `;
            }

            tgIntelResultsEl.innerHTML = `
                <div style="background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.05); padding:12px; border-radius:6px; display:flex; gap:12px; align-items:start;">
                    <div style="width:50px; height:50px; border-radius:50%; background:rgba(36,161,222,0.1); border:1px solid rgba(36,161,222,0.3); display:flex; align-items:center; justify-content:center; font-weight:bold; color:var(--accent-blue); flex-shrink:0;">TG</div>
                    <div style="display:flex; flex-direction:column; gap:4px; flex-grow:1;">
                        <div style="font-size:0.9rem; font-weight:700; color:var(--text-primary); display:flex; justify-content:space-between;">
                            <span>${tgData.full_name || "Telegram Profile"}</span>
                            <span style="font-size:0.75rem; color:var(--text-secondary); font-weight:normal;">@${tgData.username}</span>
                        </div>
                        ${tgData.bio ? `<div style="font-size:0.8rem; color:var(--text-secondary); line-height:1.4;">${tgData.bio}</div>` : ""}
                        <div style="font-size:0.78rem; color:var(--text-primary); font-weight:600; margin-top:2px;">
                            Entity Type: ${(tgData.entity_type || "user").toUpperCase()} 
                            ${tgData.subscriber_count ? `· ${Number(tgData.subscriber_count).toLocaleString()} members` : ""}
                        </div>
                        ${signalsHTML}
                    </div>
                </div>
                ${(() => {
                    const ia = tgData.intelligence_analysis || {};
                    let extraHTML = "";
                    if (ia.links_extracted && ia.links_extracted.length > 0) {
                        extraHTML += `<div style="margin-top:8px; font-size:0.75rem; color:var(--text-secondary);"><strong>Links in Bio:</strong> ${ia.links_extracted.map(l => `<a href="${l}" target="_blank" style="color:var(--accent-blue); margin-right:6px;">${l}</a>`).join("")}</div>`;
                    }
                    if (ia.handles_mentioned && ia.handles_mentioned.length > 0) {
                        extraHTML += `<div style="margin-top:4px; font-size:0.75rem; color:var(--text-secondary);"><strong>Handles Mentioned:</strong> ${ia.handles_mentioned.map(h => `<span class="tag-pill" style="font-size:0.65rem; padding:1px 5px; margin-right:4px;">${h}</span>`).join("")}</div>`;
                    }
                    if (ia.recommended_osint_bots && ia.recommended_osint_bots.length > 0) {
                        extraHTML += `
                            <div style="margin-top:10px; background:rgba(0,198,255,0.03); border:1px solid rgba(0,198,255,0.12); padding:8px 10px; border-radius:6px;">
                                <div style="font-size:0.7rem; text-transform:uppercase; font-weight:700; color:var(--accent-blue); margin-bottom:4px;">Recommended Telegram OSINT Bots (Methodology):</div>
                                <div style="display:flex; flex-direction:column; gap:3px;">
                                    ${ia.recommended_osint_bots.map(b => `<div style="font-size:0.72rem; color:var(--text-secondary);"><strong style="color:var(--accent-gold);">${b.bot}</strong> — ${b.purpose}</div>`).join("")}
                                </div>
                            </div>
                        `;
                    }
                    return extraHTML;
                })()}
                ${mtprotoHTML}
            `;
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

    // Filter out empty/null-only posts (private accounts return a skeleton with profile URL only)
    const realPosts = posts.filter(p => p.caption || p.taken_at || p.like_count != null || p.display_url || (p.hashtags && p.hashtags.length));

    if (badge) {
        if (igPosts.error) {
            badge.innerText = `Error: ${igPosts.error}`;
            badge.style.color = "var(--accent-crimson)";
        } else {
            badge.innerText = `${realPosts.length} posts · ${hashtags.length} hashtags`;
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

    if (realPosts.length === 0) {
        feed.innerHTML = `<div style="color:var(--text-secondary); font-size:0.82rem; padding:10px 0;">${igPosts.error ? igPosts.error : "No posts retrieved (account may be private or have no posts)."}</div>`;
        return;
    }

    realPosts.forEach(post => {
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

// Helper to return platform-specific branded, coloured SVG icons
function getPlatformSVG(platform) {
    const svgs = {
        instagram: `<svg class="svg-icon" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><defs><radialGradient id="ig-grad" cx="30%" cy="107%" r="150%"><stop offset="0%" stop-color="#fdf497"/><stop offset="5%" stop-color="#fdf497"/><stop offset="45%" stop-color="#fd5949"/><stop offset="60%" stop-color="#d6249f"/><stop offset="90%" stop-color="#285AEB"/></radialGradient></defs><rect x="2" y="2" width="20" height="20" rx="5" ry="5" fill="url(#ig-grad)"/><rect x="2" y="2" width="20" height="20" rx="5" ry="5" fill="none" stroke="none"/><circle cx="12" cy="12" r="4" fill="none" stroke="white" stroke-width="1.8"/><circle cx="17.5" cy="6.5" r="1.2" fill="white"/></svg>`,
        twitter: `<svg class="svg-icon" viewBox="0 0 24 24" fill="white" style="background:#000; border-radius:6px; padding:2px;"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>`,
        telegram: `<svg class="svg-icon" viewBox="0 0 24 24" fill="none" style="background:#29a9eb; border-radius:50%; padding:2px;"><path d="M21.93 3.36L3.46 10.27c-1.18.47-1.17 1.13-.22 1.42l4.58 1.43 10.62-6.7c.5-.3.95-.14.58.19L9.63 15.15l-.35 4.67c.51 0 .74-.23 1.02-.5l2.45-2.38 5.09 3.76c.94.52 1.61.25 1.84-.87l3.33-15.69c.34-1.36-.52-1.97-1.08-1.78z" fill="white"/></svg>`,
        linkedin: `<svg class="svg-icon" viewBox="0 0 24 24" style="background:#0A66C2; border-radius:5px; padding:2px;"><path d="M6.94 5a2 2 0 1 1-4-.002 2 2 0 0 1 4 .002zM7 8.48H3V21h4V8.48zm6.32 0H9.34V21h3.94v-6.57c0-3.66 4.77-4 4.77 0V21H22v-7.93c0-6.17-7.06-5.94-8.72-2.91l.04-1.68z" fill="white"/></svg>`,
        facebook: `<svg class="svg-icon" viewBox="0 0 24 24" style="background:#1877F2; border-radius:50%; padding:1px;"><path d="M22 12.06C22 6.5 17.52 2 12 2S2 6.5 2 12.06C2 17.08 5.66 21.25 10.44 22v-7.03H7.9v-2.91h2.54V9.85c0-2.52 1.5-3.91 3.78-3.91 1.09 0 2.23.2 2.23.2v2.46H15.2c-1.24 0-1.63.77-1.63 1.56v1.9h2.78l-.44 2.91h-2.34V22C18.34 21.25 22 17.08 22 12.06z" fill="white"/></svg>`,
        github: `<svg class="svg-icon" viewBox="0 0 24 24" fill="white" style="background:#24292e; border-radius:50%; padding:1px;"><path d="M12 2C6.48 2 2 6.48 2 12c0 4.42 2.87 8.17 6.84 9.5.5.09.66-.22.66-.48v-1.7c-2.78.6-3.37-1.34-3.37-1.34-.45-1.16-1.1-1.47-1.1-1.47-.9-.62.07-.6.07-.6 1 .07 1.52 1.02 1.52 1.02.89 1.52 2.34 1.08 2.91.83.09-.65.35-1.08.63-1.33-2.22-.25-4.56-1.11-4.56-4.94 0-1.09.39-1.98 1.03-2.68-.1-.25-.45-1.27.1-2.64 0 0 .84-.27 2.75 1.02A9.56 9.56 0 0 1 12 6.8c.85.004 1.7.114 2.5.334 1.9-1.29 2.74-1.02 2.74-1.02.55 1.37.2 2.39.1 2.64.64.7 1.03 1.59 1.03 2.68 0 3.84-2.34 4.68-4.57 4.93.36.31.68.92.68 1.85v2.75c0 .27.16.58.67.48A10.01 10.01 0 0 0 22 12C22 6.48 17.52 2 12 2z"/></svg>`,
        reddit: `<svg class="svg-icon" viewBox="0 0 24 24" style="background:#FF4500; border-radius:50%; padding:1px;"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm5.88 11.27a1.5 1.5 0 0 1-1.5 1.5c-.43 0-.82-.18-1.1-.47-.96.67-2.3 1.1-3.79 1.15l.64 3.02 2.08-.44a1.1 1.1 0 1 1 .15.73l-2.32.49c-.1.02-.2-.04-.23-.14l-.71-3.37c-1.5-.04-2.85-.47-3.82-1.14-.28.29-.67.47-1.1.47a1.5 1.5 0 0 1-.27-2.97c-.02-.15-.03-.3-.03-.45 0-2.23 2.43-4.04 5.43-4.04s5.43 1.81 5.43 4.04c0 .15-.01.3-.03.45.43.14.75.55.75 1.03l.02-.87zm-8.88.23a1.1 1.1 0 1 1 2.2 0 1.1 1.1 0 0 1-2.2 0zm5.35 2.81s-.87.87-2.35.87-2.35-.87-2.35-.87c-.13-.13-.13-.33 0-.46.13-.13.33-.13.46 0 0 0 .7.66 1.89.66s1.89-.66 1.89-.66c.13-.13.33-.13.46 0 .13.13.13.33 0 .46zm-.05-1.71a1.1 1.1 0 1 1 2.2 0 1.1 1.1 0 0 1-2.2 0z" fill="white"/></svg>`,
        youtube: `<svg class="svg-icon" viewBox="0 0 24 24" style="background:#FF0000; border-radius:6px; padding:2px;"><path d="M21.8 8s-.2-1.4-.8-2c-.77-.8-1.63-.81-2.02-.86C16.24 5 12 5 12 5s-4.24 0-6.98.14c-.4.05-1.25.06-2.02.86-.6.6-.8 2-.8 2S2 9.6 2 11.2v1.5c0 1.6.2 3.2.2 3.2s.2 1.4.8 2c.77.8 1.79.78 2.24.86C6.8 19 12 19 12 19s4.24 0 6.98-.16c.4-.05 1.25-.06 2.02-.86.6-.6.8-2 .8-2s.2-1.6.2-3.2v-1.5C22 9.6 21.8 8 21.8 8zM9.75 14.85V9.15l5.5 2.85-5.5 2.85z" fill="white"/></svg>`,
        pinterest: `<svg class="svg-icon" viewBox="0 0 24 24" style="background:#E60023; border-radius:50%; padding:1px;"><path d="M12 2C6.48 2 2 6.48 2 12c0 4.24 2.65 7.86 6.39 9.29-.09-.78-.17-1.98.04-2.83.18-.77 1.23-5.22 1.23-5.22s-.31-.63-.31-1.56c0-1.46.85-2.55 1.9-2.55.9 0 1.33.67 1.33 1.48 0 .9-.57 2.26-.87 3.52-.25 1.05.52 1.9 1.55 1.9 1.86 0 3.11-2.4 3.11-5.25 0-2.17-1.47-3.69-3.57-3.69-2.43 0-3.86 1.82-3.86 3.7 0 .73.28 1.52.63 1.94.07.08.08.16.06.24-.06.26-.2.82-.23.93-.04.15-.13.18-.3.11-1.12-.52-1.82-2.17-1.82-3.49 0-2.84 2.06-5.44 5.94-5.44 3.12 0 5.54 2.22 5.54 5.19 0 3.1-1.95 5.59-4.65 5.59-.91 0-1.76-.47-2.05-1.03l-.56 2.09c-.2.78-.75 1.76-1.12 2.35.85.26 1.74.4 2.67.4 5.52 0 10-4.48 10-10S17.52 2 12 2z" fill="white"/></svg>`,
        koo: `<svg class="svg-icon" viewBox="0 0 24 24" style="background:#FFCC00; border-radius:8px; padding:2px;"><text x="4" y="17" font-size="13" font-weight="bold" fill="#2d2d2d">koo</text></svg>`,
        sharechat: `<svg class="svg-icon" viewBox="0 0 24 24" style="background:#3DB97D; border-radius:8px; padding:2px;"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" fill="white"/></svg>`,
        moj: `<svg class="svg-icon" viewBox="0 0 24 24" style="background:#9B59B6; border-radius:50%; padding:2px;"><circle cx="12" cy="12" r="8" fill="white" fill-opacity="0.2"/><path d="M10 8l6 4-6 4V8z" fill="white"/></svg>`
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

    // 1. Associated Accounts Rows
    const assocAccounts = (data.reverse_lookup_results && data.reverse_lookup_results.associated_accounts) || [];
    let assocAccountsRows = "";
    if (assocAccounts.length > 0) {
        assocAccounts.forEach(acc => {
            assocAccountsRows += `
            <tr>
                <td><strong>@${acc.username}</strong></td>
                <td>${acc.platform.toUpperCase()}</td>
                <td>${acc.source}</td>
                <td>${Math.round(acc.confidence * 100)}%</td>
                <td>${acc.evidence || "N/A"}</td>
            </tr>`;
        });
    } else {
        assocAccountsRows = `<tr><td colspan="5" style="text-align: center; color: #555;">No associated accounts detected.</td></tr>`;
    }

    // 2. Secret Profiles Rows
    const secretVariations = (data.reverse_lookup_results && data.reverse_lookup_results.keyword_profile && data.reverse_lookup_results.keyword_profile.username_variations) || [];
    let secretProfilesRows = "";
    if (secretVariations.length > 0) {
        secretVariations.forEach(v => {
            secretProfilesRows += `
            <tr>
                <td style="font-family: monospace;"><strong>${v}</strong></td>
                <td>Alias Handle Candidate</td>
                <td>Keyword similarity profiling</td>
            </tr>`;
        });
    } else {
        secretProfilesRows = `<tr><td colspan="3" style="text-align: center; color: #555;">No username variations/aliases identified.</td></tr>`;
    }

    // 3. Personality Profile Summary
    const profileType = (data.reverse_lookup_results && data.reverse_lookup_results.profile_type) || {};
    const traits = (data.intelligence_report && data.intelligence_report.intelligence_sections && data.intelligence_report.intelligence_sections.hashtag_intelligence && data.intelligence_report.intelligence_sections.hashtag_intelligence.key_discoveries && data.intelligence_report.intelligence_sections.hashtag_intelligence.key_discoveries.personality_indicators) || [];
    let personalityProfileHTML = "";
    if (profileType.primary_type) {
        let interestsHTML = (profileType.interests || []).map(i => `<span style="display: inline-block; background: #e0f2f1; color: #00796b; padding: 2px 6px; border-radius: 4px; font-size: 0.8rem; margin-right: 4px; margin-bottom: 4px;">${i}</span>`).join("");
        let traitsHTML = traits.map(t => `<li><strong>${t.trait}</strong> (${t.category}) - ${t.confidence} match</li>`).join("");
        personalityProfileHTML = `
            <div class="evidence-box">
                <strong>Dominant Profile Type:</strong> ${profileType.primary_type.replace(/_/g, ' ').toUpperCase()}<br>
                <strong>Confidence Level:</strong> ${Math.round(profileType.confidence * 100)}%<br>
                ${profileType.description ? `<strong>Description:</strong> ${profileType.description}<br>` : ""}
                ${profileType.professional_field ? `<strong>Professional Field:</strong> ${profileType.professional_field}<br>` : ""}
                <br>
                <strong>Interest Fingerprint:</strong><br>
                <div style="margin-top: 4px;">${interestsHTML || "None detected."}</div>
                ${traitsHTML ? `<br><strong>Personality Trait Indicators:</strong><ul>${traitsHTML}</ul>` : ""}
            </div>
        `;
    } else {
        personalityProfileHTML = `<p>Insufficient indicators to classify personality or interest fingerprint.</p>`;
    }

    // 4. Telegram Intelligence Summary
    const tgData = (data.scraped_data && data.scraped_data.telegram) || {};
    let telegramIntelligenceHTML = "";
    if (tgData.username) {
        let signalsText = "";
        if (tgData.verification_signals) {
            const vs = tgData.verification_signals;
            signalsText = `Verified: ${vs.is_verified ? "YES" : "NO"} | Scam: ${vs.is_scam ? "YES" : "NO"} | Fake: ${vs.is_fake ? "YES" : "NO"}`;
        }
        let mtprotoText = "";
        if (tgData.mtproto_status) {
            const ms = tgData.mtproto_status;
            mtprotoText = `MTProto Enabled: ${ms.enabled ? "YES" : "NO"} | Session File: ${ms.session_file_present ? "FOUND" : "NOT FOUND"}`;
        }
        telegramIntelligenceHTML = `
            <div class="evidence-box">
                <strong>Username:</strong> @${tgData.username}<br>
                <strong>Display Name:</strong> ${tgData.full_name || "N/A"}<br>
                <strong>Entity Type:</strong> ${(tgData.entity_type || "user").toUpperCase()}<br>
                ${tgData.subscriber_count ? `<strong>Subscribers/Members:</strong> ${Number(tgData.subscriber_count).toLocaleString()}<br>` : ""}
                ${tgData.bio ? `<strong>Biography:</strong> ${tgData.bio}<br>` : ""}
                ${signalsText ? `<strong>Security Signals:</strong> ${signalsText}<br>` : ""}
                ${mtprotoText ? `<strong>API Access:</strong> ${mtprotoText}<br>` : ""}
            </div>
        `;
    } else {
        telegramIntelligenceHTML = `<p>No Telegram intelligence cached for this target username.</p>`;
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
        const conf = m.exists === true ? 85 : m.exists === null ? 0 : 5;
        const confClass = m.exists === true ? "finding-high" : m.exists === null ? "" : "";
        const evidenceStr = m.exists === true
            ? `MATCH IDENTIFIED. Active profile URL resolved status ${m.status_code}. Path: ${m.url}`
            : m.exists === null
            ? `INCONCLUSIVE. ${m.note || 'Platform blocked automated check (HTTP ' + m.status_code + ')'}. Manual verification required.`
            : `ABSENT. Profile resolution returned status ${m.status_code || "Timeout"}.`;

        matchesRows += `
        <tr>
            <td>${m.platform.toUpperCase()}</td>
            <td>${pData.username}</td>
            <td class="${confClass}">${m.exists === null ? 'N/A' : conf + '%'}</td>
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

    <h4>3.2a Guessed Email Addresses (UNVERIFIED — Pattern-Generated, NOT Confirmed)</h4>
    <p style="background:#fff3cd; border:1px solid #ffc107; padding:6px 10px; font-size:10pt; border-radius:4px;">⚠️ The following email addresses were algorithmically generated from the username pattern. They have <strong>NOT been verified</strong> and may not be real. Do not use as confirmed contact data.</p>
    ${(() => {
        const guessedEmails = (data.intelligence_report && data.intelligence_report.executive_summary && data.intelligence_report.executive_summary.contact_information && data.intelligence_report.executive_summary.contact_information.emails) || [];
        if (guessedEmails.length === 0) return '<p style="color:#555;">No email patterns generated.</p>';
        return '<ul>' + guessedEmails.map(e => `<li style="color:#856404; font-family:monospace;">${e} <em>(unverified guess)</em></li>`).join('') + '</ul>';
    })()}
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
    
    <h4>4.4 Associated Accounts Discovery</h4>
    <table>
        <thead>
            <tr>
                <th style="width: 25%;">Username</th>
                <th style="width: 20%;">Platform</th>
                <th style="width: 20%;">Source</th>
                <th style="width: 15%;">Confidence</th>
                <th style="width: 20%;">Evidence Snippet</th>
            </tr>
        </thead>
        <tbody>
            ${assocAccountsRows}
        </tbody>
    </table>

    <h4>4.5 Secret Profiles / Alias Candidates</h4>
    <table>
        <thead>
            <tr>
                <th>Variation / Alias</th>
                <th>Type</th>
                <th>Profiling Method</th>
            </tr>
        </thead>
        <tbody>
            ${secretProfilesRows}
        </tbody>
    </table>

    <h4>4.6 Personality Profile & Interest Fingerprint</h4>
    ${personalityProfileHTML}

    <h4>4.7 Telegram Intelligence</h4>
    ${telegramIntelligenceHTML}
    
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
        const exists = match.exists;  // true | false | null (inconclusive)
        const card = document.createElement("div");
        card.className = `platform-intel-card ${isPrimary ? 'status-primary' : (exists === true ? 'status-found' : exists === null ? 'status-inconclusive' : 'status-absent')}`;

        const svgIcon = getPlatformSVG(match.platform);
        const badgeText = exists === true ? "Profile found" : exists === null ? "Inconclusive" : "Profile absent";
        const badgeClass = exists === true ? "match-badge match-found" : exists === null ? "match-badge match-inconclusive" : "match-badge match-absent";
        const codeText = match.status_code ? `HTTP ${match.status_code}` : (exists === true ? "RESOLVED" : exists === null ? "BLOCKED" : "TIMEOUT");

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
    const svg = btn.querySelector(".platform-intel-toggle-icon svg") || btn.querySelector("svg");
    if (isExpanded) {
        el.classList.remove("expanded");
        if (svg) svg.style.transform = "rotate(0deg)";
    } else {
        el.classList.add("expanded");
        if (svg) svg.style.transform = "rotate(180deg)";
        
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
    const span = btn.querySelector(".toggle-text") || btn.querySelector("span");
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
    if (container) {
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

    const skeletonHTML = `
        <div class="skeleton-pulse" style="display:flex; flex-direction:column; gap:8px; padding:10px;">
            <div class="skeleton-block" style="width:55%; height:12px; background:rgba(255,255,255,0.06); border-radius:4px;"></div>
            <div class="skeleton-block" style="width:90%; height:20px; background:rgba(255,255,255,0.06); border-radius:4px;"></div>
            <div class="skeleton-block" style="width:40%; height:12px; background:rgba(255,255,255,0.06); border-radius:4px;"></div>
        </div>
    `;

    ["associated-accounts-results", "secret-profiles-results", "personality-profile-results", "telegram-intel-results", "dorking-results-container"].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.innerHTML = skeletonHTML;
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

