/**
 * Law Enforcement Agency (LEA) Official Investigation Report Exporter for Beta-v2.
 * Conforms 100% to docs/report-templates/official_investigation_report.html.html
 */

window.LeaPdfExporter = {
  generateReportHtml: function (data) {
    const escapeHTML = (val) => String(val ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");

    const targetQuery = data.target_query || data.username || "UNKNOWN";
    const consolidated = data.consolidated_identity || {};
    const aiPersonality = data.ai_personality || {};
    const wmnData = data.wmn_results || {};
    const wmnHits = wmnData.hits || [];
    const dorking = data.dorking_results || {};
    const dorkHits = dorking.results || [];
    const ctiData = data.telegram_cti || {};
    const ctiResults = ctiData.results || [];
    const internalMatches = data.internal_database_matches || {};
    const internalList = internalMatches.matches || [];

    const currentDate = new Date().toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });
    const caseId = data.investigation_id || "UPP-INTEL-2026-001";
    const officerName = "Special Investigator Ark Agrawal (ID: UPP-811)";

    // Internal DB Rows
    let internalDbRows = internalList.map(m => `
      <tr>
        <td>${escapeHTML(m.username || "-")}</td>
        <td>${escapeHTML(m.alt_username || "-")}</td>
        <td>${escapeHTML(m.phone || "-")}</td>
        <td>${escapeHTML(m.email || "-")}</td>
        <td>${escapeHTML(m.data_source || "HiTek Registry")}</td>
      </tr>
    `).join("");

    if (!internalList.length) {
      internalDbRows = `<tr><td colspan="5" style="text-align: center; color: #555;">No records matched in internal target databases.</td></tr>`;
    }

    // WMN Presence Rows
    let wmnRows = wmnHits.map(h => `
      <tr>
        <td>${escapeHTML(h.site)}</td>
        <td>${escapeHTML(h.handle || targetQuery)}</td>
        <td style="color:#2E9E5B; font-weight:bold;">FOUND (${h.ms}ms)</td>
        <td><a href="${escapeHTML(h.url)}" target="_blank">${escapeHTML(h.url)}</a></td>
      </tr>
    `).join("");

    if (!wmnHits.length) {
      wmnRows = `<tr><td colspan="4" style="text-align: center; color: #555;">No cross-platform WMN profile hits recorded.</td></tr>`;
    }

    // Dorking Rows
    let dorkingRows = dorkHits.map(r => `
      <tr>
        <td><strong>${escapeHTML(r.category || "Web Search")}</strong></td>
        <td><a href="${escapeHTML(r.url)}" target="_blank">${escapeHTML(r.title || "Hit")}</a><br><small>${escapeHTML(r.domain || "")}</small></td>
        <td>${escapeHTML(r.snippet || "")}</td>
        <td><small>${escapeHTML(r.query || "")}</small></td>
      </tr>
    `).join("");

    if (!dorkHits.length) {
      dorkingRows = `<tr><td colspan="4" style="text-align: center; color: #555;">No organic search results resolved via Google Dorking.</td></tr>`;
    }

    // Email deliverability list
    const emailsList = consolidated.emails || [];
    let emailsHTML = emailsList.map(e => `
      <li>${escapeHTML(e.email)} — <strong>${escapeHTML(e.status)}</strong></li>
    `).join("");

    return `<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Official LEA Investigation Report - ${escapeHTML(targetQuery)}</title>
    <style>
        body { font-family: 'Times New Roman', serif; font-size: 12pt; line-height: 1.5; margin: 2cm; color: #000; background: #fff; }
        .header { text-align: center; border-bottom: 2px solid #000; margin-bottom: 20px; }
        .confidential { color: red; font-weight: bold; text-align: center; border: 2px solid red; padding: 5px; margin: 10px 0; }
        .section-title { font-weight: bold; font-size: 14pt; margin-top: 20px; border-bottom: 1px solid #333; text-transform: uppercase; }
        .evidence-box { border: 1px solid #999; padding: 10px; background: #f5f5f5; margin: 10px 0; }
        table { width: 100%; border-collapse: collapse; margin: 10px 0; }
        th, td { border: 1px solid #333; padding: 6px; text-align: left; font-size: 10.5pt; }
        th { background: #333; color: white; }
        @media print { body { margin: 1cm; } .no-print { display: none; } }
    </style>
</head>
<body>
    <div class="no-print" style="margin-bottom:20px; text-align:right;">
        <button onclick="window.print()" style="padding:8px 16px; background:#000; color:#fff; font-size:14px; font-weight:bold; cursor:pointer; border:none; border-radius:4px;">🖨️ Print / Save as PDF</button>
    </div>

    <div class="header">
        <h1>CYBERCRIME INVESTIGATION REPORT</h1>
        <p>LAW ENFORCEMENT USE ONLY — UTTAR PRADESH POLICE CYBER CELL</p>
    </div>
    
    <div class="confidential">
        ⚠️ CONFIDENTIAL - RESTRICTED ACCESS - INVESTIGATIVE MATERIAL
    </div>
    
    <h2>MAIN HEADING</h2>
    <p>Open-Source Intelligence Assessment for Subject Target: <strong>${escapeHTML(targetQuery)}</strong></p>
    
    <h3>SUBJECT</h3>
    <p>Target Profile Alias / Handle: <strong>${escapeHTML(targetQuery)}</strong> (${escapeHTML(consolidated.likely_name || targetQuery)})</p>
    
    <h3>CASE DETAILS</h3>
    <table>
        <tr><td style="width:30%;">Case ID</td><td><strong>${escapeHTML(caseId)}</strong></td></tr>
        <tr><td>Investigating Officer</td><td>${escapeHTML(officerName)}</td></tr>
        <tr><td>Date of Investigation</td><td>${currentDate}</td></tr>
        <tr><td>AI Model Version</td><td>Groq llama-3.3-70b-versatile (Beta-v2 SOC Engine)</td></tr>
    </table>
    
    <div class="section-title">1. EXECUTIVE SUMMARY</div>
    <p>${escapeHTML(aiPersonality.summary || `Public-source OSINT scan completed for target ${targetQuery}. Identified ${wmnHits.length} cross-platform presences and ${ctiData.total_records || 0} breach database hits.`)}</p>

    <div class="section-title">2. CONSOLIDATED IDENTITY PROFILE</div>
    <table>
        <tr><td style="width:30%;">Likely Full Name</td><td>${escapeHTML(consolidated.likely_name || "N/A")}</td></tr>
        <tr><td>Location</td><td>${escapeHTML(consolidated.location || "N/A")}</td></tr>
        <tr><td>Behavioral Category</td><td>${escapeHTML(consolidated.profession || aiPersonality.primaryCategory || "N/A")}</td></tr>
        <tr><td>Identity Confidence</td><td>${consolidated.confidence_percentage || 0}% (${escapeHTML((consolidated.overall_confidence || "low").toUpperCase())})</td></tr>
    </table>

    <h4>Verified &amp; Pattern-Checked Emails</h4>
    <ul>${emailsHTML || "<li>No email addresses discovered.</li>"}</ul>
    
    <div class="section-title">3. PROFILE &amp; INTERNAL REGISTRY MATCHES</div>
    <table>
        <thead>
            <tr>
                <th>Username</th>
                <th>Alt Username</th>
                <th>Phone</th>
                <th>Email</th>
                <th>Source</th>
            </tr>
        </thead>
        <tbody>
            ${internalDbRows}
        </tbody>
    </table>
    
    <div class="section-title">4. CROSS-PLATFORM CORRELATION</div>
    <h4>4.1 WhatsMyName Probe Matrix (700+ Templates)</h4>
    <table>
        <thead>
            <tr>
                <th>Platform</th>
                <th>Handle</th>
                <th>Status</th>
                <th>URL Link</th>
            </tr>
        </thead>
        <tbody>
            ${wmnRows}
        </tbody>
    </table>

    <h4>4.2 Google Search Dorking Discovery</h4>
    <table>
        <thead>
            <tr>
                <th>Category</th>
                <th>Title / Source</th>
                <th>Snippet</th>
                <th>Query</th>
            </tr>
        </thead>
        <tbody>
            ${dorkingRows}
        </tbody>
    </table>
    
    <div class="section-title">5. AI BEHAVIORAL PROFILE &amp; RISK ASSESSMENT</div>
    <div class="evidence-box">
        <strong>Primary Category:</strong> ${escapeHTML(aiPersonality.primaryCategory || "Unable to Classify")}<br>
        <strong>Behavioral Traits:</strong> ${escapeHTML((aiPersonality.traits || []).join(", ") || "None")}<br>
        <strong>Detected Interests:</strong> ${escapeHTML((aiPersonality.interests || []).join(", ") || "None")}<br>
        <strong>Confidence:</strong> ${aiPersonality.confidence || 0}% (${escapeHTML(aiPersonality.confidenceLabel || "insufficient")})
    </div>
    
    <div class="section-title">6. RECOMMENDATIONS &amp; SIGN-OFF</div>
    <ol>
        <li>Perform lawful human verification before asserting common account ownership.</li>
        <li>Preserve public-source timestamps and provider logs for administrative reference.</li>
    </ol>
    
    <div style="margin-top: 50px;">
        <p>Report Generated by: UP Police Cyber Cell OSINT Platform (Beta-v2)</p>
        <p>Date: ${currentDate}</p>
        <p>Signature: ___________________________</p>
        <p>Name: ${escapeHTML(officerName)}</p>
        <p>Designation: Senior OSINT Investigator</p>
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
