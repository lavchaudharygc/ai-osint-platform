const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const mappers = require("../data_mappers.js");
const frontendRoot = path.resolve(__dirname, "..");
const appSource = fs.readFileSync(path.join(frontendRoot, "app.js"), "utf8");

function fakeElement() {
    const attributes = new Map();
    return {
        innerHTML: "",
        innerText: "",
        className: "",
        style: {},
        children: [],
        classList: {
            add() {},
            remove() {},
            contains() { return false; },
            toggle() {}
        },
        addEventListener() {},
        appendChild(child) { this.children.push(child); },
        querySelector() { return null; },
        setAttribute(name, value) { attributes.set(name, String(value)); },
        getAttribute(name) { return attributes.get(name) ?? null; }
    };
}

function loadApp(elements = {}) {
    const document = {
        getElementById(id) { return elements[id] || null; },
        querySelector() { return null; },
        querySelectorAll() { return []; },
        createElement() { return fakeElement(); }
    };
    const window = {
        OSINTDataMappers: mappers,
        addEventListener() {},
        innerWidth: 1280,
        document
    };
    window.window = window;

    const context = vm.createContext({
        URL,
        alert() {},
        clearInterval,
        clearTimeout,
        console,
        document,
        encodeURIComponent,
        fetch: async () => ({ ok: false, json: async () => ({}) }),
        navigator: { clipboard: { writeText: async () => {} } },
        setInterval,
        setTimeout,
        window
    });
    vm.runInContext(appSource, context, { filename: "app.js" });
    return context;
}

function renderDetails(platform, payload, username = "target") {
    const app = loadApp();
    const container = fakeElement();
    app.renderScrapedDetails(platform, payload, container, username, false);
    return container.innerHTML;
}

test("Twitter renderer consumes canonical profile and engagement fields", () => {
    const html = renderDetails("twitter", {
        success: true,
        full_name: "Canonical Twitter Name",
        username: "canonical_user",
        follower_count: 4321,
        following_count: 321,
        post_count: 5678,
        statuses_count: 999,
        joined_at: "2024-03-02T12:00:00Z",
        tweets: [{
            id: "tw-canonical",
            text: "Canonical tweet body",
            like_count: 1234,
            favorite_count: 999,
            retweet_count: 77,
            reply_count: 17,
            created_at: "2026-07-10T12:30:00Z"
        }]
    });

    assert.match(html, /Canonical Twitter Name/);
    assert.match(html, /5,678/);
    assert.match(html, /Canonical tweet body/);
    assert.match(html, /1,234/);
    assert.match(html, /Replies 17/);
    assert.doesNotMatch(html, />999</);
});

test("Reddit renderer consumes canonical text, dates, and comment counts", () => {
    const html = renderDetails("reddit", {
        success: true,
        username: "canonical_redditor",
        posts: [{
            id: "rd-post",
            title: "Canonical title",
            text: "Canonical Reddit post text",
            selftext: "legacy text should lose",
            subreddit: "osint",
            comment_count: 23,
            num_comments: 99,
            created_at: "2026-07-09T08:15:00Z"
        }],
        comments: [{
            id: "rd-comment",
            text: "Canonical Reddit comment text",
            body: "legacy comment should lose",
            subreddit: "osint",
            created_at: "2026-07-09T10:30:00Z"
        }]
    });

    assert.match(html, /Canonical Reddit post text/);
    assert.match(html, /Canonical Reddit comment text/);
    assert.match(html, /23<\/span>/);
    assert.doesNotMatch(html, /legacy text should lose/);
    assert.doesNotMatch(html, /legacy comment should lose/);
    assert.doesNotMatch(html, />99</);
});

test("Facebook renderer consumes canonical date and engagement fields", () => {
    const html = renderDetails("facebook", {
        success: true,
        full_name: "Canonical Facebook Page",
        posts: [{
            id: "fb-post",
            text: "Canonical Facebook post",
            created_at: "2026-07-07T11:00:00Z",
            like_count: 14,
            likes: 99,
            reaction_count: 18,
            comment_count: 3,
            share_count: 2
        }]
    });

    assert.match(html, /Canonical Facebook post/);
    assert.match(html, /Likes 14/);
    assert.match(html, /Reactions 18/);
    assert.match(html, /Comments 3/);
    assert.match(html, /Shares 2/);
    assert.doesNotMatch(html, /Likes 99/);
});

test("collection coverage renders normalized content and actor health consistently", () => {
    const status = fakeElement();
    const results = fakeElement();
    const app = loadApp({
        "collection-coverage-status": status,
        "collection-coverage-results": results
    });

    app.renderCollectionCoverage({
        platform_content: {
            platform: "instagram",
            posts: [{ text: "Normalized primary content" }],
            replies: [],
            comments: []
        },
        apify_social_results: {
            status: "completed_with_warnings",
            summary: { total: 2, completed: 1, empty: 1, failed: 0, not_configured: 0 },
            actors: {
                twitter_tweet_search_v2: {
                    success: true,
                    status: "completed",
                    tweets: [{ text: "Actor-only visible tweet" }]
                },
                facebook_posts: {
                    success: true,
                    status: "empty_dataset",
                    error: "No public records returned",
                    posts: []
                }
            }
        }
    });

    assert.equal(status.innerText, "COMPLETED WITH WARNINGS");
    assert.match(results.innerHTML, /Normalized primary content/);
    assert.match(results.innerHTML, /Actor-only visible tweet/);
    assert.match(results.innerHTML, /actor-status-warning/);
    assert.match(results.innerHTML, /No public records returned/);
});

test("Telegram invite details render without requiring or exposing a username/hash", () => {
    const html = renderDetails("telegram", {
        success: true,
        exists: true,
        platform: "telegram",
        target_type: "invite_link",
        invite_hash_redacted: true,
        full_name: "Private Group Preview",
        member_count: 0
    });

    assert.match(html, /Private Group Preview/);
    assert.match(html, /Invite preview \(hash redacted\)/);
    assert.match(html, /Members/);
    assert.match(html, />0</);
    assert.doesNotMatch(html, /privateInviteHash/);
});

test("new investigation skeleton clears stale AI result values", () => {
    const confidence = Object.assign(fakeElement(), { innerText: "Confidence Index: 91%" });
    const decision = Object.assign(fakeElement(), { innerText: "HIGHLY LIKELY" });
    const engine = Object.assign(fakeElement(), { innerText: "completed with groq" });
    const summary = Object.assign(fakeElement(), { innerText: "Previous case summary" });
    const collectionStatus = Object.assign(fakeElement(), { innerText: "COMPLETED" });
    const telegramStatus = Object.assign(fakeElement(), { innerText: "Active Account/Channel" });
    const app = loadApp({
        "ai-confidence": confidence,
        "ai-decision-badge": decision,
        "ai-engine-status": engine,
        "ai-summary": summary,
        "collection-coverage-status": collectionStatus,
        "telegram-intel-status": telegramStatus
    });

    app.renderSkeletonDossier();

    assert.equal(confidence.innerText, "Confidence Index: Not available");
    assert.equal(decision.innerText, "PENDING");
    assert.equal(engine.innerText, "running");
    assert.match(summary.innerText, /Awaiting correlation results/);
    assert.equal(collectionStatus.innerText, "RUNNING");
    assert.equal(telegramStatus.innerText, "Loading");
});

test("both HTML entry points begin with honest AI status and mapper load order", () => {
    for (const filename of ["index.html", "mock_test.html"]) {
        const html = fs.readFileSync(path.join(frontendRoot, filename), "utf8");
        assert.match(html, /id="ai-confidence"[^>]*>Confidence: Not available</);
        assert.match(html, /id="ai-engine-status"[^>]*>not run</);
        assert.ok(html.indexOf("data_mappers.js") < html.indexOf("app.js"));
    }
});

test("personality helper treats fallback types and zero confidence as insufficient evidence", () => {
    const app = loadApp();

    for (const primaryType of [undefined, "unknown", "unclassified", "insufficient_evidence"]) {
        const result = app.getPersonalityClassification({ primary_type: primaryType, confidence: 0.72 });
        assert.equal(result.isClassified, false);
        assert.equal(result.label, "Insufficient Evidence");
        assert.equal(result.confidencePercent, 0);
    }

    const zeroConfidence = app.getPersonalityClassification({ primary_type: "politics", confidence: 0 });
    assert.equal(zeroConfidence.isClassified, false);
    assert.equal(zeroConfidence.label, "Insufficient Evidence");
});

test("personality helper exposes the new normal profile labels", () => {
    const app = loadApp();
    const expectedLabels = {
        politics: "Politics",
        student: "Student",
        art: "Art",
        business: "Business"
    };

    for (const [primaryType, expectedLabel] of Object.entries(expectedLabels)) {
        const result = app.getPersonalityClassification({ primary_type: primaryType, confidence: 0.62 });
        assert.equal(result.isClassified, true);
        assert.equal(result.primaryType, primaryType);
        assert.equal(result.label, expectedLabel);
        assert.equal(result.confidencePercent, 62);
    }
});

test("dashboard renders an unknown personality result as insufficient evidence", () => {
    const status = fakeElement();
    const results = fakeElement();
    const app = loadApp({
        "personality-profile-status": status,
        "personality-profile-results": results
    });

    app.renderInvestigationResults({
        reverse_lookup_results: {
            profile_type: {
                primary_type: "unknown",
                confidence: 0,
                description: "No reliable public indicators were found."
            }
        }
    });

    assert.equal(status.innerText, "Insufficient Evidence");
    assert.match(results.innerHTML, /Insufficient Evidence/);
    assert.match(results.innerHTML, /No reliable public indicators were found/);
    assert.doesNotMatch(results.innerHTML, /Dominant Profile Type/);
});

test("official report does not present a fallback personality as dominant", () => {
    const app = loadApp();
    const html = app.renderOfficialReportTemplate({
        status: "completed",
        platform_data: { username: "target", platform: "instagram" },
        risk_assessment: { level: "low", score: 0, factors: [] },
        reverse_lookup_results: {
            profile_type: {
                primary_type: "insufficient_evidence",
                confidence: 0,
                description: "More public evidence is required."
            }
        }
    }, "CASE-TEST");

    assert.match(html, /Classification Status:<\/strong> Insufficient Evidence/);
    assert.match(html, /More public evidence is required/);
    assert.doesNotMatch(html, /Dominant Profile Type/);
});
