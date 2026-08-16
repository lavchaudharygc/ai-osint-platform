/**
 * Law Enforcement Agency (LEA) Official Investigation Report Exporter for Beta-v2.
 * Comprehensive PDF Report generator with Official SVG Platform Badges,
 * Full Platform Dossier Cards, Telegram CTI Darkweb Leaks, Associated Accounts & AI Threat Analysis.
 */

window.LeaPdfExporter = {
  getPlatformBadge: function (platform) {
    const p = String(platform || "").toLowerCase();
    if (p.includes("linkedin")) {
      return `<span style="display:inline-flex;align-items:center;gap:6px;background:#0A66C2;color:#fff;padding:4px 10px;border-radius:4px;font-weight:bold;font-size:11px;">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="#fff"><path d="M19 3a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h14m-.5 15.5v-5.3a3.26 3.26 0 0 0-3.26-3.26c-.85 0-1.84.52-2.28 1.3v-1.11h-2.79v8.37h2.79v-4.93c0-.77.62-1.4 1.39-1.4a1.4 1.4 0 0 1 1.4 1.4v4.93h2.75M6.46 10.9v8.37H9.25V10.9H6.46M7.86 6.78a1.62 1.62 0 1 0 0 3.24 1.62 1.62 0 0 0 0-3.24z"/></svg>
        LinkedIn Dossier
      </span>`;
    }
    if (p.includes("instagram")) {
      return `<span style="display:inline-flex;align-items:center;gap:6px;background:linear-gradient(45deg,#f09433,#e6683c,#dc2743,#cc2366,#bc1888);color:#fff;padding:4px 10px;border-radius:4px;font-weight:bold;font-size:11px;">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="#fff"><path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z"/></svg>
        Instagram Profile
      </span>`;
    }
    if (p.includes("facebook")) {
      return `<span style="display:inline-flex;align-items:center;gap:6px;background:#1877F2;color:#fff;padding:4px 10px;border-radius:4px;font-weight:bold;font-size:11px;">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="#fff"><path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/></svg>
        Facebook Page / Profile
      </span>`;
    }
    if (p.includes("tiktok")) {
      return `<span style="display:inline-flex;align-items:center;gap:6px;background:#000;color:#fff;padding:4px 10px;border-radius:4px;font-weight:bold;font-size:11px;border:1px solid #333;">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="#25F4EE"><path d="M19.59 6.69a4.83 4.83 0 0 1-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 0 1-5.2 1.74 2.89 2.89 0 0 1 2.31-4.64c.29 0 .56.04.82.12V9.4a6.27 6.27 0 0 0-1-.08A6.34 6.34 0 0 0 3 15.66a6.34 6.34 0 0 0 10.86 4.43v-7a8.16 8.16 0 0 0 4.77 1.52v-3.4a4.85 4.85 0 0 1-1.04-.52z"/></svg>
        TikTok Account
      </span>`;
    }
    if (p.includes("telegram") || p.includes("cti")) {
      return `<span style="display:inline-flex;align-items:center;gap:6px;background:#24A1DE;color:#fff;padding:4px 10px;border-radius:4px;font-weight:bold;font-size:11px;">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="#fff"><path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.831-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/></svg>
        Telegram Darkweb CTI
      </span>`;
    }
    return `<span style="display:inline-flex;align-items:center;gap:6px;background:#333;color:#fff;padding:4px 10px;border-radius:4px;font-weight:bold;font-size:11px;">
      ${this.escapeHTML(platform)}
    </span>`;
  },

  escapeHTML: function (val) {
    return String(val ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  },

  generateReportHtml: function (data) {
    const esc = this.escapeHTML.bind(this);

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
    const scrapedData = data.scraped_data || {};
    const associatedAccounts = data.associated_accounts || [];

    const currentDate = new Date().toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });
    const currentTime = new Date().toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    const officerName = "Senior OSINT & Cyber Crime Investigator (ID: UPP-SOC-01)";
    const caseId = data.investigation_id || "UPP-" + Math.random().toString(16).substring(2, 10).toUpperCase();

    // --- 1. Scraped Platform Dossiers Cards HTML ---
    let platformCardsHTML = "";

    if (scrapedData.linkedin && scrapedData.linkedin.success) {
      const li = scrapedData.linkedin;
      const expList = (li.experience || []).map(e => `<li><strong>${esc(e.title || e.role || "Role")}</strong> at ${esc(e.company || e.organization || "")} <small>(${esc(e.duration || "")})</small></li>`).join("");
      const eduList = (li.education || []).map(e => `<li><strong>${esc(e.school || e.degree || "Education")}</strong> <small>${esc(e.field || "")}</small></li>`).join("");
      const honorsList = (li.honors || []).map(h => `<li>${esc(typeof h === "string" ? h : h.title || h.name)}</li>`).join("");

      let rrHTML = "";
      if (li.rocketreach && li.rocketreach.success) {
        const rr = li.rocketreach;
        const rrEmailsHTML = (rr.emails || []).map(e => `<span class="badge badge-info">${esc(e)}</span>`).join(" ");
        const rrPhonesHTML = (rr.phones || []).map(p => `<span class="badge badge-success">${esc(p)}</span>`).join(" ");
        rrHTML = `
        <div style="margin-top:10px; padding:8px; background:#f0f8ff; border:1px solid #add8e6; border-radius:4px; page-break-inside:avoid;">
          <strong style="font-size:11px; color:#0056b3;">🚀 ROCKETREACH CONTACT ENRICHMENT (CONFIRMED MATCH)</strong>
          ${rr.full_name ? `<div style="font-size:10px; margin-top:4px;"><strong>Full Name:</strong> ${esc(rr.full_name)} ${rr.current_title ? `· <em>${esc(rr.current_title)}</em>` : ''}</div>` : ''}
          ${rr.current_employer ? `<div style="font-size:10px;"><strong>Employer:</strong> ${esc(rr.current_employer)} ${rr.location ? `(${esc(rr.location)})` : ''}</div>` : ''}
          <div style="font-size:10px; margin-top:4px;">
            <strong>Emails:</strong> ${rrEmailsHTML || "None"}<br/>
            <strong>Phones:</strong> ${rrPhonesHTML || "None"}
          </div>
        </div>`;
      }

      platformCardsHTML += `
      <div class="card-box">
        <div class="card-header">
          ${this.getPlatformBadge("linkedin")}
          <span class="card-status status-success">ACTIVE PROFILE CONFIRMED</span>
        </div>
        <div class="card-body">
          <table class="card-table">
            <tr><td style="width:25%;">Full Name</td><td><strong>${esc(li.full_name || li.basic_info?.fullName || "N/A")}</strong></td></tr>
            <tr><td>Headline</td><td>${esc(li.headline || li.basic_info?.headline || "N/A")}</td></tr>
            <tr><td>Profile URL</td><td><a href="${esc(li.profile_url)}" target="_blank">${esc(li.profile_url || "N/A")}</a></td></tr>
            <tr><td>Location</td><td>${esc(li.location || li.basic_info?.location || "N/A")}</td></tr>
            <tr><td>Discovered Emails</td><td>${(li.emails || []).map(e => `<span class="badge badge-info">${esc(e)}</span>`).join(" ") || "None"}</td></tr>
            <tr><td>Discovered Phones</td><td>${(li.phone_numbers || li.phones || []).map(p => `<span class="badge badge-success">${esc(p)}</span>`).join(" ") || "None"}</td></tr>
          </table>
          ${rrHTML}
          ${expList ? `<h5 style="margin:10px 0 4px 0;">Work Experience</h5><ul>${expList}</ul>` : ""}
          ${eduList ? `<h5 style="margin:10px 0 4px 0;">Education</h5><ul>${eduList}</ul>` : ""}
          ${honorsList ? `<h5 style="margin:10px 0 4px 0;">Honors &amp; Awards</h5><ul>${honorsList}</ul>` : ""}
        </div>
      </div>`;
    }

    // RocketReach Card
    const rr = scrapedData.rocketreach || (scrapedData.linkedin && scrapedData.linkedin.rocketreach);
    if (rr && (rr.success || (rr.emails && rr.emails.length > 0) || (rr.phones && rr.phones.length > 0) || rr.full_name)) {
      const rrEmailsHTML = (rr.emails || []).map(e => `<span class="badge badge-info">${esc(e)}</span>`).join(" ");
      const rrPhonesHTML = (rr.phones || []).map(p => `<span class="badge badge-success">${esc(p)}</span>`).join(" ");
      const rrExpList = (rr.job_history || []).map(j => `<li><strong>${esc(j.title || "Role")}</strong> at ${esc(j.company || "")} <small>(${esc(j.duration || "")})</small></li>`).join("");

      platformCardsHTML += `
      <div class="card-box" style="border: 1px solid #add8e6; background: #f0f8ff;">
        <div class="card-header" style="background: #e6f2ff; display:flex; justify-content:space-between; align-items:center;">
          <span style="font-weight:bold; font-size:11px; color:#0056b3;">CONTACT ENRICHMENT DOSSIER</span>
          <span class="card-status status-success" style="background:#d4edda; color:#155724; border:1px solid #c3e6cb;">CONFIRMED MATCH</span>
        </div>
        <div class="card-body">
          <table class="card-table">
            <tr><td style="width:25%;">Full Name</td><td><strong>${esc(rr.full_name || "N/A")}</strong></td></tr>
            ${rr.current_title ? `<tr><td>Current Title</td><td>${esc(rr.current_title)}</td></tr>` : ""}
            ${rr.current_employer ? `<tr><td>Current Employer</td><td>${esc(rr.current_employer)}</td></tr>` : ""}
            ${rr.location ? `<tr><td>Location</td><td>${esc(rr.location)}</td></tr>` : ""}
            <tr><td>Resolved Emails</td><td>${rrEmailsHTML || "None"}</td></tr>
            <tr><td>Resolved Phones</td><td>${rrPhonesHTML || "None"}</td></tr>
          </table>
          ${rrExpList ? `<h5 style="margin:10px 0 4px 0;">Work History</h5><ul>${rrExpList}</ul>` : ""}
        </div>
      </div>`;
    }

    // Instagram Card
    if (scrapedData.instagram && scrapedData.instagram.success) {
      const ig = scrapedData.instagram;
      platformCardsHTML += `
      <div class="card-box">
        <div class="card-header">
          ${this.getPlatformBadge("instagram")}
          <span class="card-status status-success">PROFILE RESOLVED</span>
        </div>
        <div class="card-body">
          <table class="card-table">
            <tr><td style="width:25%;">Username</td><td><strong>@${esc(ig.username)}</strong></td></tr>
            <tr><td>Full Name</td><td>${esc(ig.full_name || "N/A")}</td></tr>
            <tr><td>Bio / Description</td><td>${esc(ig.bio || "N/A")}</td></tr>
            <tr><td>Metrics</td><td>${esc(ig.follower_count || 0)} Followers | ${esc(ig.following_count || 0)} Following | ${esc(ig.post_count || 0)} Posts</td></tr>
            <tr><td>Badges</td><td>Verified: ${ig.is_verified ? "YES" : "NO"} | Business: ${ig.is_business ? "YES" : "NO"}</td></tr>
            ${ig.external_url ? `<tr><td>External Link</td><td><a href="${esc(ig.external_url)}" target="_blank">${esc(ig.external_url)}</a></td></tr>` : ""}
          </table>
        </div>
      </div>`;
    }

    // Facebook Card
    if (scrapedData.facebook && scrapedData.facebook.success) {
      const fb = scrapedData.facebook;
      platformCardsHTML += `
      <div class="card-box">
        <div class="card-header">
          ${this.getPlatformBadge("facebook")}
          <span class="card-status status-success">PAGE / PROFILE FOUND</span>
        </div>
        <div class="card-body">
          <table class="card-table">
            <tr><td style="width:25%;">Title / Name</td><td><strong>${esc(fb.title || fb.page_name || fb.full_name || "N/A")}</strong></td></tr>
            <tr><td>Page URL</td><td><a href="${esc(fb.url)}" target="_blank">${esc(fb.url || "N/A")}</a></td></tr>
            <tr><td>Address / Location</td><td>${esc(fb.address || "N/A")}</td></tr>
            <tr><td>Category / Website</td><td>${esc(fb.categories?.join(", ") || fb.website || "N/A")}</td></tr>
            <tr><td>Likes / Followers</td><td>${esc(fb.likes_count || fb.likes || 0)} Likes | ${esc(fb.follower_count || 0)} Followers</td></tr>
          </table>
        </div>
      </div>`;
    }

    // TikTok Card
    if (scrapedData.tiktok) {
      const tt = scrapedData.tiktok;
      platformCardsHTML += `
      <div class="card-box">
        <div class="card-header">
          ${this.getPlatformBadge("tiktok")}
          <span class="card-status ${tt.success ? "status-success" : "status-warning"}">${tt.success ? "RESOLVED" : "ACCESSED (LIMITED)"}</span>
        </div>
        <div class="card-body">
          <table class="card-table">
            <tr><td style="width:25%;">Handle</td><td><strong>@${esc(tt.username)}</strong></td></tr>
            <tr><td>Status</td><td>${esc(tt.success ? "Active Account" : tt.error || "HTTP 400 Probe Response")}</td></tr>
          </table>
        </div>
      </div>`;
    }

    if (!platformCardsHTML) {
      platformCardsHTML = `<div style="text-align:center; padding:15px; color:#666; border:1px dashed #ccc;">No direct social platform dossiers scraped for this target query.</div>`;
    }

    // --- 2. Telegram CTI Darkweb Breach HTML ---
    let ctiRowsHTML = "";
    if (ctiResults.length > 0) {
      ctiResults.forEach(r => {
        const dbName = esc(r.database || r.query || "Leak Database");
        const infoLeak = esc(r.info_leak || r.infoLeak || "Breached Records Set");
        const rows = r.rows || r.data || [];

        rows.slice(0, 10).forEach(row => {
          let rowDetails = Object.entries(row)
            .map(([k, v]) => `<strong>${esc(k)}:</strong> ${esc(v)}`)
            .join(" | ");

          ctiRowsHTML += `
          <tr>
            <td><strong style="color:#d9534f;">${dbName}</strong></td>
            <td><small>${infoLeak.substring(0, 120)}...</small></td>
            <td>${rowDetails}</td>
          </tr>`;
        });
      });
    }

    if (!ctiRowsHTML) {
      ctiRowsHTML = `<tr><td colspan="3" style="text-align: center; color: #555;">No records matched in active darkweb leak databases.</td></tr>`;
    }

    // --- 3. Associated Accounts HTML ---
    let assocRowsHTML = associatedAccounts.map(a => `
      <tr>
        <td><strong>${esc(a.platform)}</strong></td>
        <td>${esc(a.username)}</td>
        <td><a href="${esc(a.url)}" target="_blank">${esc(a.url)}</a></td>
        <td><strong>${a.confidence}%</strong></td>
        <td><span class="badge badge-success">${esc(a.match_status || "VERIFIED")}</span></td>
      </tr>
    `).join("");

    if (!associatedAccounts.length) {
      assocRowsHTML = `<tr><td colspan="5" style="text-align: center; color: #555;">No associated cross-platform accounts identified.</td></tr>`;
    }

    // --- 4. Internal DB Rows ---
    let internalDbRows = internalList.map(m => `
      <tr>
        <td>${esc(m.username || "-")}</td>
        <td>${esc(m.alt_username || "-")}</td>
        <td>${esc(m.phone || "-")}</td>
        <td>${esc(m.email || "-")}</td>
        <td>${esc(m.data_source || "HiTek Registry")}</td>
      </tr>
    `).join("");

    if (!internalList.length) {
      internalDbRows = `<tr><td colspan="5" style="text-align: center; color: #555;">No records matched in internal target registries.</td></tr>`;
    }

    // --- 5. WMN Probe Rows ---
    let wmnRows = wmnHits.map(h => `
      <tr>
        <td>${esc(h.site)}</td>
        <td>${esc(h.handle || targetQuery)}</td>
        <td style="color:#2E9E5B; font-weight:bold;">FOUND (${h.ms}ms)</td>
        <td><a href="${esc(h.url)}" target="_blank">${esc(h.url)}</a></td>
      </tr>
    `).join("");

    if (!wmnHits.length) {
      wmnRows = `<tr><td colspan="4" style="text-align: center; color: #555;">No cross-platform WMN profile hits recorded.</td></tr>`;
    }

    // --- 6. Dorking Rows ---
    let dorkingRows = dorkHits.map(r => `
      <tr>
        <td><strong>${esc(r.category || "Web Search")}</strong></td>
        <td><a href="${esc(r.url)}" target="_blank">${esc(r.title || "Hit")}</a><br><small>${esc(r.domain || "")}</small></td>
        <td>${esc(r.snippet || "")}</td>
        <td><small>${esc(r.query || "")}</small></td>
      </tr>
    `).join("");

    if (!dorkHits.length) {
      dorkingRows = `<tr><td colspan="4" style="text-align: center; color: #555;">No organic search results resolved via Google Dorking.</td></tr>`;
    }

    // --- 7. Email deliverability list ---
    const emailsList = consolidated.emails || [];
    let emailsHTML = emailsList.map(e => `
      <li><strong>${esc(e.email)}</strong> — <span style="color:${e.status === 'verified' ? '#2E9E5B' : '#d9534f'}; font-weight:bold;">${esc(e.status?.toUpperCase())}</span> <small>(${esc(e.reason || "")})</small></li>
    `).join("");

    // --- 9. Risk Flags ---
    const riskFlags = aiPersonality.riskFlags || [];
    const riskFlagsHTML = riskFlags.map(f => {
      const label = typeof f === 'string' ? f : (f.label || f.flag || 'Unknown');
      const severity = typeof f === 'object' ? (f.severity || 'low') : 'medium';
      const badgeClass = severity === 'high' || severity === 'critical' ? 'badge-danger' : 'badge-warning';
      return `<span class="badge ${badgeClass}">${esc(label)} (${esc(severity)})</span>`;
    }).join(" ");


    // --- 8. Media Gallery HTML ---
    const mediaItems = [];
    const mediaPlatforms = ["instagram", "linkedin", "tiktok", "twitter", "facebook"];
    mediaPlatforms.forEach(plat => {
      const info = scrapedData[plat] || {};
      const pic = info.profile_pic_url || info.profile_pic_hd || (info.basic_info && (info.basic_info.profile_picture_url || info.basic_info.profile_pic_url));
      if (pic) {
        mediaItems.push({
          url: pic,
          source: plat.toUpperCase(),
          caption: `Profile photo resolved on ${plat.toUpperCase()}`
        });
      }
    });

    if (scrapedData.instagram && Array.isArray(scrapedData.instagram.posts)) {
      scrapedData.instagram.posts.forEach(post => {
        if (post.display_url) {
          mediaItems.push({
            url: post.display_url,
            source: "INSTAGRAM",
            caption: post.caption ? post.caption.substring(0, 100) + "..." : "Instagram post media"
          });
        }
      });
    }

    if (scrapedData.facebook) {
      const fb = scrapedData.facebook;
      if (fb.cover_image_url) {
        mediaItems.push({
          url: fb.cover_image_url,
          source: "FACEBOOK",
          caption: `Facebook cover photo for ${fb.page_name || fb.username || ''}`
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
                  caption: post.text ? post.text.substring(0, 100) + "..." : "Facebook post photo"
                });
              }
            });
          }
        });
      }
    }

    let mediaGalleryHTML = "";
    if (mediaItems.length > 0) {
      const gridItems = mediaItems.map(item => `
        <div style="border: 1px solid #ddd; border-radius: 4px; overflow: hidden; background: #f9f9f9; padding: 6px; text-align: center; page-break-inside: avoid;">
          <img src="${esc(item.url)}" referrerpolicy="no-referrer" style="width: 100%; height: 110px; object-fit: cover; border-radius: 3px; display: block; margin-bottom: 4px;" onerror="if(!this.dataset.proxied){this.dataset.proxied='true';this.src='${(typeof API_BASE !== 'undefined' ? API_BASE : 'http://127.0.0.1:8010')}/api/v1/investigation/proxy_image?url='+encodeURIComponent('${esc(item.url)}');}else{this.style.display='none';}">
          <div style="font-size: 8pt; font-weight: bold; color: #006699; margin-bottom: 2px;">${esc(item.source)}</div>
          <div style="font-size: 7.5pt; color: #555; height: 26px; overflow: hidden; text-overflow: ellipsis;">${esc(item.caption)}</div>
        </div>
      `).join("");
      mediaGalleryHTML = `<div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); gap: 10px; margin-top: 10px;">${gridItems}</div>`;
    } else {
      mediaGalleryHTML = `<p><small style="color: #666;">No media files or post images extracted for this target.</small></p>`;
    }

    return `<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Official LEA Investigation Dossier - ${esc(targetQuery)}</title>
    <style>
        body { font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 11pt; line-height: 1.5; margin: 1.5cm; color: #111; background: #fff; }
        .header { text-align: center; border-bottom: 3px double #000; padding-bottom: 12px; margin-bottom: 20px; }
        .header h1 { margin: 0; font-size: 20pt; font-weight: bold; letter-spacing: 1px; color: #000; }
        .header p { margin: 4px 0 0 0; font-size: 10pt; font-weight: bold; color: #333; }
        .confidential { color: #d9534f; font-weight: bold; text-align: center; border: 2px solid #d9534f; padding: 6px; margin: 12px 0; background: #fff5f5; font-size: 11pt; letter-spacing: 1px; }
        .section-title { font-weight: bold; font-size: 12pt; margin-top: 24px; margin-bottom: 10px; border-bottom: 2px solid #222; padding-bottom: 4px; text-transform: uppercase; color: #111; }
        .card-box { border: 1px solid #ccc; border-radius: 6px; margin-bottom: 14px; background: #fafafa; overflow: hidden; page-break-inside: avoid; }
        .card-header { background: #eee; padding: 8px 12px; border-bottom: 1px solid #ddd; display: flex; justify-content: space-between; align-items: center; }
        .card-status { font-size: 10px; font-weight: bold; padding: 2px 8px; border-radius: 3px; }
        .status-success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .status-warning { background: #fff3cd; color: #856404; border: 1px solid #ffeeba; }
        .card-body { padding: 12px; font-size: 10pt; }
        .card-table { width: 100%; border: none; margin: 0; }
        .card-table td { border: none; border-bottom: 1px solid #eee; padding: 4px 6px; }
        table { width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 10pt; }
        th, td { border: 1px solid #444; padding: 6px 8px; text-align: left; }
        th { background: #222; color: #fff; font-size: 9.5pt; text-transform: uppercase; }
        .badge { display: inline-block; padding: 3px 8px; border-radius: 3px; font-size: 9.5pt; margin-right: 4px; margin-bottom: 4px; }
        .badge-danger { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        .badge-warning { background: #fff3cd; color: #856404; border: 1px solid #ffeeba; }
        .badge-info { background: #d1ecf1; color: #0c5460; border: 1px solid #bee5eb; }
        .badge-success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .evidence-box { border: 1px solid #bbb; padding: 12px; background: #f9f9f9; margin: 10px 0; border-radius: 4px; }
        @media print { body { margin: 1cm; } .no-print { display: none; } }
    </style>
</head>
<body>
    <div class="no-print" style="margin-bottom:20px; text-align:right;">
        <button onclick="window.print()" style="padding:10px 20px; background:#000; color:#fff; font-size:14px; font-weight:bold; cursor:pointer; border:none; border-radius:6px;">Print / Save Official PDF Report</button>
    </div>

    <div class="header">
        <div style="display:flex; align-items:center; justify-content:center; gap:12px; margin-bottom:8px;">
            <svg width="42" height="42" viewBox="0 0 24 24" fill="#002147"><path d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-5.45 9-12V5l-9-4zm0 4.18l5 2.22v4.6c0 3.3-2.18 6.44-5 7.42-2.82-.98-5-4.12-5-7.42V7.4s.001 0 5-2.22z"/></svg>
            <div>
                <h1>UP POLICE CYBER CRIME HEADQUARTERS</h1>
                <p>LAW ENFORCEMENT OFFICIAL OSINT &amp; CYBER THREAT ASSESSMENT REPORT</p>
            </div>
        </div>
    </div>
    
    <div class="confidential">
        CONFIDENTIAL // LAW ENFORCEMENT SENSITIVE // RESTRICTED ACCESS
    </div>
    
    <table style="margin-top:15px; margin-bottom:20px;">
        <tr><td style="width:25%; background:#eee;"><strong>Case ID / Reference</strong></td><td><strong>${esc(caseId)}</strong></td><td style="width:20%; background:#eee;"><strong>Target Query</strong></td><td><strong>${esc(targetQuery)}</strong></td></tr>
        <tr><td style="background:#eee;"><strong>Investigating Unit</strong></td><td>${esc(officerName)}</td><td style="background:#eee;"><strong>Date &amp; Time</strong></td><td>${currentDate} ${currentTime}</td></tr>
        <tr><td style="background:#eee;"><strong>Classification Kind</strong></td><td><strong>${esc((data.classified_kind || "username").toUpperCase())}</strong></td><td style="background:#eee;"><strong>AI Classifier Engines</strong></td><td>Consolidated AI Classifier Engines</td></tr>
    </table>
    
    <div class="section-title">1. EXECUTIVE SUMMARY &amp; CONSOLIDATED IDENTITY</div>
    <div class="evidence-box">
        <p style="margin-top:0;">${esc(aiPersonality.summary || `Public-source OSINT scan completed for target ${targetQuery}. Identified ${wmnHits.length} cross-platform presences and ${ctiData.total_records || 0} breach database hits.`)}</p>
    </div>

    <table>
        <tr><td style="width:30%; background:#eee;"><strong>Likely Full Name</strong></td><td><strong>${esc(consolidated.likely_name || "N/A")}</strong></td></tr>
        <tr><td style="background:#eee;"><strong>Location / Clues</strong></td><td>${esc(consolidated.location || "N/A")}</td></tr>
        <tr><td style="background:#eee;"><strong>Behavioral Classification</strong></td><td><strong>${esc(consolidated.profession || aiPersonality.primaryCategory || "N/A")}</strong></td></tr>
        <tr><td style="background:#eee;"><strong>Identity Confidence Score</strong></td><td><strong style="font-size:12pt; color:#2E9E5B;">${consolidated.confidence_percentage || 0}%</strong> (${esc((consolidated.overall_confidence || "low").toUpperCase())})</td></tr>
    </table>

    <h4 style="margin-top:14px; margin-bottom:6px;">Discovered &amp; Verified Email Addresses</h4>
    <ul>${emailsHTML || "<li>No email addresses discovered.</li>"}</ul>

    <div class="section-title">2. SCRAPED PLATFORM DOSSIERS &amp; CARDS</div>
    ${platformCardsHTML}

    <div class="section-title">3. TELEGRAM CTI DARKWEB BREACH &amp; LEAK DOSSIER</div>
    <p><small>Matches retrieved from darkweb paste dumps, telecom subscriber leaks, and credential breach registries:</small></p>
    <table>
        <thead>
            <tr>
                <th style="width:25%;">Database / Source</th>
                <th style="width:30%;">Breach Context / Leak Details</th>
                <th>Exposed Record Fields (Address, DocNumber, Password, Phone)</th>
            </tr>
        </thead>
        <tbody>
            ${ctiRowsHTML}
        </tbody>
    </table>

    <div class="section-title">4. ASSOCIATED ACCOUNTS MATRIX</div>
    <table>
        <thead>
            <tr>
                <th>Platform</th>
                <th>Handle / Account</th>
                <th>URL Link</th>
                <th>Confidence</th>
                <th>Status</th>
            </tr>
        </thead>
        <tbody>
            ${assocRowsHTML}
        </tbody>
    </table>

    <div class="section-title">5. CROSS-PLATFORM PROBE &amp; SEARCH DISCOVERY</div>
    <h4>5.1 WhatsMyName Probe Matrix (700+ Templates)</h4>
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

    <h4>5.2 Google Search Dorking Discovery</h4>
    <table>
        <thead>
            <tr>
                <th>Category</th>
                <th>Title / Source</th>
                <th>Snippet</th>
                <th>Query Used</th>
            </tr>
        </thead>
        <tbody>
            ${dorkingRows}
        </tbody>
    </table>

    <div class="section-title">6. INTERNAL TARGET REGISTRY MATCHES</div>
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

    <div class="section-title">7. AI BEHAVIORAL PROFILING &amp; THREAT RISK ASSESSMENT</div>
    <div class="evidence-box">
        <p><strong>Behavioral Category:</strong> <span class="badge badge-info">${esc(aiPersonality.primaryCategory || "Unable to Classify")}</span></p>
        <p><strong>Behavioral Summary:</strong> ${esc(aiPersonality.summary || "N/A")}</p>
        <p><strong>Behavioral Traits:</strong> ${esc((aiPersonality.traits || []).join(", ") || "None")}</p>
        <p><strong>Detected Interests:</strong> ${esc((aiPersonality.interests || []).join(", ") || "None")}</p>
        <p><strong>Threat &amp; Risk Flags:</strong> ${riskFlagsHTML || "None detected"}</p>
        <p><strong>Cross-Platform Note:</strong> ${esc(aiPersonality.crossPlatformNote || "Verified across multiple data sources.")}</p>
    </div>

    <div class="section-title">8. RESOLVED MEDIA &amp; PHOTO EVIDENCE GALLERY</div>
    ${mediaGalleryHTML}

    <div class="section-title">9. LAW ENFORCEMENT RECOMMENDATIONS &amp; SIGN-OFF</div>
    <ol>
        <li>Perform lawful human verification before asserting common account ownership.</li>
        <li>Preserve public-source timestamps and provider logs for administrative reference.</li>
        <li>All material contained herein is compiled strictly from public-source OSINT and breach intelligence feeds for investigative lead generation.</li>
    </ol>
    
    <div style="margin-top: 40px; border-top: 1px solid #ccc; padding-top: 15px; page-break-inside: avoid;">
        <p><strong>Report Generated By:</strong> UP Police Cyber Crime HQ OSINT Platform (Beta-v2 SOC Engine)</p>
        <p><strong>Date &amp; Timestamp:</strong> ${currentDate} ${currentTime}</p>
        <p><strong>Authorized Investigator Signature:</strong> ___________________________</p>
        <p><strong>Investigating Unit:</strong> ${esc(officerName)}</p>
        <p><strong>Designation:</strong> Senior OSINT &amp; Cyber Crime Intelligence Unit</p>
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
