const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const mappers = require("../data_mappers.js");

test("AI confidence is evidence-based and preserves zero", () => {
    assert.equal(mappers.confidencePercent(null), null);
    assert.equal(mappers.confidencePercent({}), null);
    assert.equal(mappers.confidencePercent({ confidence: 0 }), 0);
    assert.equal(mappers.confidencePercent({ confidence: 0.42 }), 42);
    assert.equal(
        mappers.confidencePercent({ ai_analysis: { parsed: { confidence: 87 } } }),
        87
    );
});

test("Telegram invite preview falls back to canonical platform_data", () => {
    const invitePreview = {
        platform: "telegram",
        target_type: "invite_link",
        invite_hash_redacted: true,
        full_name: "Private group preview"
    };
    const response = {
        scraped_data: null,
        platform_data: invitePreview,
        apify_social_results: { telegram: { full_name: "lower-priority copy" } }
    };

    assert.equal(mappers.resolveTelegramData(response), invitePreview);
    const entries = mappers.buildPlatformEntries(response);
    assert.equal(entries.length, 1);
    assert.equal(entries[0].platform, "telegram");
});

test("renderable data merges scraped, normalized, and actor Twitter results", () => {
    const response = {
        platform_data: { platform: "twitter", username: "target", success: true },
        scraped_data: {
            twitter: {
                platform: "twitter",
                username: "target",
                tweets: [{ id: "profile-tweet", text: "profile timeline" }]
            }
        },
        platform_content: {
            platform: "twitter",
            posts: [{ id: "primary-post", text: "primary normalized content" }],
            replies: [{ id: "primary-reply", text: "primary reply" }],
            comments: []
        },
        apify_social_results: {
            actors: {
                twitter_tweet_search_v2: {
                    status: "completed",
                    tweets: [{ id: "search-tweet", text: "actor-only search result" }]
                }
            }
        }
    };

    const twitter = mappers.getRenderablePlatformData(response, "twitter");
    assert.deepEqual(
        twitter.tweets.map(item => item.id).sort(),
        ["primary-post", "profile-tweet", "search-tweet"].sort()
    );
    assert.equal(twitter.replies[0].id, "primary-reply");
});

test("a failed auxiliary actor does not poison a successful sibling profile", () => {
    const response = {
        apify_social_results: {
            actors: {
                linkedin_profiles: {
                    success: true,
                    status: "completed",
                    profiles: [{ full_name: "Valid Profile", bio: "Public professional bio" }]
                },
                linkedin_posts_search: {
                    success: false,
                    status: "provider_error",
                    error: { message: "Auxiliary post search failed" },
                    posts: []
                }
            }
        }
    };

    const linkedin = mappers.getRenderablePlatformData(response, "linkedin");
    assert.equal(linkedin.full_name, "Valid Profile");
    assert.equal(linkedin.success, true);
    assert.equal(linkedin.status, "completed");
    assert.equal(linkedin.error, undefined);
});

test("actor-only profile evidence creates a confirmed dossier entry", () => {
    const response = {
        apify_social_results: {
            actors: {
                twitter_profile_and_replies: {
                    success: true,
                    status: "completed",
                    platform: "twitter",
                    full_name: "Actor Profile",
                    tweets: [{ id: "actor-profile-tweet", text: "Profile timeline" }]
                }
            }
        }
    };

    const [entry] = mappers.buildPlatformEntries(response);
    assert.equal(entry.platform, "twitter");
    assert.equal(entry.exists, true);
    assert.equal(entry.scraper_confirmed, true);
});

test("keyword-search content cannot turn an absent profile into a found profile", () => {
    const response = {
        cross_platform_matches: [{ platform: "linkedin", exists: false, status_code: 404 }],
        apify_social_results: {
            actors: {
                linkedin_profiles: {
                    success: true,
                    status: "empty_dataset",
                    platform: "linkedin",
                    profiles: []
                },
                linkedin_posts_search: {
                    success: true,
                    status: "completed",
                    platform: "linkedin",
                    posts: [{ id: "mention-1", text: "A keyword mention, not profile proof" }]
                }
            }
        }
    };

    const [entry] = mappers.buildPlatformEntries(response);
    const linkedin = mappers.getRenderablePlatformData(response, "linkedin");
    assert.equal(entry.exists, false);
    assert.equal(entry.scraper_confirmed, undefined);
    assert.equal(linkedin.posts[0].id, "mention-1");
});

test("empty and unconfigured executions are not positive identity evidence", () => {
    assert.equal(
        mappers.hasPositivePlatformEvidence({ success: true, status: "empty_dataset", posts: [] }),
        false
    );
    assert.equal(
        mappers.hasPositivePlatformEvidence({ success: true, status: "not_configured", full_name: "Echoed input" }),
        false
    );
    const response = {
        cross_platform_matches: [{ platform: "linkedin", exists: false, status_code: 404 }],
        apify_social_results: {
            actors: {
                linkedin_profiles: {
                    success: false,
                    exists: null,
                    status: "empty_dataset",
                    platform: "linkedin",
                    profiles: [{ provider_status: "NOT_FOUND", input: "target" }]
                }
            }
        }
    };
    const [entry] = mappers.buildPlatformEntries(response);
    assert.equal(entry.exists, false);
    assert.equal(entry.scraper_confirmed, undefined);
});

test("platform-content-only data is renderable but remains identity-inconclusive", () => {
    const response = {
        platform_content: {
            platform: "reddit",
            posts: [{ id: "normalized-only", text: "Normalized content" }],
            replies: [],
            comments: []
        }
    };

    const [entry] = mappers.buildPlatformEntries(response);
    assert.equal(entry.platform, "reddit");
    assert.equal(entry.exists, null);
    assert.equal(mappers.getRenderablePlatformData(response, "reddit").posts[0].id, "normalized-only");
});

test("renderable LinkedIn data includes actor-only public posts", () => {
    const response = {
        platform_data: { platform: "linkedin", username: "target", success: true },
        scraped_data: { linkedin: { platform: "linkedin", full_name: "Target Person" } },
        apify_social_results: {
            actors: {
                linkedin_posts_search: {
                    status: "completed",
                    posts: [{ id: "li-1", text: "actor-only LinkedIn post" }]
                }
            }
        }
    };

    const linkedin = mappers.getRenderablePlatformData(response, "linkedin");
    assert.equal(linkedin.full_name, "Target Person");
    assert.equal(linkedin.posts[0].id, "li-1");
});

test("successful scraper evidence overrides a failed lightweight URL probe", () => {
    const response = {
        platform_data: { platform: "facebook", username: "target" },
        cross_platform_matches: [{ platform: "facebook", exists: false, status_code: 404 }],
        scraped_data: {
            facebook: {
                platform: "facebook",
                success: true,
                exists: true,
                posts: [{ id: "fb-1", text: "confirmed public post" }]
            }
        }
    };

    const [entry] = mappers.buildPlatformEntries(response);
    assert.equal(entry.exists, true);
    assert.equal(entry.scraper_confirmed, true);
});

test("a failed scraped Telegram placeholder cannot mask a richer invite preview", () => {
    const invitePreview = {
        success: true,
        exists: true,
        platform: "telegram",
        target_type: "invite_link",
        invite_hash_redacted: true,
        full_name: "Private group preview",
        member_count: 0
    };
    const response = {
        scraped_data: {
            telegram: {
                success: false,
                status: "orchestration_error",
                error: "collector unavailable"
            }
        },
        platform_data: invitePreview
    };

    assert.equal(mappers.resolveTelegramData(response), invitePreview);
});

test("production frontend contains no hard-coded 65 percent AI fallback", () => {
    const frontendRoot = path.resolve(__dirname, "..");
    for (const filename of ["app.js", "index.html", "mock_test.html"]) {
        const source = fs.readFileSync(path.join(frontendRoot, filename), "utf8");
        assert.doesNotMatch(source, /Confidence(?:\s+Index)?:\s*65%/i);
        assert.doesNotMatch(source, /ai\.confidence\s*\|\|\s*0\.65/);
        assert.doesNotMatch(source, /parsedAI\.confidence\s*\|\|\s*65/);
        assert.doesNotMatch(source, /confidence\s*:\s*0\.65/);
    }
});
