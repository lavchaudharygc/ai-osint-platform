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

test("Reddit renderer combines OAuth profile metadata with Apify activity", () => {
    const html = renderDetails("reddit", {
        success: true,
        username: "canonical_redditor",
        bio: "Canonical public Reddit bio",
        profile_pic_url: "https://styles.redditmedia.com/avatar.png",
        profile_url: "https://www.reddit.com/user/canonical_redditor/",
        link_karma: 12000,
        comment_karma: 3000,
        total_karma: 15123,
        account_created_at: "2016-07-09T08:15:00Z",
        account_age_days: 3650,
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

    assert.match(html, /Canonical public Reddit bio/);
    assert.match(html, /styles\.redditmedia\.com/);
    assert.match(html, /Post Karma/);
    assert.match(html, /12,000/);
    assert.match(html, /Comment Karma/);
    assert.match(html, /3,000/);
    assert.match(html, /Total Karma/);
    assert.match(html, /15,123/);
    assert.match(html, /Account Age/);
    assert.match(html, /3,650 days/);
    assert.match(html, /Cake Day/);
    assert.match(html, /OAuth profile \+ Apify activity/);
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

test("TikTok renderer exposes canonical profile, video, and engagement fields", () => {
    const html = renderDetails("tiktok", {
        success: true,
        username: "canonical_creator",
        full_name: "Canonical TikTok Creator",
        bio: "Public creator biography",
        follower_count: 1200,
        following_count: 34,
        post_count: 9,
        likes_count: 7654,
        posts: [{
            id: "tt-video",
            text: "Canonical TikTok video caption",
            created_at: "2026-07-08T10:00:00Z",
            like_count: 300,
            view_count: 4321,
            comment_count: 12,
            share_count: 8,
            hashtags: ["osint"]
        }]
    });

    assert.match(html, /Canonical TikTok Creator/);
    assert.match(html, /Public creator biography/);
    assert.match(html, /Canonical TikTok video caption/);
    assert.match(html, /Views 4,321/);
    assert.match(html, /#osint/);
    assert.match(html, /7,654/);
});

test("GitHub renderer exposes profile metadata and public repositories", () => {
    const html = renderDetails("github", {
        success: true,
        username: "octocat",
        profile: {
            username: "octocat",
            full_name: "The Octocat",
            bio: "GitHub mascot and developer",
            public_repos: 8,
            followers: 100,
            following: 2,
            company: "GitHub",
            location: "San Francisco"
        },
        repositories: [{
            id: 10,
            name: "hello-world",
            full_name: "octocat/hello-world",
            description: "Canonical repository description",
            language: "JavaScript",
            license: "MIT",
            stars: 80,
            forks: 9,
            open_issues: 1,
            updated_at: "2026-07-07T11:00:00Z"
        }],
        organizations: [{
            id: 20,
            username: "github",
            description: "How people build software"
        }],
        contributions: {
            period_start: "2025-07-28T00:00:00Z",
            period_end: "2026-07-28T00:00:00Z",
            total_contributions: 148,
            commit_contributions: 120,
            issue_contributions: 4,
            pull_request_contributions: 12,
            pull_request_review_contributions: 9,
            restricted_contributions: 3,
            has_restricted_contributions: true
        }
    });

    assert.match(html, /The Octocat/);
    assert.match(html, /GitHub mascot and developer/);
    assert.match(html, /octocat\/hello-world/);
    assert.match(html, /Canonical repository description/);
    assert.match(html, /Stars 80/);
    assert.match(html, /JavaScript/);
    assert.match(html, /MIT/);
    assert.match(html, /Contribution Activity/);
    assert.match(html, /Total Contributions/);
    assert.match(html, /148/);
    assert.match(html, /Commits/);
    assert.match(html, /120/);
    assert.match(html, /restricted\/private contributions/);
    assert.match(html, /Public Organizations/);
    assert.match(html, /@github/);
    assert.match(html, /How people build software/);
});

test("YouTube renderer exposes channel metadata, subscribers, and recent videos", () => {
    const html = renderDetails("youtube", {
        success: true,
        exists: true,
        channel_id: "UC1234567890123456789012",
        handle: "canonicalchannel",
        channel_name: "Canonical YouTube Channel",
        description: "Public channel description",
        profile_url: "https://www.youtube.com/@canonicalchannel",
        avatar_url: "https://yt3.googleusercontent.com/channel-avatar",
        subscriber_count: 1234,
        view_count: 98765,
        video_count: 42,
        channel: {
            published_at: "2018-05-04T10:00:00Z",
            country: "IN",
            default_language: "en"
        },
        recent_videos: [{
            video_id: "video-1",
            title: "Canonical recent video",
            description: "Recent video description",
            published_at: "2026-07-26T10:00:00Z",
            url: "https://www.youtube.com/watch?v=video-1",
            channel_name: "Canonical YouTube Channel"
        }]
    });

    assert.match(html, /YouTube Channel/);
    assert.match(html, /Canonical YouTube Channel/);
    assert.match(html, /Public channel description/);
    assert.match(html, /Subscribers/);
    assert.match(html, /1,234/);
    assert.match(html, /Channel Views/);
    assert.match(html, /98,765/);
    assert.match(html, /Recent YouTube Videos/);
    assert.match(html, /Canonical recent video/);
    assert.match(html, /Recent video description/);
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

test("collection coverage prefers provider-neutral results and shows routing, budget, and cache metadata", () => {
    const status = fakeElement();
    const results = fakeElement();
    const app = loadApp({
        "collection-coverage-status": status,
        "collection-coverage-results": results
    });

    app.renderCollectionCoverage({
        provider_results: {
            status: "completed_with_warnings",
            routing: {
                google_search: "serpapi",
                linkedin: "apify_linkedin_profile_scraper",
                reddit: "reddit_oauth_plus_apify",
                github: "github_rest_plus_graphql",
                youtube: "youtube_data_api_v3"
            },
            social: {
                twitter: {
                    success: true,
                    status: "completed",
                    provider: "apify",
                    tweets: [{ text: "Neutral social result" }]
                }
            }
        },
        execution_metadata: {
            cache: { hit: false, mode: "use", ttl_seconds: 3600 },
            provider_call_budget: {
                maximum: 8,
                used: 3,
                remaining: 5,
                skipped: [{ capability: "social.facebook", reason: "provider_call_limit_exceeded" }]
            }
        },
        apify_social_results: {
            actors: {
                twitter_profile_and_replies: {
                    success: true,
                    status: "completed",
                    tweets: [{ text: "Stale legacy social result" }]
                }
            }
        }
    });

    assert.equal(status.innerText, "COMPLETED WITH WARNINGS");
    assert.match(results.innerHTML, /provider-neutral/);
    assert.match(results.innerHTML, /3\/8 used/);
    assert.match(results.innerHTML, /miss \(use\)/);
    assert.match(results.innerHTML, /Capability routing/);
    assert.match(results.innerHTML, /google search/);
    assert.match(results.innerHTML, /serpapi/);
    assert.match(results.innerHTML, /apify linkedin profile scraper/);
    assert.match(results.innerHTML, /reddit oauth plus apify/);
    assert.match(results.innerHTML, /github rest plus graphql/);
    assert.match(results.innerHTML, /youtube data api v3/);
    assert.match(results.innerHTML, /Neutral social result/);
    assert.doesNotMatch(results.innerHTML, /Stale legacy social result/);
    assert.match(results.innerHTML, /skipped to stay within/);
});

test("Google dorking configuration copy names SerpAPI as the only provider", () => {
    assert.match(appSource, /Configure[\s\S]*SERPAPI_KEY/);
    assert.match(appSource, /Google search is routed only through SerpAPI/);
    assert.doesNotMatch(appSource, /BRIGHTDATA_SERP_API_KEY/);
    assert.doesNotMatch(appSource, /APIFY_API_TOKEN/);
});

test("primary platform selector includes TikTok, GitHub, and YouTube", () => {
    const html = fs.readFileSync(path.join(frontendRoot, "index.html"), "utf8");
    assert.match(html, /<div class="form-row">\s*<label>Target Platform<\/label>/);
    assert.match(html, /<option value="tiktok">TikTok<\/option>/);
    assert.match(html, /<option value="github">GitHub<\/option>/);
    assert.match(html, /<option value="youtube">YouTube<\/option>/);
    assert.doesNotMatch(html, /<div class="form-row" style="display:\s*none;">\s*<label>Target Platform/);
});

test("on-demand routes use YouTube Data API and combined Reddit OAuth plus Apify contracts", async () => {
    const youtubeDetails = fakeElement();
    const redditDetails = fakeElement();
    const app = loadApp({
        "youtube-details": youtubeDetails,
        "reddit-details": redditDetails
    });
    const requests = [];
    app.fetch = async (url, options) => {
        requests.push({ url, options });
        if (String(url).endsWith("/providers/youtube/channel")) {
            return {
                ok: true,
                json: async () => ({
                    success: true,
                    channel_name: "Routed YouTube Channel",
                    handle: "routed",
                    recent_videos: []
                })
            };
        }
        return {
            ok: true,
            json: async () => ({
                success: true,
                username: "routed_redditor",
                total_karma: 9,
                posts: [],
                comments: []
            })
        };
    };

    await app.scrapePlatformOnDemand("youtube", "@routed", "youtube-details", fakeElement());
    await app.scrapePlatformOnDemand("reddit", "routed_redditor", "reddit-details", fakeElement());

    assert.equal(requests.length, 2);
    assert.match(String(requests[0].url), /\/api\/v1\/providers\/youtube\/channel$/);
    assert.deepEqual(JSON.parse(requests[0].options.body), {
        target: "@routed",
        recent_video_limit: 5
    });
    assert.match(String(requests[1].url), /\/api\/v1\/providers\/reddit\/profile$/);
    assert.deepEqual(JSON.parse(requests[1].options.body), {
        username: "routed_redditor",
        max_posts: 10
    });
    assert.match(youtubeDetails.innerHTML, /Routed YouTube Channel/);
    assert.match(redditDetails.innerHTML, /Total Karma/);
    assert.match(appSource, /linkedin: "Apify LinkedIn collector"/);
    assert.match(appSource, /reddit: "Reddit OAuth \+ Apify collector"/);
    assert.doesNotMatch(appSource, /linkedin: "Bright Data collector"/);
});

test("advanced provider inputs expose and send every investigation schema field", () => {
    const withValue = (value) => Object.assign(fakeElement(), { value });
    const app = loadApp({
        "filter-hitek": Object.assign(fakeElement(), { checked: false }),
        "dork-query-limit": withValue("7"),
        "provider-call-limit": withValue("18"),
        "provider-email": withValue("analyst@example.com"),
        "provider-phone": withValue("+919876543210"),
        "company-domain": withValue("example.com"),
        "web-urls": withValue("https://example.com/a\nhttps://example.com/b"),
        "extract-urls": withValue("https://example.org/public, https://example.net/profile"),
        "extraction-prompt": withValue("Extract public identity attributes."),
        "cache-mode": withValue("refresh")
    });

    const request = JSON.parse(JSON.stringify(app.buildInvestigationRequestFromForm({
        username: "target",
        platform: "twitter",
        caseId: "CASE-1",
        depth: 4
    })));

    assert.deepEqual(request, {
        username: "target",
        platform: "twitter",
        case_id: "CASE-1",
        correlation_depth: 4,
        filter_hitek: false,
        web_urls: ["https://example.com/a", "https://example.com/b"],
        extract_urls: ["https://example.org/public", "https://example.net/profile"],
        cache_mode: "refresh",
        email: "analyst@example.com",
        phone_number: "+919876543210",
        company_domain: "example.com",
        extraction_prompt: "Extract public identity attributes.",
        dork_query_limit: 7,
        provider_call_limit: 18
    });

    const html = fs.readFileSync(path.join(frontendRoot, "index.html"), "utf8");
    for (const id of [
        "advanced-provider-inputs", "dork-query-limit", "provider-call-limit",
        "provider-email", "provider-phone", "company-domain", "web-urls",
        "extract-urls", "extraction-prompt", "cache-mode"
    ]) {
        assert.match(html, new RegExp(`id="${id}"`));
    }
});

test("dork status rendering distinguishes empty success, failure, and budget exhaustion", () => {
    const count = fakeElement();
    const results = fakeElement();
    const app = loadApp();

    const empty = app.getDorkStatusView({
        status: "completed",
        queries_run: 3,
        queries: [{ category: "twitter", query: "site:x.com target" }],
        results: [],
        errors: []
    });
    assert.equal(empty.kind, "empty");
    assert.match(empty.label, /Completed successfully - 0 matching hits/);

    app.renderDorkingPanel({
        status: "failed",
        provider: "serpapi",
        reason: "SerpAPI search failed.",
        queries_run: 1,
        queries: [{ category: "twitter", query: "site:x.com target" }],
        results: [],
        errors: [{ status: "429", message: "Quota exhausted", query: "site:x.com target" }]
    }, count, results);
    assert.match(count.innerText, /SerpAPI search failed/);
    assert.match(results.innerHTML, /Provider errors/);
    assert.match(results.innerHTML, /Quota exhausted/);
    assert.match(results.innerHTML, /site:x.com target/);
    assert.doesNotMatch(results.innerHTML, /0 matching general items/);

    const budget = app.getDorkStatusView({ status: "budget_exhausted", reason: "Call limit reached", results: [] });
    assert.equal(budget.kind, "budget");
    assert.match(budget.label, /Search not run/);
});

test("HTTP probes render as unverified candidates rather than profile matches", () => {
    const dossier = fakeElement();
    const app = loadApp({
        "platform-dossier-container": dossier,
        "target-username": Object.assign(fakeElement(), { value: "target" })
    });

    app.renderPlatformDossier({
        platform_data: { platform: "instagram", username: "target", success: false, status: "provider_error" },
        cross_platform_matches: [{
            platform: "twitter",
            exists: true,
            status_code: 200,
            url: "https://x.com/target"
        }],
        dorking_results: { status: "completed", results: [] }
    });

    const rendered = dossier.children.map(child => child.innerHTML).join("\n");
    assert.match(rendered, /Unverified candidate/);
    assert.match(rendered, /HTTP 200 URL PROBE/);
    assert.match(rendered, /does not confirm that a profile exists/);
    assert.doesNotMatch(rendered, /Profile found/);
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
    const riskScore = Object.assign(fakeElement(), { innerText: "95%" });
    const riskBadge = Object.assign(fakeElement(), { innerText: "CRITICAL RISK ASSESSMENT" });
    const riskNotice = Object.assign(fakeElement(), { innerText: "Previous disagreement", style: { display: "block" } });
    const app = loadApp({
        "ai-confidence": confidence,
        "ai-decision-badge": decision,
        "ai-engine-status": engine,
        "ai-summary": summary,
        "collection-coverage-status": collectionStatus,
        "telegram-intel-status": telegramStatus,
        "risk-score-num": riskScore,
        "risk-badge": riskBadge,
        "risk-fill": fakeElement(),
        "risk-consistency-notice": riskNotice
    });

    app.renderSkeletonDossier();

    assert.equal(confidence.innerText, "Confidence Index: Not available");
    assert.equal(decision.innerText, "PENDING");
    assert.equal(engine.innerText, "running");
    assert.match(summary.innerText, /Awaiting correlation results/);
    assert.equal(collectionStatus.innerText, "RUNNING");
    assert.equal(telegramStatus.innerText, "Loading");
    assert.equal(riskScore.innerText, "N/A");
    assert.equal(riskBadge.innerText, "ASSESSMENT RUNNING");
    assert.equal(riskNotice.innerText, "");
    assert.equal(riskNotice.style.display, "none");
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

test("dashboard preserves backend and AI risk disagreement for human review", () => {
    const score = fakeElement();
    const badge = fakeElement();
    const notice = fakeElement();
    const app = loadApp({
        "risk-score-num": score,
        "risk-badge": badge,
        "risk-fill": fakeElement(),
        "risk-consistency-notice": notice,
        "risk-analysis-text-section": fakeElement(),
        "risk-analysis-text-content": fakeElement()
    });

    app.renderInvestigationResults({
        status: "completed_with_warnings",
        platform_data: { platform: "twitter", username: "target" },
        risk_assessment: {
            level: "critical",
            score: 95,
            ai_risk_analysis: {
                success: true,
                analysis: "RISK LEVEL: LOW\nRISK SCORE: 20\nINDICATORS FOUND:\n- none"
            }
        }
    });

    assert.equal(score.innerText, "95%");
    assert.equal(badge.innerText, "CRITICAL RISK ASSESSMENT");
    assert.match(notice.innerText, /Human review required/);
    assert.match(notice.innerText, /CRITICAL \(95%\)/);
    assert.match(notice.innerText, /LOW \(20%\)/);
});

test("unknown backend risk remains unknown instead of becoming low at zero", () => {
    const score = fakeElement();
    const badge = fakeElement();
    const app = loadApp({
        "risk-score-num": score,
        "risk-badge": badge,
        "risk-fill": fakeElement(),
        "risk-consistency-notice": fakeElement()
    });

    app.renderInvestigationResults({
        status: "completed_with_warnings",
        platform_data: { platform: "instagram", username: "target" },
        risk_assessment: {
            level: "unknown",
            score: 0,
            basis: "insufficient_evidence"
        }
    });

    assert.equal(score.innerText, "N/A");
    assert.equal(badge.innerText, "RISK ASSESSMENT UNKNOWN");
    const consistency = app.getRiskConsistency({ level: "unknown", score: 0, basis: "insufficient_evidence" });
    assert.equal(consistency.backendLevel, "unknown");
    assert.equal(consistency.backendScore, null);
});

test("absent Telegram invite risk renders UNKNOWN and N/A in dashboard and report", () => {
    const score = fakeElement();
    const badge = fakeElement();
    const app = loadApp({
        "risk-score-num": score,
        "risk-badge": badge,
        "risk-fill": fakeElement(),
        "risk-consistency-notice": fakeElement()
    });
    const response = {
        status: "completed",
        platform_data: {
            platform: "telegram",
            success: true,
            target_type: "invite_link",
            invite_hash_redacted: true,
            full_name: "Private Group Preview"
        },
        cross_platform_matches: [],
        ai_correlation_result: null,
        risk_assessment: null
    };

    app.renderInvestigationResults(response);

    assert.equal(score.innerText, "N/A");
    assert.equal(badge.innerText, "RISK ASSESSMENT UNKNOWN");
    assert.deepEqual(
        JSON.parse(JSON.stringify(app.getRiskConsistency(null))),
        {
            backendLevel: "unknown",
            backendScore: null,
            ai: {
                available: false,
                level: null,
                score: null,
                analysis: ""
            },
            disagrees: false
        }
    );

    const html = app.renderOfficialReportTemplate(response, "CASE-TG-INVITE");
    assert.match(html, /Automated public-source assessment<\/td><td>UNKNOWN<\/td>/);
    assert.match(html, /automated public-source risk assessment is <strong>UNKNOWN<\/strong>/);
    assert.doesNotMatch(html, /LOW \(0%\)/);
});

test("official report separates collector evidence, URL candidates, dork failures, and risk signals", () => {
    const app = loadApp();
    const html = app.renderOfficialReportTemplate({
        status: "completed_with_warnings",
        platform_data: { platform: "instagram", username: "target", success: true, full_name: "Target" },
        scraped_data: {
            instagram: { platform: "instagram", username: "target", success: true, status: "completed", full_name: "Target" }
        },
        cross_platform_matches: [{
            platform: "twitter",
            exists: true,
            status_code: 200,
            url: "https://x.com/target"
        }],
        dorking_results: {
            status: "failed",
            provider: "serpapi",
            reason: "SerpAPI search failed.",
            queries_run: 1,
            queries: [{ category: "twitter", query: "site:x.com target" }],
            results: [],
            errors: [{ status: "429", message: "Quota exhausted", query: "site:x.com target" }]
        },
        risk_assessment: {
            level: "critical",
            score: 95,
            factors: ["cross_platform_presence"],
            ai_risk_analysis: { success: true, analysis: "RISK LEVEL: LOW\nRISK SCORE: 20\nRECOMMENDATIONS:\n- Ask ISP for subscriber records" }
        },
        ai_correlation_result: {
            summary: "Advisory model output.",
            confidence: 0.4,
            parsed: { decision: "POSSIBLY SAME", reasons: ["Username overlap"], next_steps: ["Request legal intercepts on active handles", "Ask ISP for subscriber records", "Compare profile photos"] }
        }
    }, "CASE-INTEGRITY");

    assert.match(html, /COLLECTOR CONFIRMED/);
    assert.match(html, /UNVERIFIED CANDIDATE/);
    assert.match(html, /URL reachability does not prove profile existence or ownership/);
    assert.match(html, /SerpAPI search failed/);
    assert.match(html, /Quota exhausted/);
    assert.match(html, /site:x.com target/);
    assert.match(html, /Human review required/);
    assert.match(html, /CRITICAL \(95%\)/);
    assert.match(html, /LOW \(20%\)/);
    assert.match(html, /KEY FINDINGS &amp; LIMITATIONS/);
    assert.doesNotMatch(html, /85%/);
    assert.doesNotMatch(html, /CRITICAL DISCOVERIES/);
    assert.doesNotMatch(html, /Request legal intercepts/);
    assert.doesNotMatch(html, /Ask ISP for subscriber records/i);
});

test("official report preserves candidate, collector-only, corroborated, and confirmed identity tiers", () => {
    const app = loadApp();
    const html = app.renderOfficialReportTemplate({
        status: "completed_with_warnings",
        platform_data: {
            platform: "instagram",
            username: "target",
            success: true,
            full_name: "Target Person"
        },
        scraped_data: {
            instagram: { platform: "instagram", username: "target", success: true, full_name: "Target Person" },
            linkedin: { platform: "linkedin", username: "target", success: true, full_name: "Target Person" },
            reddit: { platform: "reddit", username: "target", success: true, full_name: "Target Person" },
            github: { platform: "github", username: "target", success: true, full_name: "Target Person" }
        },
        cross_platform_matches: [
            { platform: "twitter", exists: true, status_code: 200, url: "https://x.com/target" },
            { platform: "linkedin", exists: true, status_code: 200, url: "https://linkedin.com/in/target" },
            { platform: "reddit", exists: true, status_code: 200, url: "https://reddit.com/user/target" },
            { platform: "github", exists: true, status_code: 200, url: "https://github.com/target" }
        ],
        ai_correlation_result: {
            candidate_platforms: ["twitter", "linkedin", "reddit", "github"],
            collector_confirmed_platforms: ["instagram", "linkedin", "reddit", "github"],
            matching_platforms: ["reddit", "github"],
            identity_corroborated_platforms: ["reddit"],
            identity_confirmed_platforms: ["github"]
        },
        risk_assessment: {
            level: "unknown",
            score: 0,
            basis: "insufficient_evidence"
        }
    }, "CASE-TIERS");

    assert.match(html, /<td>GITHUB<\/td>\s*<td>target<\/td>\s*<td class="finding-confirmed">IDENTITY CONFIRMED<\/td>/);
    assert.match(html, /<td>REDDIT<\/td>\s*<td>target<\/td>\s*<td class="finding-confirmed">IDENTITY CORROBORATED<\/td>/);
    assert.match(html, /<td>LINKEDIN<\/td>\s*<td>target<\/td>\s*<td class="finding-confirmed">COLLECTOR CONFIRMED<\/td>/);
    assert.match(html, /<td>TWITTER<\/td>\s*<td>target<\/td>\s*<td class="finding-candidate">UNVERIFIED CANDIDATE<\/td>/);
    assert.match(html, /1 identity-confirmed profile, 1 identity-corroborated profile, 2 collector-only profiles, 1 HTTP-only candidate/);
    assert.match(html, /Identity-confirmed public profile correlation/);
    assert.match(html, /Identity-corroborated public profile correlation/);
    assert.match(html, /Collector-only public profile payload/);
});

test("AI platform capsules distinguish candidates from stronger evidence", () => {
    const platforms = fakeElement();
    const app = loadApp({ "ai-associated-platforms": platforms });

    app.renderInvestigationResults({
        status: "completed",
        platform_data: { platform: "instagram", username: "target", success: true },
        scraped_data: {
            instagram: { platform: "instagram", username: "target", success: true, status: "completed" }
        },
        ai_correlation_result: {
            candidate_platforms: ["twitter"],
            collector_confirmed_platforms: ["instagram"],
            identity_corroborated_platforms: ["github"]
        }
    });

    const capsuleHTML = platforms.children.map(child => child.innerHTML).join("\n");
    assert.match(capsuleHTML, /UNVERIFIED CANDIDATE/);
    assert.match(capsuleHTML, /COLLECTOR CONFIRMED/);
    assert.match(capsuleHTML, /IDENTITY CORROBORATED/);
});
