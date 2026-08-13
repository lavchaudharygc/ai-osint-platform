/**
 * Law Enforcement Agency (LEA) Official Investigation Report Exporter.
 * Conforms 100% to docs/report-templates/official_investigation_report.html.html
 */

window.LeaPdfExporter = {
  generateReportHtml: function (data) {
    const escapeHTML = (val) => String(val ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");

    const pData = data.platform_data || {};
    const scraped = data.scraped_data || {};
    const primaryProfile = Object.values(scraped).find(p => typeof p === "object" && p.success) || pData || {};
    const username = primaryProfile.username || data.username || "UNKNOWN";
    const fullName = primaryProfile.full_name || primaryProfile.name || "UNSPECIFIED";
    const bio = primaryProfile.bio || primaryProfile.description || "No biography details cached.";
    const followers = primaryProfile.followers || primaryProfile.follower_count || "UNKNOWN";
    const following = primaryProfile.following || primaryProfile.following_count || "UNKNOWN";
    const platform = (primaryProfile.platform || pData.platform || "GLOBAL_OSINT").toUpperCase();

    const currentDate = new Date().toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });
    const caseId = data.investigation_id || "UPP-INTEL-2026-001";
    const officerName = "Special Investigator Ark Agrawal (ID: UPP-811)";

    // WMN Hits for Social Network Presence Index
    const wmnSummary = data.wmn_summary || (scraped.wmn) || {};
    const wmnHits = wmnSummary.hits || [];
    const crossMatches = data.cross_platform_matches || [];

    // Internal Database Matches
    const internalMatches = data.internal_database_matches || {};
    const internalRowsList = [
      ...(internalMatches.by_username || []),
      ...(internalMatches.by_phone || []),
      ...(internalMatches.by_email || [])
    ];

    let internalDbRows = internalRowsList.map(m => `
      <tr>
        <td>${escapeHTML(m.username || "-")}</td>
        <td>${escapeHTML(m.alt_username || "-")}</td>
        <td>${escapeHTML(m.phone || "-")}</td>
        <td>${escapeHTML(m.email || "-")}</td>
        <td>${escapeHTML(m.data_source || "HiTek Registry")}</td>
      </tr>
    `).join("");

    if (!internalRowsList.length) {
      internalDbRows = `<tr><td colspan="5" style="text-align: center; color: #555;">No records matched in internal target databases.</td></tr>`;
    }

    // Social Network Presence Index Rows (WMN + Cross matches)
    let socialPresenceRows = wmnHits.map(h => `
      <tr>
        <td>${escapeHTML(h.site || h.platform)}</td>
        <td>${escapeHTML(h.handle || username)}</td>
        <td class="finding-high">FOUND</td>
        <td>Direct profile URL reachability probe hit: ${escapeHTML(h.url)}</td>
      </tr>
    `).join("");

    if (!socialPresenceRows && crossMatches.length > 0) {
      socialPresenceRows = crossMatches.map(m => `
        <tr>
          <td>${escapeHTML(m.platform || "Unknown")}</td>
          <td>${escapeHTML(m.username || username)}</td>
          <td class="${(m.confidence || 0) > 70 ? 'finding-high' : ''}">${m.confidence || 50}%</td>
          <td>${escapeHTML((m.reasons || []).join("; ") || "Cross-platform identity match candidate")}</td>
        </tr>
      `).join("");
    }

    if (!socialPresenceRows) {
      socialPresenceRows = `<tr><td colspan="4" style="text-align: center; color: #555;">No cross-platform profile hits recorded.</td></tr>`;
    }

    // Hashtag Analysis
    const hashtagAnalysis = data.hashtag_analysis || {};
    const hashtagsStr = (hashtagAnalysis.hashtags || []).join(", ") || "None extracted";
    const connections = hashtagAnalysis.potential_connections || [];
    let hashtagRows = connections.map(c => `
      <tr>
        <td><strong>@id:${escapeHTML(c.user)}</strong></td>
        <td>${c.frequency || 1} Overlaps</td>
        <td>${escapeHTML((c.hashtags || []).join(", "))}</td>
      </tr>
    `).join("");

    if (!connections.length) {
      hashtagRows = `<tr><td colspan="3" style="text-align: center; color: #555;">No multiple-hashtag connection links identified on network.</td></tr>`;
    }

    // Dorking Results
    const dorking = data.dorking_results || {};
    const dorkHits = dorking.results || [];
    let dorkingRows = dorkHits.slice(0, 15).map(r => `
      <tr>
        <td><strong>${escapeHTML(r.category || "General")}</strong></td>
        <td><a href="${escapeHTML(r.url || r.link)}" target="_blank">${escapeHTML(r.title || "Hit")}</a><br><small>${escapeHTML(r.domain || "")}</small></td>
        <td>${escapeHTML(r.snippet || "")}</td>
        <td><small>${escapeHTML(r.query || "")}</small></td>
      </tr>
    `).join("");

    if (!dorkHits.length) {
      dorkingRows = `<tr><td colspan="4" style="text-align: center; color: #555;">No organic results resolved via Google Dorking.</td></tr>`;
    }

    // Instagram Posts
    const igPosts = data.instagram_posts || {};
    const postsList = igPosts.posts || igPosts.reels || [];
    let igRows = postsList.slice(0, 10).map(p => `
      <tr>
        <td>${escapeHTML(p.taken_at || p.created_at || "N/A")}</td>
        <td>${escapeHTML(p.media_type || "Post")} (${escapeHTML(p.product_type || "feed")})</td>
        <td>${escapeHTML(p.caption || "No caption")}</td>
        <td>Likes: ${p.like_count || 0} | Comments: ${p.comment_count || 0}${p.location ? `<br>Location: ${escapeHTML(p.location.name)}` : ""}</td>
      </tr>
    `).join("");

    // AI Correlation / Personality
    const aiCorrelation = data.ai_correlation_result || {};
    const aiPersonality = data.ai_personality || {};
    const consolidated = data.consolidated_identity || {};

    const consolidationText = consolidated.likely_name 
      ? `Likely Name: ${consolidated.likely_name} | Location: ${consolidated.location || "N/A"} | Category: ${consolidated.profession || "N/A"} | Discovered Emails: ${(consolidated.emails || []).join(", ") || "None"}`
      : (aiCorrelation.parsed ? aiCorrelation.parsed.reasons?.join(". ") : "Insufficient cross-platform evidence to confirm single ownership.");

    const confidenceAssessmentText = consolidated.overall_confidence
      ? `Overall Identity Confidence: ${consolidated.confidence_percentage}% (${consolidated.overall_confidence.toUpperCase()}).`
      : (aiCorrelation.parsed ? `Confidence level: ${aiCorrelation.parsed.confidence}%. Decision: ${aiCorrelation.parsed.decision}.` : "Assessment pending additional corroborating evidence.");

    // Risk Assessment
    const risk = data.risk_assessment || {};
    const riskLevel = String(risk.level || risk.risk_level || "LOW").toUpperCase();
    const riskIndicators = risk.indicators || (risk.parsed ? risk.parsed.indicators : []) || [];
    let riskIndicatorsHTML = riskIndicators.map(i => `<li>${escapeHTML(i)}</li>`).join("");
    if (!riskIndicatorsHTML) riskIndicatorsHTML = "<li>No concrete indicators of harmful conduct identified in public evidence.</li>";

    // Recommendations
    const recommendationsList = [
      "Manually verify collector-confirmed public display names, biographies, and linked web domains.",
      "Preserve public-source timestamps and provider logs for administrative reference.",
      "Perform lawful human verification before asserting identity or common account ownership.",
      "Cross-reference discovered email addresses against official state registry databases."
    ];
    const recommendationsHTML = recommendationsList.map(r => `<li>${r}</li>`).join("");

    // Return exact HTML conforming to docs/report-templates/official_investigation_report.html.html
    return `<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Official LEA Investigation Report - ${escapeHTML(username)}</title>
    <style>
        /* Official LEA Report Styling conforming to docs/report-templates/official_investigation_report.html.html */
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
        }
        .section-title {
            font-weight: bold;
            font-size: 14pt;
            margin-top: 20px;
            border-bottom: 1px solid #333;
            text-transform: uppercase;
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
            padding: 5px;
            text-align: left;
        }
        th {
            background: #333;
            color: white;
        }
        @media print {
            body { margin: 1cm; }
            .no-print { display: none; }
        }
    </style>
</head>
<body>
    <div class="no-print" style="margin-bottom:20px; text-align:right;">
        <button onclick="window.print()" style="padding:8px 16px; background:#000; color:#fff; font-size:14px; font-weight:bold; cursor:pointer; border:none; border-radius:4px;">🖨️ Print / Save as PDF</button>
    </div>

    <div class="header">
        <h1>CYBERCRIME INVESTIGATION REPORT</h1>
        <p>LAW ENFORCEMENT USE ONLY</p>
    </div>
    
    <div class="confidential">
        ⚠️ CONFIDENTIAL - RESTRICTED ACCESS - INVESTIGATIVE MATERIAL
    </div>
    
    <h2>MAIN HEADING</h2>
    <p>Open-Source Intelligence Assessment for Subject Profile: <strong>${escapeHTML(username)}</strong></p>
    
    <h3>SUBJECT</h3>
    <p>Target Profile Alias / Handle: <strong>${escapeHTML(username)}</strong> (${escapeHTML(fullName)})</p>
    
    <h3>CASE DETAILS</h3>
    <table>
        <tr><td style="width:30%;">Case ID</td><td><strong>${escapeHTML(caseId)}</strong></td></tr>
        <tr><td>Investigating Officer</td><td>${escapeHTML(officerName)}</td></tr>
        <tr><td>Date of Investigation</td><td>${currentDate}</td></tr>
        <tr><td>Platform Investigated</td><td>${escapeHTML(platform)}</td></tr>
        <tr><td>AI-Assisted Analysis</td><td>Yes - Model Core v0.1.0</td></tr>
    </table>
    
    <div class="section-title">1. EXECUTIVE SUMMARY</div>
    <p>${escapeHTML(aiPersonality.summary || `Public-source investigation initiated for subject alias ${username}. Social network probes and automated dorking resolved multi-vector profiles across web domains. Risk level assessed as ${riskLevel}.`)}</p>
    
    <div class="section-title">2. INCIDENT OVERVIEW</div>
    <p>An automated open-source intelligence scan was conducted on ${currentDate} under reference ID ${escapeHTML(caseId)}. The primary target identifier was <strong>${escapeHTML(username)}</strong>. The objective was to catalog public web presence, evaluate cross-platform identity correlation, and identify potential threat flags.</p>
    
    <div class="section-title">3. PROFILE ANALYSIS</div>
    <h4>3.1 Primary Profile - ${escapeHTML(platform)}</h4>
    <table>
        <tr><td style="width:30%;">Username</td><td>${escapeHTML(username)}</td></tr>
        <tr><td>Display Name</td><td>${escapeHTML(fullName)}</td></tr>
        <tr><td>Account Created</td><td>N/A (Public Probe)</td></tr>
        <tr><td>Bio</td><td>${escapeHTML(bio)}</td></tr>
        <tr><td>Followers</td><td>${escapeHTML(String(followers))}</td></tr>
        <tr><td>Following</td><td>${escapeHTML(String(following))}</td></tr>
        <tr><td>Account Status</td><td>${escapeHTML(String(data.status || "COMPLETED").toUpperCase())}</td></tr>
    </table>
    
    <h4>3.2 Content Analysis</h4>
    <p>Public post content, metadata, and associated text excerpts were extracted. Behavioral alignment indicates primary category: <strong>${escapeHTML(aiPersonality.primaryCategory || "General User")}</strong> with traits: ${escapeHTML((aiPersonality.traits || []).join(", ") || "Standard User Profile")}.</p>
    
    <h4>3.3 Internal Database Registry Matches</h4>
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
            ${internalDbRows}
        </tbody>
    </table>
    
    <div class="section-title">4. CROSS-PLATFORM CORRELATION</div>
    <h4>4.1 Social Network Presence Index</h4>
    <table>
        <thead>
            <tr>
                <th>Platform</th>
                <th>Username</th>
                <th>Confidence</th>
                <th>Key Evidence</th>
            </tr>
        </thead>
        <tbody>
            ${socialPresenceRows}
        </tbody>
    </table>

    <h4>4.2 Hashtag Reverse Lookup Analysis</h4>
    <p><strong>Extracted Hashtags from Primary Profile:</strong> ${escapeHTML(hashtagsStr)}</p>
    <table>
        <thead>
            <tr>
                <th>Matched Twitter User</th>
                <th>Overlapping Frequency</th>
                <th>Overlapping Hashtags</th>
            </tr>
        </thead>
        <tbody>
            ${hashtagRows}
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

    <h4>4.4 Instagram Posts &amp; Reels Intelligence</h4>
    ${postsList.length > 0 ? `
    <p>Extracted <strong>${postsList.length}</strong> posts/reels.</p>
    <table>
        <thead>
            <tr>
                <th style="width: 20%;">Timestamp</th>
                <th style="width: 15%;">Media Type</th>
                <th style="width: 45%;">Caption Snippet</th>
                <th style="width: 20%;">Metrics / Location</th>
            </tr>
        </thead>
        <tbody>
            ${igRows}
        </tbody>
    </table>` : '<p>No Instagram posts/reels intelligence retrieved for this subject.</p>'}
    
    <div class="section-title">5. AI CORRELATION ANALYSIS</div>
    <div class="evidence-box">
        <strong>Identity Consolidation:</strong>
        <p>${escapeHTML(consolidationText)}</p>
        
        <strong>Confidence Assessment:</strong>
        <p>${escapeHTML(confidenceAssessmentText)}</p>
    </div>
    
    <div class="section-title">6. RISK ASSESSMENT</div>
    <p><strong>Risk Level:</strong> <span class="finding-${riskLevel.toLowerCase() === 'high' || riskLevel.toLowerCase() === 'critical' ? 'critical' : (riskLevel.toLowerCase() === 'medium' ? 'high' : 'normal')}">${escapeHTML(riskLevel)}</span></p>
    <p><strong>Indicators Found:</strong></p>
    <ul>
        ${riskIndicatorsHTML}
    </ul>
    
    <div class="section-title">7. CRITICAL DISCOVERIES</div>
    ${(data.telegram_cti && data.telegram_cti.total_records > 0)
        ? `<p class="finding-critical">⚠ Telegram CTI matched ${data.telegram_cti.total_records} records across ${data.telegram_cti.databases.length} databases.</p>`
        : '<p style="color:var(--text-secondary);">No critical threat indicators or leak database triggers identified.</p>'}
    
    <div class="section-title">8. EVIDENCE SUMMARY</div>
    <table>
        <thead>
            <tr><th>Evidence ID</th><th>Type</th><th>Source</th><th>Timestamp</th></tr>
        </thead>
        <tbody>
            <tr>
                <td>EVD-001</td>
                <td>Social Probe</td>
                <td>WhatsMyName / Social Scrapers</td>
                <td>${currentDate}</td>
            </tr>
            <tr>
                <td>EVD-002</td>
                <td>AI Behavioral Profile</td>
                <td>Groq / DeepSeek LLM Engine</td>
                <td>${currentDate}</td>
            </tr>
        </tbody>
    </table>
    
    <div class="section-title">9. RECOMMENDATIONS</div>
    <ol>
        ${recommendationsHTML}
    </ol>
    
    <div class="section-title">10. CONCLUSION</div>
    <p>Automated public-source collection completed. Human verification is required prior to taking any administrative action.</p>
    
    <div style="margin-top: 50px;">
        <p>Report Generated by: AI-OSINT Platform</p>
        <p>Date: ${currentDate}</p>
        <p>Signature: ___________________________</p>
        <p>Name: ${escapeHTML(officerName)}</p>
        <p>Designation: Analyst</p>
    </div>
</body>
</html>`;
  },

  exportReport: function (data) {
    if (!data) {
      alert("No active investigation data available to export.");
      return;
    }
    const htmlContent = this.generateReportHtml(data);
    const reportWindow = window.open("", "_blank");
    if (reportWindow) {
      reportWindow.document.open();
      reportWindow.document.write(htmlContent);
      reportWindow.document.close();
    } else {
      alert("Pop-up blocked! Please allow pop-ups for this site to open and print the LEA report.");
    }
  }
};
