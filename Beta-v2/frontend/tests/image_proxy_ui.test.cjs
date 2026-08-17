"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const frontendRoot = path.resolve(__dirname, "..");
const appSource = fs.readFileSync(path.join(frontendRoot, "js", "app.js"), "utf8");
const exporterSource = fs.readFileSync(
  path.join(frontendRoot, "js", "lea_pdf_exporter.js"),
  "utf8",
);

assert(!appSource.includes('<img src="${item.url}"'));
assert(appSource.includes('src="${escapeHTML(proxyUrl)}"'));
assert(appSource.includes('crossorigin="use-credentials"'));
assert(!exporterSource.includes("encodeURIComponent('${esc(item.url)}')"));

const context = {
  URL,
  window: {},
  console,
};
vm.createContext(context);
vm.runInContext(exporterSource, context, { filename: "lea_pdf_exporter.js" });

const maliciousUrl = "https://pbs.twimg.com/photo.png' onerror='alert(1)";
const html = context.window.LeaPdfExporter.generateReportHtml({
  investigation_id: "UPP-TEST",
  target_query: "safe-target",
  scraped_data: {
    twitter: {
      success: true,
      profile_pic_url: maliciousUrl,
    },
  },
});

assert(!html.includes(maliciousUrl));
assert(!html.includes("onerror='alert(1)"));
assert(html.includes("/api/v1/investigation/proxy_image?url="));
assert(html.includes('crossorigin="use-credentials"'));
assert(!/<img[^>]+src=["']https:\/\/pbs\.twimg\.com/i.test(html));

console.log("image_proxy_ui.test.cjs: all assertions passed");
