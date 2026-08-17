"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const frontendRoot = path.resolve(__dirname, "..");
const appPath = path.join(frontendRoot, "js", "app.js");
const exporterPath = path.join(frontendRoot, "js", "lea_pdf_exporter.js");
const appSource = fs.readFileSync(appPath, "utf8");
const exporterSource = fs.readFileSync(exporterPath, "utf8");

const API_BASE = "http://127.0.0.1:8010";
const VALID_LINKS = {
    public: "https://public.example.org/evidence?id=42",
    linkedin: "https://www.linkedin.com/in/valid-profile",
    instagram: "https://www.instagram.com/valid.profile/",
    tiktok: "https://www.tiktok.com/@valid.profile",
    facebook: "https://www.facebook.com/valid.profile",
    github: "https://github.com/valid-profile",
    x: "https://x.com/valid_profile",
};
const VALID_IMAGES = {
    linkedin: "https://media.licdn.com/dms/image/valid-linkedin.jpg",
    instagram: "https://scontent.cdninstagram.com/v/valid-instagram.jpg",
    tiktok: "https://p16.tiktokcdn.com/valid-tiktok.jpg",
    twitter: "https://pbs.twimg.com/profile_images/valid-twitter.jpg",
    facebook: "https://scontent.fbcdn.net/v/valid-facebook.jpg",
};
const BAD_URLS = [
    "javascript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "file:///etc/passwd",
    "vbscript:msgbox(1)",
    "https://user:password@public.example.org/private",
    "http://localhost/admin",
    "http://api.local/admin",
    "http://service.internal/admin",
    "http://router.home.arpa/admin",
    "http://127.0.0.1/admin",
    "http://2130706433/admin",
    "http://0x7f000001/admin",
    "http://10.0.0.1/admin",
    "http://100.64.0.1/admin",
    "http://169.254.169.254/latest/meta-data",
    "http://172.16.0.1/admin",
    "http://192.168.1.1/admin",
    "http://0.0.0.0/admin",
    "http://224.0.0.1/admin",
    "http://198.51.100.7/admin",
    "http://203.0.113.7/admin",
    "http://[::1]/admin",
    "http://[fc00::1]/admin",
    "http://[fe80::1]/admin",
];
const ATTRIBUTE_BREAKER = "x\" data-owned=\"ATTRIBUTE-INJECTION-SENTINEL";
const MARKUP_PAYLOAD = '<img src="x" data-owned="MARKUP-INJECTION-SENTINEL">';
const NUMERIC_PAYLOAD = '<img src="x" data-owned="NUMERIC-INJECTION-SENTINEL">';
const SECRET_SENTINELS = [
    "DATABASE-SECRET-SENTINEL",
    "INFO-SECRET-SENTINEL",
    "PASSWORD-SECRET-SENTINEL",
    "PASS-SECRET-SENTINEL",
    "AUTH-SECRET-SENTINEL",
    "CVC-SECRET-SENTINEL",
    "PAN-SECRET-SENTINEL",
    "SESSION-SECRET-SENTINEL",
    "MEDICAL-SECRET-SENTINEL",
    "IP-SECRET-SENTINEL",
    "NOTE-SECRET-SENTINEL",
    "NESTED-SECRET-SENTINEL",
];

function decodeAttribute(value) {
    return String(value)
        .replace(/&amp;/g, "&")
        .replace(/&quot;/g, "\"")
        .replace(/&#39;/g, "'")
        .replace(/&lt;/g, "<")
        .replace(/&gt;/g, ">");
}

function anchors(html) {
    return [...String(html).matchAll(/<a\b[^>]*>/gi)].map(match => match[0]);
}

function imageSources(html) {
    return [...String(html).matchAll(/<img\b[^>]*\bsrc="([^"]*)"[^>]*>/gi)]
        .map(match => ({ tag: match[0], src: decodeAttribute(match[1]) }));
}

function assertLinksAreSafe(html, hostnameIsClearlyNonPublic, label) {
    for (const anchor of anchors(html)) {
        const hrefMatch = anchor.match(/\bhref="([^"]*)"/i);
        if (!hrefMatch) continue;
        const href = decodeAttribute(hrefMatch[1]);
        if (href === "#") continue;
        assert.doesNotMatch(
            href,
            /^(?:javascript|data|file|vbscript):/i,
            `${label}: active URL scheme survived: ${href}`,
        );
        const parsed = new URL(href);
        assert(["http:", "https:"].includes(parsed.protocol), `${label}: non-HTTP link survived`);
        assert.equal(parsed.username, "", `${label}: URL username survived`);
        assert.equal(parsed.password, "", `${label}: URL password survived`);
        assert.equal(
            hostnameIsClearlyNonPublic(parsed.hostname),
            false,
            `${label}: non-public target became clickable: ${href}`,
        );
    }

    for (const anchor of anchors(html).filter(value => /\btarget="_blank"/i.test(value))) {
        assert.match(
            anchor,
            /\brel="noopener noreferrer"/i,
            `${label}: target=_blank anchor is missing opener protection`,
        );
    }
}

function assertImagesUseAuthenticatedProxy(html, safeURL, label, minimum = 0) {
    const images = imageSources(html);
    assert(
        images.length >= minimum,
        `${label}: expected at least ${minimum} proxied image(s), received ${images.length}`,
    );
    for (const { tag, src } of images) {
        assert.doesNotMatch(tag, /\bdata-owned=/i, `${label}: injected image attribute survived`);
        const parsed = new URL(src);
        assert.equal(parsed.origin, API_BASE, `${label}: image bypassed the local proxy`);
        assert.equal(
            parsed.pathname,
            "/api/v1/investigation/proxy_image",
            `${label}: unexpected image endpoint`,
        );
        const upstream = parsed.searchParams.get("url");
        assert(upstream, `${label}: proxy URL omitted its upstream target`);
        assert.equal(safeURL(upstream), upstream, `${label}: unsafe upstream reached the proxy`);
        assert.match(tag, /\bcrossorigin="use-credentials"/i, `${label}: auth cookie mode missing`);
        assert.match(tag, /\breferrerpolicy="no-referrer"/i, `${label}: referrer protection missing`);
    }
    return images;
}

function assertSecretsSuppressed(html, label) {
    for (const sentinel of SECRET_SENTINELS) {
        assert(!String(html).includes(sentinel), `${label}: leaked ${sentinel}`);
    }
    assert.match(String(html), /\[(?:VALUE )?(?:SUPPRESSED|REDACTED)\]/i, `${label}: suppression marker missing`);
}

function makeCtiFixture() {
    return {
        total_records: 4,
        databases: ["fixture"],
        results: [{
            database: "password: DATABASE-SECRET-SENTINEL",
            info_leak: "api_key=INFO-SECRET-SENTINEL",
            data: [{
                Password: "PASSWORD-SECRET-SENTINEL",
                Pass: "PASS-SECRET-SENTINEL",
                Authorization: "AUTH-SECRET-SENTINEL",
                CVC: "CVC-SECRET-SENTINEL",
                PAN: "PAN-SECRET-SENTINEL",
                session_id: "SESSION-SECRET-SENTINEL",
                medical_record: "MEDICAL-SECRET-SENTINEL",
                IP: "IP-SECRET-SENTINEL",
                note: "token: NOTE-SECRET-SENTINEL",
                profile: { token: "NESTED-SECRET-SENTINEL" },
            }, {
                Url: "javascript:alert('cti')",
            }, {
                Url: "http://127.0.0.1/admin",
            }, {
                Url: VALID_LINKS.public,
            }],
        }],
    };
}

function loadApp() {
    const nodes = new Map();
    const nodeFor = id => {
        if (!nodes.has(id)) {
            nodes.set(id, {
                id,
                innerHTML: "",
                textContent: "",
                value: "",
                checked: false,
                disabled: false,
                scrollHeight: 0,
                scrollTop: 0,
                style: {},
                className: "",
                classList: { add() {}, remove() {}, toggle() {} },
                appendChild() {},
                remove() {},
                addEventListener() {},
                querySelectorAll() { return []; },
            });
        }
        return nodes.get(id);
    };

    const sandbox = {
        API_BASE,
        URL,
        console,
        location: { protocol: "http:", hostname: "127.0.0.1" },
        sessionStorage: { getItem() { return null; }, setItem() {}, removeItem() {} },
        document: {
            getElementById: nodeFor,
            querySelectorAll() { return []; },
            createElement() { return nodeFor(`created-${nodes.size}`); },
        },
        SocAuth: { fetch() { throw new Error("network calls are forbidden in this test"); } },
        addEventListener() {},
        scrollTo() {},
        alert() {},
        setInterval() { return 1; },
        clearInterval() {},
        setTimeout() { return 1; },
    };
    sandbox.window = sandbox;
    vm.createContext(sandbox);
    vm.runInContext(appSource, sandbox, { filename: appPath });
    return { sandbox, nodeFor };
}

function assertBadURLsRejected(safeURL, label) {
    for (const value of BAD_URLS) {
        assert.equal(safeURL(value), "", `${label}: accepted unsafe URL ${value}`);
    }
    assert.equal(safeURL(VALID_LINKS.public), VALID_LINKS.public, `${label}: rejected valid HTTPS URL`);
    assert.equal(safeURL("https://8.8.8.8/dns-query"), "https://8.8.8.8/dns-query", `${label}: rejected public IPv4 URL`);
}

async function runAppTests() {
    const { sandbox, nodeFor } = loadApp();
    const safeURL = value => sandbox.safeAbsoluteHttpURL(value);
    assertBadURLsRejected(safeURL, "app.safeAbsoluteHttpURL");
    assert.equal(sandbox.proxiedImageURL(BAD_URLS[0]), "", "app image helper accepted active scheme");
    assert.equal(sandbox.proxiedImageURL("http://10.0.0.1/private.png"), "", "app image helper accepted private host");
    assert.match(sandbox.proxiedImageURL(VALID_IMAGES.twitter), /\/api\/v1\/investigation\/proxy_image\?url=/);

    sandbox.renderConsolidatedIdentity({
        confidence_percentage: 50,
        overall_confidence: "moderate",
        likely_name: "Fixture",
        emails: [{ email: "fixture@example.org", status: MARKUP_PAYLOAD }],
        links: [...BAD_URLS, VALID_LINKS.public],
        profile_pic: ATTRIBUTE_BREAKER,
    });
    let html = nodeFor("consolidated-identity-body").innerHTML;
    assertLinksAreSafe(html, sandbox.hostnameIsClearlyNonPublic, "app consolidated identity");
    assert(html.includes(`href="${VALID_LINKS.public.replace(/&/g, "&amp;")}"`));
    assert.equal(imageSources(html).length, 0, "invalid consolidated image was rendered");
    assert(!html.includes(MARKUP_PAYLOAD), "email status markup reached consolidated HTML");
    assert.match(html, /<small>\(unknown\)<\/small>/, "unknown email status was not normalized");

    sandbox.renderConsolidatedIdentity({
        confidence_percentage: 50,
        overall_confidence: "moderate",
        likely_name: "Fixture",
        emails: [],
        links: [VALID_LINKS.public],
        profile_pic: VALID_IMAGES.twitter,
    });
    html = nodeFor("consolidated-identity-body").innerHTML;
    assertImagesUseAuthenticatedProxy(html, safeURL, "app consolidated image", 1);

    sandbox.renderGoogleDorking({
        results: [...BAD_URLS, VALID_LINKS.public].map((url, index) => ({
            url,
            title: `Result ${index}`,
            domain: "public.example.org",
            snippet: "Public snippet",
            query: "fixture",
        })),
    });
    html = nodeFor("dorking-results-body").innerHTML;
    assertLinksAreSafe(html, sandbox.hostnameIsClearlyNonPublic, "app dork results");
    assert(html.includes(`href="${VALID_LINKS.public.replace(/&/g, "&amp;")}"`));

    sandbox.renderAssociatedAccounts([...BAD_URLS, VALID_LINKS.github].map((url, index) => ({
        platform: "fixture",
        category: "public",
        username: `fixture-${index}`,
        url,
        confidence: index === 0 ? NUMERIC_PAYLOAD : 50,
        match_status: "candidate",
        reasons: [],
    })));
    html = nodeFor("associated-accounts-body").innerHTML;
    assertLinksAreSafe(html, sandbox.hostnameIsClearlyNonPublic, "app associated accounts");
    assert(html.includes(`href="${VALID_LINKS.github}"`));
    assert(!html.includes("NUMERIC-INJECTION-SENTINEL"), "associated-account confidence reached HTML");

    sandbox.renderTelegramCTI(makeCtiFixture());
    html = nodeFor("telegram-cti-body").innerHTML;
    assertSecretsSuppressed(html, "app Telegram CTI");
    assertLinksAreSafe(html, sandbox.hostnameIsClearlyNonPublic, "app Telegram CTI");
    assert(html.includes(`href="${VALID_LINKS.public.replace(/&/g, "&amp;")}"`));
    assert(!html.includes('href="javascript:'), "CTI javascript value became clickable");
    assert(!html.includes('href="http://127.0.0.1'), "CTI loopback value became clickable");

    sandbox.renderPlatformDossiers({
        instagram: {
            success: true,
            username: "fixture",
            follower_count: NUMERIC_PAYLOAD,
            following_count: NUMERIC_PAYLOAD,
            post_count: NUMERIC_PAYLOAD,
            external_url: "javascript:alert('instagram')",
        },
        tiktok: {
            success: true,
            username: "fixture",
            follower_count: NUMERIC_PAYLOAD,
            heart_count: NUMERIC_PAYLOAD,
            video_count: NUMERIC_PAYLOAD,
            url: "http://127.0.0.1/tiktok",
        },
        linkedin: {
            success: true,
            basic_info: {
                full_name: "Fixture",
                profile_url: "data:text/html,linkedin",
                profile_picture_url: ATTRIBUTE_BREAKER,
                follower_count: NUMERIC_PAYLOAD,
            },
            featured: [{
                url: "javascript:alert('featured')",
                image_url: VALID_IMAGES.linkedin,
                title: "Unsafe link",
            }, {
                url: VALID_LINKS.public,
                image_url: ATTRIBUTE_BREAKER,
                title: "Unsafe image",
            }],
        },
        twitter: {
            success: true,
            username: "fixture",
            follower_count: NUMERIC_PAYLOAD,
            following_count: NUMERIC_PAYLOAD,
            post_count: NUMERIC_PAYLOAD,
            profile_pic_url: "http://10.0.0.1/twitter.jpg",
            tweets: [{ text: "fixture", like_count: NUMERIC_PAYLOAD, retweet_count: NUMERIC_PAYLOAD }],
        },
    });
    html = nodeFor("platform-dossiers-body").innerHTML;
    assertLinksAreSafe(html, sandbox.hostnameIsClearlyNonPublic, "app malicious platform dossiers");
    assert(!html.includes("ATTRIBUTE-INJECTION-SENTINEL"));
    assert(!html.includes("NUMERIC-INJECTION-SENTINEL"), "provider metric markup reached dossier HTML");
    assert.equal(imageSources(html).length, 0, "unsafe dossier image was rendered");

    sandbox.SocAuth.fetch = async () => ({
        ok: true,
        async json() {
            return {
                [MARKUP_PAYLOAD]: { configured: false, status: MARKUP_PAYLOAD },
                malformed: null,
            };
        },
    });
    await sandbox.fetchApiKeysStatus();
    html = nodeFor("hero-api-keys-list").innerHTML;
    assert(!html.includes(MARKUP_PAYLOAD), "diagnostics markup reached HTML");
    assert(html.includes("&lt;IMG SRC=&quot;X&quot;"), "diagnostics key was not escaped");
    assert.match(html, />MISSING<\/span>/, "unknown diagnostics status was not normalized");

    sandbox.renderPlatformDossiers({
        instagram: {
            success: true,
            username: "fixture",
            follower_count: 1,
            following_count: 1,
            post_count: 1,
            external_url: VALID_LINKS.instagram,
        },
        tiktok: {
            success: true,
            username: "fixture",
            follower_count: 1,
            heart_count: 1,
            video_count: 1,
            url: VALID_LINKS.tiktok,
        },
        linkedin: {
            success: true,
            basic_info: {
                full_name: "Fixture",
                profile_url: VALID_LINKS.linkedin,
                profile_picture_url: VALID_IMAGES.linkedin,
                follower_count: 1,
            },
            featured: [{
                url: VALID_LINKS.public,
                image_url: VALID_IMAGES.instagram,
                title: "Valid featured link",
            }],
        },
        twitter: {
            success: true,
            username: "fixture",
            follower_count: 1,
            following_count: 1,
            post_count: 1,
            profile_pic_url: VALID_IMAGES.twitter,
            tweets: [],
        },
    });
    html = nodeFor("platform-dossiers-body").innerHTML;
    assertLinksAreSafe(html, sandbox.hostnameIsClearlyNonPublic, "app valid platform dossiers");
    for (const url of [VALID_LINKS.instagram, VALID_LINKS.tiktok, VALID_LINKS.linkedin]) {
        assert(html.includes(`href="${url}"`), `valid platform link disappeared: ${url}`);
    }
    assert(
        html.includes(`href="${VALID_LINKS.public.replace(/&/g, "&amp;")}"`),
        "valid LinkedIn featured link disappeared",
    );
    assertImagesUseAuthenticatedProxy(html, safeURL, "app valid platform images", 3);

    sandbox.renderMediaGallery({
        scraped_data: {
            instagram: {
                profile_pic_url: "javascript:alert('image')",
                url: "javascript:alert('link')",
                posts: [{ display_url: ATTRIBUTE_BREAKER, url: "http://127.0.0.1/post" }],
            },
            linkedin: { profile_pic_url: "http://10.0.0.1/linkedin.jpg", profile_url: BAD_URLS[1] },
            tiktok: { profile_pic_url: BAD_URLS[1], url: BAD_URLS[1] },
            twitter: { profile_pic_url: "http://[::1]/twitter.jpg", url: "http://[::1]/profile" },
            facebook: {
                profile_pic_url: BAD_URLS[4],
                cover_image_url: "http://169.254.169.254/cover.jpg",
                url: "http://192.168.1.1/facebook",
                posts: [{ media: [{ thumbnail: ATTRIBUTE_BREAKER, url: BAD_URLS[0] }] }],
            },
        },
    });
    html = nodeFor("media-gallery-body").innerHTML;
    assertLinksAreSafe(html, sandbox.hostnameIsClearlyNonPublic, "app malicious media gallery");
    assert.equal(imageSources(html).length, 0, "unsafe media-gallery image was rendered");
    assert(!html.includes("ATTRIBUTE-INJECTION-SENTINEL"));

    sandbox.renderMediaGallery({
        scraped_data: {
            instagram: {
                profile_pic_url: VALID_IMAGES.instagram,
                url: VALID_LINKS.instagram,
                posts: [{ display_url: VALID_IMAGES.instagram, url: VALID_LINKS.instagram }],
            },
            linkedin: { profile_pic_url: VALID_IMAGES.linkedin, profile_url: VALID_LINKS.linkedin },
            tiktok: { profile_pic_url: VALID_IMAGES.tiktok, url: VALID_LINKS.tiktok },
            twitter: { profile_pic_url: VALID_IMAGES.twitter, url: VALID_LINKS.x },
            facebook: {
                profile_pic_url: VALID_IMAGES.facebook,
                cover_image_url: VALID_IMAGES.facebook,
                url: VALID_LINKS.facebook,
                posts: [{ media: [{ thumbnail: VALID_IMAGES.facebook, url: VALID_LINKS.facebook }] }],
            },
        },
    });
    html = nodeFor("media-gallery-body").innerHTML;
    assertLinksAreSafe(html, sandbox.hostnameIsClearlyNonPublic, "app valid media gallery");
    assertImagesUseAuthenticatedProxy(html, safeURL, "app valid media gallery", 8);
}

function loadExporter() {
    const sandbox = { API_BASE, URL, window: {}, console };
    vm.createContext(sandbox);
    vm.runInContext(exporterSource, sandbox, { filename: exporterPath });
    return sandbox.window.LeaPdfExporter;
}

function maliciousExporterData() {
    return {
        investigation_id: "UPP-SECURITY-TEST",
        target_query: "fixture",
        consolidated_identity: { confidence_percentage: NUMERIC_PAYLOAD },
        telegram_cti: makeCtiFixture(),
        associated_accounts: BAD_URLS.map((url, index) => ({
            platform: "fixture",
            username: `fixture-${index}`,
            url,
            confidence: NUMERIC_PAYLOAD,
        })),
        wmn_results: {
            hits: BAD_URLS.map(url => ({ site: "fixture", handle: "fixture", ms: NUMERIC_PAYLOAD, url })),
        },
        dorking_results: {
            results: BAD_URLS.map((url, index) => ({
                category: "fixture",
                url,
                title: `Result ${index}`,
                domain: "fixture",
            })),
        },
        scraped_data: {
            linkedin: { success: true, profile_url: BAD_URLS[0], profile_pic_url: ATTRIBUTE_BREAKER },
            instagram: {
                success: true,
                external_url: BAD_URLS[1],
                profile_pic_url: "http://127.0.0.1/instagram.jpg",
                posts: [{ display_url: ATTRIBUTE_BREAKER }],
            },
            tiktok: { success: true, profile_pic_url: "http://10.0.0.1/tiktok.jpg" },
            twitter: { success: true, profile_pic_url: "http://[::1]/twitter.jpg" },
            facebook: {
                success: true,
                url: BAD_URLS[4],
                profile_pic_url: "http://192.168.1.1/facebook.jpg",
                cover_image_url: "http://169.254.169.254/cover.jpg",
                posts: [{ media: [{ thumbnail: ATTRIBUTE_BREAKER }] }],
            },
        },
    };
}

function validExporterData() {
    return {
        investigation_id: "UPP-VALID-TEST",
        target_query: "fixture",
        associated_accounts: [{
            platform: "GitHub",
            username: "valid-profile",
            url: VALID_LINKS.github,
            confidence: 80,
        }],
        wmn_results: { hits: [{ site: "X", handle: "valid_profile", ms: 1, url: VALID_LINKS.x }] },
        dorking_results: {
            results: [{
                category: "public",
                url: VALID_LINKS.public,
                title: "Valid public result",
                domain: "public.example.org",
            }],
        },
        scraped_data: {
            linkedin: {
                success: true,
                profile_url: VALID_LINKS.linkedin,
                profile_pic_url: VALID_IMAGES.linkedin,
            },
            instagram: {
                success: true,
                external_url: VALID_LINKS.instagram,
                profile_pic_url: VALID_IMAGES.instagram,
                posts: [{ display_url: VALID_IMAGES.instagram }],
            },
            tiktok: { success: true, profile_pic_url: VALID_IMAGES.tiktok },
            twitter: { success: true, profile_pic_url: VALID_IMAGES.twitter },
            facebook: {
                success: true,
                url: VALID_LINKS.facebook,
                profile_pic_url: VALID_IMAGES.facebook,
                cover_image_url: VALID_IMAGES.facebook,
                posts: [{ media: [{ thumbnail: VALID_IMAGES.facebook }] }],
            },
        },
    };
}

function runExporterTests() {
    const exporter = loadExporter();
    const safeURL = value => exporter.safeAbsoluteHttpURL(value);
    assertBadURLsRejected(safeURL, "exporter.safeAbsoluteHttpURL");

    let html = exporter.generateReportHtml(maliciousExporterData());
    assertSecretsSuppressed(html, "PDF Telegram CTI");
    assertLinksAreSafe(html, exporter.hostnameIsClearlyNonPublic.bind(exporter), "malicious PDF report");
    assert.equal(imageSources(html).length, 0, "unsafe PDF image was rendered");
    assert(!html.includes("ATTRIBUTE-INJECTION-SENTINEL"));
    assert(!html.includes("NUMERIC-INJECTION-SENTINEL"), "numeric markup reached PDF report HTML");

    html = exporter.generateReportHtml(validExporterData());
    assertLinksAreSafe(html, exporter.hostnameIsClearlyNonPublic.bind(exporter), "valid PDF report");
    for (const url of [
        VALID_LINKS.linkedin,
        VALID_LINKS.instagram,
        VALID_LINKS.facebook,
        VALID_LINKS.github,
        VALID_LINKS.x,
        VALID_LINKS.public,
    ]) {
        assert(html.includes(`href="${url.replace(/&/g, "&amp;")}"`), `valid PDF link disappeared: ${url}`);
    }
    assertImagesUseAuthenticatedProxy(html, safeURL, "valid PDF media", 8);
}

async function main() {
    await runAppTests();
    runExporterTests();
    console.log("legacy_render_security.test.cjs: all assertions passed");
}

main().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
