"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const frontendRoot = path.resolve(__dirname, "..");
const appPath = path.join(frontendRoot, "js", "app.js");
const exporterPath = path.join(frontendRoot, "js", "lea_pdf_exporter.js");
const indexPath = path.join(frontendRoot, "index.html");
const demoPath = path.join(frontendRoot, "demo_data.json");
const appSource = fs.readFileSync(appPath, "utf8");
const exporterSource = fs.readFileSync(exporterPath, "utf8");
const indexSource = fs.readFileSync(indexPath, "utf8");
const demoData = JSON.parse(fs.readFileSync(demoPath, "utf8"));

const API_BASE = "http://127.0.0.1:8010";
const VALID_LINKS = {
    public: "https://public.example.org/evidence?id=42",
    linkedin: "https://www.linkedin.com/in/valid-profile",
    linkedinPost: "https://www.linkedin.com/posts/valid-profile_activity-123456789",
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
    assert.match(indexSource, /id="hashtag-analysis-badge"/);
    assert.match(indexSource, /id="hashtag-analysis-body"/);
    assertBadURLsRejected(safeURL, "app.safeAbsoluteHttpURL");
    assert.equal(sandbox.classifyInput("alice@example.org").kind, "email");
    assert.equal(sandbox.classifyInput("+91 98765 43210").kind, "phone");
    assert.equal(sandbox.classifyInput("john.doe").kind, "domain");
    assert.equal(sandbox.classifyInput("@john.doe").kind, "username");
    assert.equal(sandbox.classifyInput("John Doe").kind, "name");
    assert.equal(sandbox.classifyInput("example.com").kind, "domain");
    assert.equal(sandbox.classifyInput("sub.example.co.in").kind, "domain");
    assert.equal(sandbox.classifyInput("https://sub.example.tech/path").kind, "domain");
    assert.equal(sandbox.classifyInput("example.tech").kind, "domain");
    assert.equal(sandbox.classifyInput("example.online").kind, "domain");
    assert.equal(sandbox.classifyInput("example.xn--p1ai").kind, "domain");
    assert.equal(sandbox.classifyInput("192.168.1.1").kind, "domain");
    assert.equal(sandbox.classifyInput("2001:db8::1").kind, "domain");
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
    assert.match(html, /<small>\(unknown · discovered · source unavailable\)<\/small>/, "unknown email status was not normalized");

    sandbox.renderConsolidatedIdentity({
        confidence_percentage: 75,
        overall_confidence: "high",
        likely_name: "Contact Fixture",
        emails: [
            {
                email: "Observed@Example.org",
                status: "observed",
                sources: [{ source: "linkedin", provider: "apify", field: "email", collection_method: "public_profile" }],
            },
            {
                address: "observed@example.org",
                status: "verified",
                verification_provider: "hunter",
                sources: [{ provider: "RocketReach", field: "emails", collection_method: "enrichment_provider" }],
            },
            { email: MARKUP_PAYLOAD, status: "verified" },
        ],
        email_guesses: [{
            email: "candidate@example.org",
            status: "likely",
            reason: "Generated pattern candidate; not provider-observed",
            sources: [{ source: "pattern generator", field: "candidate", collection_method: "generated_pattern" }],
        }],
        phones: [
            {
                phone: "+91 98765 43210",
                normalized: "+919876543210",
                status: "valid",
                sources: [{ provider: "SignalHire", field: "phones", collection_method: "enrichment_provider" }],
            },
            {
                e164: "+919876543210",
                status: "possible",
                sources: [{ source: "linkedin", field: "phone", collection_method: "public_profile" }],
            },
        ],
        links: [],
    });
    html = nodeFor("consolidated-identity-body").innerHTML;
    assert(html.includes("DISCOVERED / PROVIDED EMAILS (1)"), "observed email count was not de-duplicated");
    assert.equal((html.match(/observed@example\.org/g) || []).length, 1, "duplicate email was rendered more than once");
    assert(html.includes("GENERATED EMAIL CANDIDATES — NOT CONFIRMED (1)"), "email guesses were not kept separate");
    assert(html.includes("candidate@example.org"), "generated email candidate was omitted");
    assert(html.includes("DISCOVERED / PROVIDED PHONE NUMBERS (1)"), "canonical phone count was not rendered");
    assert.equal((html.match(/98765 43210/g) || []).length, 1, "duplicate phone was rendered more than once");
    assert(html.includes("RocketReach"), "email provenance was omitted");
    assert(html.includes("SignalHire"), "phone provenance was omitted");
    assert(html.includes("linkedin"), "platform provenance was hidden by the generic provider label");
    assert(html.includes("verification: hunter"), "email verification provider was omitted");
    assert(!html.includes("[object Object]"), "contact object leaked through string rendering");
    assert(!html.includes(MARKUP_PAYLOAD), "malformed contact value reached consolidated HTML");

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

    const hashtagFixture = {
        status: "completed",
        total_unique_hashtags: 5,
        total_mentions: 10,
        platforms_with_hashtags: 5,
        top_hashtags: [
            {
                tag: "CyberSafe",
                mentions: 5,
                platforms: ["instagram", "linkedin", "tiktok", "twitter", "facebook"],
                cross_platform: true,
            },
            {
                tag: MARKUP_PAYLOAD,
                mentions: NUMERIC_PAYLOAD,
                platforms: ["twitter"],
                cross_platform: false,
            },
            { tag: "###", mentions: 1, platforms: [] },
        ],
        cross_platform_hashtags: [{
            tag: "CyberSafe",
            mentions: 5,
            platforms: ["instagram", "linkedin", "tiktok", "twitter", "facebook"],
            cross_platform: true,
        }],
        platforms: {
            instagram: { total_mentions: 3, hashtags: ["CyberSafe", MARKUP_PAYLOAD] },
            linkedin: { total_mentions: 1, hashtags: ["CyberSafe"] },
            tiktok: { total_mentions: 2, hashtags: ["CyberSafe"] },
            twitter: { total_mentions: 2, hashtags: ["CyberSafe", "DFIR"] },
            facebook: { total_mentions: 2, hashtags: ["CyberSafe", "UPPolice"] },
        },
    };
    sandbox.renderHashtagAnalysis(hashtagFixture);
    html = nodeFor("hashtag-analysis-body").innerHTML;
    assert(html.includes("#CyberSafe"), "top hashtag was not rendered");
    assert(html.includes("CROSS-PLATFORM HASHTAGS (1)"), "cross-platform summary was omitted");
    for (const platform of ["Instagram", "LinkedIn", "TikTok", "X", "Facebook"]) {
        assert(html.includes(`>${platform}<`), `hashtag platform row missing: ${platform}`);
    }
    assert(!html.includes(MARKUP_PAYLOAD), "hashtag markup reached rendered HTML");
    assert(!html.includes(NUMERIC_PAYLOAD), "hashtag count markup reached rendered HTML");
    assert(!html.includes("&lt;img"), "malformed hashtag text was not rejected");
    assert(!html.includes(">#</div>"), "empty hashtag chip was rendered");
    assert.equal(nodeFor("hashtag-analysis-badge").textContent, "5 UNIQUE · 10 MENTIONS");

    sandbox.renderResults({
        hashtag_analysis: hashtagFixture,
        consolidated_identity: {
            confidence_percentage: 50,
            overall_confidence: "moderate",
            likely_name: "Wiring Fixture",
            emails: [],
            phones: [],
            links: [],
        },
        contact_discovery: {
            emails: [{ email: "wired@example.org", status: "observed" }],
            phones: [{ phone: "+91 99887 76655", normalized: "+919988776655", status: "possible" }],
        },
        scraped_data: {},
        associated_accounts: [],
        dorking_results: { results: [] },
        telegram_cti: { results: [], databases: [] },
    });
    assert(
        nodeFor("hashtag-analysis-body").innerHTML.includes("#CyberSafe"),
        "renderResults did not invoke hashtag analysis rendering",
    );
    assert(
        nodeFor("consolidated-identity-body").innerHTML.includes("wired@example.org")
        && nodeFor("consolidated-identity-body").innerHTML.includes("+91 99887 76655"),
        "renderResults did not pass canonical contact discovery to the identity renderer",
    );

    sandbox.renderHashtagAnalysis({ status: "no_data", top_hashtags: [] });
    html = nodeFor("hashtag-analysis-body").innerHTML;
    assert(html.includes("No public hashtags were found"), "hashtag empty state was omitted");

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

    sandbox.renderGoogleDorking({
        status: "partial",
        provider: "serpapi",
        queries_planned: 5,
        queries_attempted: 2,
        queries_run: 1,
        results_count: 2,
        duplicates_removed: 4,
        results_truncated: 3,
        error: MARKUP_PAYLOAD,
        results: [
            null,
            {
                link: VALID_LINKS.github,
                title: MARKUP_PAYLOAD,
                domain: "github.com",
                description: MARKUP_PAYLOAD,
                query: `"fixture" (${MARKUP_PAYLOAD})`,
                query_category: "Professional and code profiles",
                matched_queries: ["Exact mentions", "Professional and code profiles"],
            },
        ],
    });
    html = nodeFor("dorking-results-body").innerHTML;
    assertLinksAreSafe(html, sandbox.hostnameIsClearlyNonPublic, "app partial dork results");
    assert(html.includes(`href="${VALID_LINKS.github}"`), "dork link alias was not rendered");
    assert(html.includes("PARTIAL"), "partial dorking status was hidden");
    assert(html.includes("4 DUPLICATES REMOVED"), "dork deduplication metric was hidden");
    assert(html.includes("3 RESULTS CAPPED"), "dork result cap metric was hidden");
    assert(html.includes("white-space:normal"), "long Google queries are still forced onto one line");
    assert(!html.includes(MARKUP_PAYLOAD), "dork result markup reached the dashboard");
    assert.equal(nodeFor("dorking-count-badge").textContent, "1 HITS · 1/2 QUERIES");

    sandbox.renderGoogleDorking({
        status: "not_configured",
        provider: "serpapi",
        queries_planned: 5,
        queries_attempted: 0,
        queries_run: 0,
        results: { malformed: true },
    });
    html = nodeFor("dorking-results-body").innerHTML;
    assert(html.includes("SERPAPI_KEY is not configured"), "missing dorking key looked like zero hits");
    assert(html.includes("No displayable organic search hits"));
    assert.equal(nodeFor("dorking-count-badge").textContent, "0 HITS · 0/5 QUERIES");

    sandbox.renderGoogleDorking({
        status: "quota_exhausted",
        error: MARKUP_PAYLOAD,
        calls_made: 1,
        results: [],
    });
    html = nodeFor("dorking-results-body").innerHTML;
    assert(html.includes("search quota is exhausted"), "quota exhaustion was hidden");
    assert(!html.includes(MARKUP_PAYLOAD), "raw dorking provider error reached the dashboard");

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

    sandbox.renderTelegramCTI({
        status: "error",
        error: `CTI provider quota exhausted ${MARKUP_PAYLOAD}`,
        total_records: 0,
        databases: [],
        results: [],
        usage: {
            logical_searches_performed: 2,
            logical_search_limit: 5,
            http_attempts: 2,
            http_attempt_limit: 6,
        },
    });
    html = nodeFor("telegram-cti-body").innerHTML;
    assert(html.includes("CTI provider quota exhausted"), "CTI error was rendered as no-results");
    assert(html.includes("provider calls"), "CTI usage counters were not rendered");
    assert(!html.includes("No breach records were found"), "failed CTI lookup was shown as successful");
    assert(!html.includes(MARKUP_PAYLOAD), "CTI error markup reached HTML");
    assert.match(nodeFor("cti-records-badge").textContent, /ERROR/);

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
            emails: { malformed: true },
            phone_numbers: MARKUP_PAYLOAD,
            all_hashtags: [MARKUP_PAYLOAD],
            posts: [{
                url: BAD_URLS[0],
                text: MARKUP_PAYLOAD,
                created_at: MARKUP_PAYLOAD,
                reaction_count: NUMERIC_PAYLOAD,
                comment_count: NUMERIC_PAYLOAD,
                repost_count: NUMERIC_PAYLOAD,
                hashtags: [MARKUP_PAYLOAD],
                author: { name: MARKUP_PAYLOAD, profile_url: BAD_URLS[1] },
            }],
            rocketreach: {
                success: false,
                raw_emails: { malformed: true },
                raw_phones: { malformed: true },
                emails: [MARKUP_PAYLOAD],
                phones: [MARKUP_PAYLOAD],
            },
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
            hashtags: [MARKUP_PAYLOAD],
        },
        facebook: {
            success: true,
            page_name: "fixture",
            all_hashtags: [MARKUP_PAYLOAD],
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

    sandbox.renderDiagnosticsPanel({
        wmn_results: { status: "success", hits_count: 0 },
        provider_statuses: {
            apify: {
                state: "quota_exhausted",
                monthly_usage_usd: 5.08,
                monthly_limit_usd: 5,
                usage_cycle_ends_at: "2030-01-01T00:00:00.000Z",
            },
            instagram: {
                success: false,
                status: "error",
                error: "Apify monthly usage limit is exhausted",
                error_code: "quota_exhausted",
            },
        },
        scraped_data: {},
        dorking_results: { status: "completed", results_count: 0 },
        telegram_cti: { status: "skipped", usage: {} },
        internal_database_matches: { status: "not_available", matches: [] },
    });
    html = nodeFor("diagnostics-body").innerHTML;
    assert(html.includes("Apify Account Capacity"), "Apify capacity diagnostic was omitted");
    assert(html.includes("$5.08 / $5.00"), "Apify quota counters were omitted");
    assert(html.includes("skipped paid Actor launches"), "Apify recovery guidance was omitted");

    sandbox.renderDiagnosticsPanel({
        wmn_results: { status: "skipped", error_code: "identifier_not_username" },
        provider_statuses: {
            apify: { state: "not_checked" },
            instagram: { status: "skipped", error_code: "identifier_not_username" },
            facebook: { status: "skipped", error_code: "identifier_not_username" },
            tiktok: { status: "skipped", error_code: "identifier_not_username" },
            twitter: { status: "skipped", error_code: "identifier_not_username" },
            linkedin: { status: "skipped", error_code: "identifier_not_username" },
            linkedin_posts: { success: true, status: "completed" },
            signalhire: { success: true, status: "success", credits_remaining: 42 },
            rocketreach: { status: "skipped", error_code: "exact_contact_routed_to_signalhire" },
        },
        scraped_data: {},
        dorking_results: { status: "completed", results_count: 1 },
        telegram_cti: { status: "no_results", usage: {} },
        internal_database_matches: { status: "not_available", matches: [] },
    });
    html = nodeFor("diagnostics-body").innerHTML;
    assert(html.includes("Non-username targets are not sent to username discovery sites."));
    assert(html.includes("non-username target was not sent to username-oriented scrapers"));
    assert(html.includes("LinkedIn Public Posts Scraper"), "LinkedIn posts diagnostics were merged into the profile collector");
    assert(html.includes("Bounded public LinkedIn post collection completed."), "LinkedIn posts success status lacked bounded-collection wording");
    assert(html.includes("Provider credits remaining: 42."));

    sandbox.renderDiagnosticsPanel({
        wmn_results: { status: "success", hits_count: 0 },
        provider_statuses: {
            linkedin_posts: { status: "skipped", error_code: "post_collection_not_selected" },
        },
        scraped_data: {},
        dorking_results: { status: "completed", results_count: 0 },
        telegram_cti: { status: "no_results", usage: {} },
        internal_database_matches: { status: "not_available", matches: [] },
    });
    html = nodeFor("diagnostics-body").innerHTML;
    assert(html.includes("Public LinkedIn posts were intentionally skipped"), "LinkedIn posts skip reason was misleading");
    assert(html.includes("no post-search Actor call was made"), "LinkedIn posts skip status did not confirm the zero-call decision");

    sandbox.renderDiagnosticsPanel({
        wmn_results: { status: "success", hits_count: 0 },
        provider_statuses: {
            linkedin_posts: { status: "no_attributed_posts", success: false },
        },
        scraped_data: {},
        dorking_results: { status: "completed", results_count: 0 },
        telegram_cti: { status: "no_results", usage: {} },
        internal_database_matches: { status: "not_available", matches: [] },
    });
    html = nodeFor("diagnostics-body").innerHTML;
    assert(html.includes("no returned post was attributable"), "LinkedIn attribution filtering was reported as a provider failure");
    assert(html.includes("unattributed posts were excluded"), "LinkedIn posts diagnostics omitted the attribution safeguard");

    sandbox.renderDiagnosticsPanel({
        wmn_results: { status: "success", hits_count: 0 },
        provider_statuses: {
            linkedin_posts: { status: "error", error_code: "actor_failed", error: MARKUP_PAYLOAD },
        },
        scraped_data: {},
        dorking_results: { status: "completed", results_count: 0 },
        telegram_cti: { status: "no_results", usage: {} },
        internal_database_matches: { status: "not_available", matches: [] },
    });
    html = nodeFor("diagnostics-body").innerHTML;
    assert(!html.includes(MARKUP_PAYLOAD), "LinkedIn posts diagnostic error markup reached HTML");
    assert(html.includes("APIFY_LINKEDIN_POSTS_ACTOR_ID"), "LinkedIn posts failure recovery omitted the Actor configuration");

    sandbox.renderDiagnosticsPanel({
        wmn_results: { status: "success", hits_count: 0 },
        provider_statuses: {
            instagram: { status: "error", error_code: "not_configured" },
        },
        scraped_data: {},
        dorking_results: { status: "completed", results_count: 0 },
        telegram_cti: { status: "no_results", usage: {} },
        internal_database_matches: { status: "not_available", matches: [] },
    });
    html = nodeFor("diagnostics-body").innerHTML;
    assert(html.includes("Configure APIFY_API_TOKEN only if this provider route is approved."));

    const rrContactFixture = {
        success: false,
        full_name: "Contact Fixture",
        raw_emails: [],
        raw_phones: [],
        emails: ["returned@example.org"],
        phones: ["+91 11234 56789"],
    };
    const staleNestedRRFixture = {
        ...rrContactFixture,
        full_name: "STALE-NESTED-ROCKETREACH",
        emails: ["stale-nested@example.org"],
    };
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
            all_hashtags: ["CyberSafe", "OSINT"],
            posts: [{
                url: VALID_LINKS.linkedinPost,
                text: "A public LinkedIn post about cyber safety.",
                created_at: "2030-01-02T03:04:05Z",
                reaction_count: 12,
                comment_count: 3,
                repost_count: 2,
                hashtags: ["CyberSafe", "OSINT"],
                author: { name: "Valid Profile", profile_url: VALID_LINKS.linkedin },
            }],
            emails: [
                { email: "linkedin@example.org", status: "observed" },
                { email: "returned@example.org", status: "observed" },
            ],
            phone_numbers: [
                { phone: "+91 98765 43210", status: "possible" },
                { phone: "+91 11234 56789", status: "possible" },
            ],
            rocketreach: staleNestedRRFixture,
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
        rocketreach: rrContactFixture,
        twitter: {
            success: true,
            username: "fixture",
            follower_count: 1,
            following_count: 1,
            post_count: 1,
            profile_pic_url: VALID_IMAGES.twitter,
            tweets: [],
            hashtags: ["CyberSafe", "UPPolice"],
        },
        facebook: {
            success: true,
            page_name: "fixture",
            all_hashtags: ["CyberSafe", "PublicSafety"],
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
    assert(html.includes(`href="${VALID_LINKS.linkedinPost}"`), "valid LinkedIn post link disappeared");
    assertImagesUseAuthenticatedProxy(html, safeURL, "app valid platform images", 3);
    assert(html.includes("PUBLIC POST HASHTAGS (2 UNIQUE)"), "X/Facebook hashtag headings were omitted");
    assert(html.includes("#CyberSafe"), "X/Facebook hashtag chips were omitted");
    assert(html.includes("LINKEDIN POST HASHTAGS (2 UNIQUE)"), "LinkedIn hashtag summary was omitted");
    assert(html.includes("RECENT PUBLIC LINKEDIN POSTS (SHOWING 1)"), "LinkedIn posts section was omitted");
    assert(html.includes("A public LinkedIn post about cyber safety."), "LinkedIn post text was omitted");
    assert(html.includes("Reactions: 12"), "LinkedIn post metrics were omitted");
    assert(html.includes("returned@example.org"), "empty RocketReach raw email array masked canonical contacts");
    assert(html.includes("+91 11234 56789"), "empty RocketReach raw phone array masked canonical contacts");
    assert(html.includes("CONTACT DATA RETURNED"), "returned contact data was mislabeled");
    assert(!html.includes("CONFIRMED MATCH"), "provider contact data was presented as an identity confirmation");
    assert.equal((html.match(/returned@example\.org/g) || []).length, 1, "duplicate RocketReach cards repeated the same contact");
    assert(!html.includes("STALE-NESTED-ROCKETREACH"), "nested RocketReach suppressed the richer top-level payload");
    assert(!html.includes("stale-nested@example.org"), "stale nested RocketReach contacts were rendered with a top-level payload");

    sandbox.renderPlatformDossiers({
        linkedin: {
            success: true,
            posts: [],
            recent_posts: Array.from({ length: 11 }, (_value, index) => ({
                text: `BOUNDED-LINKEDIN-POST-${index}`,
                hashtags: ["Bounded"],
            })),
        },
    });
    html = nodeFor("platform-dossiers-body").innerHTML;
    assert(html.includes("RECENT PUBLIC LINKEDIN POSTS (SHOWING 10)"), "LinkedIn post previews were not bounded to ten");
    assert(html.includes("BOUNDED-LINKEDIN-POST-9"), "the tenth bounded LinkedIn post was omitted");
    assert(!html.includes("BOUNDED-LINKEDIN-POST-10"), "more than ten LinkedIn posts reached the dashboard");

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
        consolidated_identity: {
            confidence_percentage: NUMERIC_PAYLOAD,
            emails: [{ email: "safe@example.org", status: MARKUP_PAYLOAD, sources: [{ provider: MARKUP_PAYLOAD }] }],
            phones: [{ phone: "+91 98765 43210", status: MARKUP_PAYLOAD, sources: [{ source: MARKUP_PAYLOAD }] }],
            email_guesses: [{ email: MARKUP_PAYLOAD, status: "likely" }],
        },
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
            linkedin: {
                success: true,
                profile_url: BAD_URLS[0],
                profile_pic_url: ATTRIBUTE_BREAKER,
                all_hashtags: [MARKUP_PAYLOAD],
                posts: [{
                    url: BAD_URLS[0],
                    text: MARKUP_PAYLOAD,
                    created_at: MARKUP_PAYLOAD,
                    reaction_count: NUMERIC_PAYLOAD,
                    comment_count: NUMERIC_PAYLOAD,
                    repost_count: NUMERIC_PAYLOAD,
                    hashtags: [MARKUP_PAYLOAD],
                    author: { name: MARKUP_PAYLOAD },
                }],
            },
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
        consolidated_identity: {
            likely_name: "Contact Fixture",
            confidence_percentage: 80,
            overall_confidence: "high",
            emails: [{
                email: "report@example.org",
                status: "verified",
                verification_provider: "hunter",
                sources: [
                    { source: "instagram", provider: "apify", field: "email", collection_method: "public_profile" },
                    { provider: "RocketReach", field: "emails", collection_method: "enrichment_provider" },
                ],
            }],
            phones: [{
                phone: "+91 98765 43210",
                normalized: "+919876543210",
                status: "valid",
                sources: [{ provider: "SignalHire", field: "phones", collection_method: "enrichment_provider" }],
            }],
            email_guesses: [{
                email: "candidate@example.org",
                status: "likely",
                reason: "Generated pattern candidate; not provider-observed",
                sources: [{ source: "pattern generator", field: "candidate", collection_method: "generated_pattern" }],
            }],
        },
        associated_accounts: [{
            platform: "GitHub",
            username: "valid-profile",
            url: VALID_LINKS.github,
            confidence: 80,
        }],
        wmn_results: { hits: [{ site: "X", handle: "valid_profile", ms: 1, url: VALID_LINKS.x }] },
        dorking_results: {
            status: "completed",
            provider: "serpapi",
            queries_attempted: 1,
            queries_run: 1,
            duplicates_removed: 2,
            results: [{
                category: "public",
                link: VALID_LINKS.public,
                title: "Valid public result",
                domain: "public.example.org",
                query_category: "Exact mentions",
            }],
        },
        scraped_data: {
            linkedin: {
                success: true,
                profile_url: VALID_LINKS.linkedin,
                profile_pic_url: VALID_IMAGES.linkedin,
                all_hashtags: ["CyberSafe", "OSINT"],
                posts: [{
                    url: VALID_LINKS.linkedinPost,
                    text: "A public LinkedIn post included in the report.",
                    created_at: "2030-01-02T03:04:05Z",
                    reaction_count: 12,
                    comment_count: 3,
                    repost_count: 2,
                    hashtags: ["CyberSafe", "OSINT"],
                    author: { name: "Valid Profile" },
                }],
                emails: ["pdf-returned@example.org"],
                phones: ["+91 11234 56789"],
                rocketreach: {
                    success: false,
                    full_name: "Contact Fixture",
                    raw_emails: [],
                    raw_phones: [],
                    emails: ["pdf-returned@example.org"],
                    phones: ["+91 11234 56789"],
                },
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
        VALID_LINKS.linkedinPost,
        VALID_LINKS.instagram,
        VALID_LINKS.facebook,
        VALID_LINKS.github,
        VALID_LINKS.x,
        VALID_LINKS.public,
    ]) {
        assert(html.includes(`href="${url.replace(/&/g, "&amp;")}"`), `valid PDF link disappeared: ${url}`);
    }
    assert(html.includes("Status: COMPLETED"), "PDF omitted dorking status");
    assert(html.includes("Provider: SERPAPI"), "PDF omitted dorking provider");
    assert(html.includes("Duplicates removed: 2"), "PDF omitted dorking deduplication count");
    assert(html.includes("Exact mentions"), "PDF omitted dork query category");
    assert(html.includes("Discovered / Provided Email Addresses (1)"), "PDF omitted canonical observed-email count");
    assert(html.includes("report@example.org"), "PDF omitted a canonical observed email");
    assert(html.includes("Generated Email Candidates — Not Confirmed (1)"), "PDF did not separate generated email guesses");
    assert(html.includes("candidate@example.org"), "PDF omitted generated email candidates");
    assert(html.includes("Discovered / Provided Phone Numbers (1)"), "PDF omitted canonical phone count");
    assert(html.includes("+91 98765 43210"), "PDF omitted a canonical phone number");
    assert(html.includes("RocketReach"), "PDF omitted email provenance");
    assert(html.includes("SignalHire"), "PDF omitted phone provenance");
    assert(html.includes("instagram"), "PDF hid platform provenance behind the generic provider label");
    assert(html.includes("via hunter"), "PDF omitted the email verification provider");
    assert(html.includes("pdf-returned@example.org"), "empty RocketReach raw array masked canonical PDF contacts");
    assert(html.includes("LinkedIn Post Hashtags"), "PDF omitted LinkedIn post hashtags");
    assert(html.includes("#CyberSafe"), "PDF omitted a LinkedIn post hashtag");
    assert(html.includes("Recent Public LinkedIn Posts (Showing 1)"), "PDF omitted LinkedIn posts");
    assert(html.includes("A public LinkedIn post included in the report."), "PDF omitted LinkedIn post text");
    assert(html.includes("Reactions: 12"), "PDF omitted LinkedIn post metrics");
    assert.equal((html.match(/pdf-returned@example\.org/g) || []).length, 1, "PDF repeated merged RocketReach contacts");
    assert(html.includes("CONTACT DATA RETURNED"), "PDF overstated provider-returned contact data");
    assert(!html.includes("CONFIRMED MATCH"), "PDF presented provider-returned contact data as identity confirmation");
    assert(!html.includes("[object Object]"), "PDF stringified a structured contact object");
    assertImagesUseAuthenticatedProxy(html, safeURL, "valid PDF media", 8);

    const boundedLinkedInReport = validExporterData();
    boundedLinkedInReport.scraped_data.linkedin.posts = [];
    boundedLinkedInReport.scraped_data.linkedin.recent_posts = Array.from({ length: 11 }, (_value, index) => ({
        text: `BOUNDED-PDF-LINKEDIN-POST-${index}`,
        hashtags: ["Bounded"],
    }));
    html = exporter.generateReportHtml(boundedLinkedInReport);
    assert(html.includes("Recent Public LinkedIn Posts (Showing 10)"), "PDF LinkedIn post previews were not bounded to ten");
    assert(html.includes("BOUNDED-PDF-LINKEDIN-POST-9"), "PDF omitted the tenth bounded LinkedIn post");
    assert(!html.includes("BOUNDED-PDF-LINKEDIN-POST-10"), "PDF included more than ten LinkedIn posts");

    const ctiFailureData = validExporterData();
    ctiFailureData.telegram_cti = {
        status: "error",
        error: `CTI provider quota exhausted ${MARKUP_PAYLOAD}`,
        total_records: 0,
        databases: [],
        results: [],
        usage: {
            logical_searches_performed: 1,
            logical_search_limit: 5,
            http_attempts: 1,
            http_attempt_limit: 6,
        },
    };
    html = exporter.generateReportHtml(ctiFailureData);
    assert(html.includes("CTI provider quota exhausted"), "PDF hid CTI provider failure");
    assert(html.includes("Provider calls: 1/6"), "PDF omitted CTI quota usage");
    assert(!html.includes("No records matched in the completed CTI searches"));
    assert(!html.includes(MARKUP_PAYLOAD), "PDF CTI error markup was not escaped");
}

function runDemoContactConsistencyTests() {
    const discovery = demoData.contact_discovery;
    const identity = demoData.consolidated_identity;
    assert(discovery, "demo omitted canonical contact_discovery");
    assert(identity, "demo omitted consolidated_identity");
    assert.equal(discovery.email_count, discovery.emails.length);
    assert.equal(discovery.phone_count, discovery.phones.length);
    assert.equal(discovery.email_guess_count, discovery.email_guesses.length);
    assert.deepEqual(discovery.emails, identity.emails);
    assert.deepEqual(discovery.phones, identity.phones);
    assert.deepEqual(discovery.email_guesses, identity.email_guesses);
}

async function main() {
    await runAppTests();
    runExporterTests();
    runDemoContactConsistencyTests();
    console.log("legacy_render_security.test.cjs: all assertions passed");
}

main().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
