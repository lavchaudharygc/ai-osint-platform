/**
 * UI unit assertions for Phone Investigation frontend module.
 */
const fs = require("fs");
const path = require("path");
const assert = require("assert");

const htmlPath = path.join(__dirname, "..", "index.html");
const jsPath = path.join(__dirname, "..", "js", "phone_investigation.js");

const htmlContent = fs.readFileSync(htmlPath, "utf-8");
const jsContent = fs.readFileSync(jsPath, "utf-8");

// Assert elements in index.html
assert(htmlContent.includes('id="nav-phone-investigation"'), "nav-phone-investigation button missing in index.html");
assert(htmlContent.includes('id="phone-investigation-view"'), "phone-investigation-view section missing in index.html");
assert(htmlContent.includes('id="phone-target-input"'), "phone-target-input input missing in index.html");
assert(htmlContent.includes('id="phone-country-code"'), "phone-country-code select missing in index.html");
assert(htmlContent.includes('id="phone-case-id"'), "phone-case-id input missing in index.html");
assert(htmlContent.includes('id="phone-reason-code"'), "phone-reason-code select missing in index.html");
assert(htmlContent.includes('id="phone-authorization-confirmed"'), "phone-authorization-confirmed checkbox missing in index.html");
assert(htmlContent.includes('src="js/phone_investigation.js"'), "phone_investigation.js script tag missing in index.html");

// Assert functions in phone_investigation.js
assert(jsContent.includes("openPhoneInvestigation"), "openPhoneInvestigation function missing in phone_investigation.js");
assert(jsContent.includes("exportPhoneInvestigation"), "exportPhoneInvestigation function missing in phone_investigation.js");
assert(jsContent.includes("submitPhoneInvestigation"), "submitPhoneInvestigation function missing in phone_investigation.js");

console.log("phone_investigation_ui.test.cjs: all assertions passed");
