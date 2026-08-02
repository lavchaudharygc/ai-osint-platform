/**
 * Law Enforcement Agency (LEA) PDF Exporter for AI-OSINT Platform.
 * Supports classification levels: public, internal, confidential, secret, top_secret.
 */

window.LeaPdfExporter = {
  classifications: {
    public: { label: "UNCLASSIFIED · PUBLIC RELEASE", watermark: "UNCLASSIFIED", bannerBg: [230, 245, 230], bannerFg: [30, 100, 30] },
    internal: { label: "INTERNAL USE ONLY · MASKED FIELDS", watermark: "INTERNAL", bannerBg: [235, 240, 255], bannerFg: [30, 60, 140] },
    confidential: { label: "CONFIDENTIAL · RESTRICTED ACCESS", watermark: "CONFIDENTIAL", bannerBg: [255, 235, 235], bannerFg: [140, 0, 0] },
    secret: { label: "SECRET · LAW ENFORCEMENT DECRYPTED CONTENT", watermark: "SECRET", bannerBg: [255, 220, 220], bannerFg: [160, 0, 0] },
    top_secret: { label: "TOP SECRET // NOFORN · FULL DECRYPT AUTHORIZED", watermark: "TOP SECRET", bannerBg: [40, 0, 0], bannerFg: [255, 220, 60] }
  },

  exportReport: function (data, classificationLevel) {
    classificationLevel = classificationLevel || "public";
    const conf = this.classifications[classificationLevel] || this.classifications.public;

    if (!window.jspdf || !window.jspdf.jsPDF) {
      alert("jsPDF library loading... Please ensure internet connection or CDN availability.");
      return;
    }

    const { jsPDF } = window.jspdf;
    const doc = new jsPDF({ unit: "mm", format: "a4" });

    // Draw header banner
    doc.setFillColor(conf.bannerBg[0], conf.bannerBg[1], conf.bannerBg[2]);
    doc.rect(0, 0, 210, 12, "F");

    doc.setTextColor(conf.bannerFg[0], conf.bannerFg[1], conf.bannerFg[2]);
    doc.setFontSize(10);
    doc.setFont("helvetica", "bold");
    doc.text(conf.label, 105, 8, { align: "center" });

    // Header Title
    doc.setTextColor(20, 20, 20);
    doc.setFontSize(18);
    doc.text("OFFICIAL INTELLIGENCE INVESTIGATION REPORT", 14, 25);

    doc.setFontSize(10);
    doc.setFont("helvetica", "normal");
    doc.text(`Generated: ${new Date().toLocaleString()}`, 14, 32);
    doc.text(`Target Query: ${data.query || data.username || "Unknown"}`, 14, 38);
    doc.text(`Engine Mode: ${data.engine_mode || "Standard"}`, 14, 44);

    let y = 55;

    // WMN Account Hits
    doc.setFontSize(14);
    doc.setFont("helvetica", "bold");
    doc.text("1. Cross-Platform Account Probes (WhatsMyName)", 14, y);
    y += 8;

    const wmnHits = data.wmn_summary ? data.wmn_summary.hits : [];
    if (wmnHits && wmnHits.length > 0) {
      const tableRows = wmnHits.map(h => [h.site || h.platform, h.category || "general", h.status || "found", h.url]);
      if (doc.autoTable) {
        doc.autoTable({
          startY: y,
          head: [["Platform", "Category", "Status", "URL"]],
          body: tableRows,
          theme: "grid",
          headStyles: { fillStyle: conf.bannerBg, textColor: conf.bannerFg }
        });
        y = doc.lastAutoTable.finalY + 12;
      } else {
        wmnHits.slice(0, 10).forEach(h => {
          doc.setFontSize(9);
          doc.setFont("helvetica", "normal");
          doc.text(`- [${h.site}] ${h.url}`, 14, y);
          y += 5;
        });
        y += 5;
      }
    } else {
      doc.setFontSize(10);
      doc.setFont("helvetica", "italic");
      doc.text("No cross-platform WMN profile hits recorded.", 14, y);
      y += 10;
    }

    // AI Personality & Risk
    if (data.ai_correlation_result || data.aiPersonality) {
      const ai = data.ai_correlation_result || data.aiPersonality;
      doc.setFontSize(14);
      doc.setFont("helvetica", "bold");
      doc.text("2. AI Behavioral & Personality Intelligence", 14, y);
      y += 8;

      doc.setFontSize(10);
      doc.setFont("helvetica", "normal");
      doc.text(`Summary: ${ai.summary || ai.narrative || "N/A"}`, 14, y, { maxWidth: 180 });
      y += 12;
      doc.text(`Primary Category: ${ai.primaryCategory || "General User"} (Confidence: ${ai.confidence || 80}%)`, 14, y);
      y += 12;
    }

    // Watermark
    doc.setTextColor(200, 200, 200);
    doc.setFontSize(40);
    doc.setFont("helvetica", "bold");
    doc.text(conf.watermark, 105, 150, { align: "center", angle: 45 });

    doc.save(`OSINT_Report_${(data.query || "investigation").replace(/[^a-zA-Z0-9]/g, "_")}.pdf`);
  }
};
