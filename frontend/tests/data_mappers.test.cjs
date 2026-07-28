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

test("actor item counts treat YouTube video aliases as one collection", () => {
    const videos = [
        { video_id: "video-1" },
        { video_id: "video-2" }
    ];

    assert.equal(
        mappers.actorItemCount({ recent_videos: videos, videos }),
        2
    );
    assert.equal(
        mappers.actorItemCount({ recent_videos: [], videos }),
        2
    );
    assert.equal(
        mappers.actorItemCount({
            posts: [{ id: "post-1" }],
            comments: [{ id: "comment-1" }],
            repositories: [{ id: "repo-1" }]
        }),
        3
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

test("provider-neutral social results take precedence over the legacy actor envelope", () => {
    const response = {
        provider_results: {
            status: "completed",
            routing: { twitter: "apify_x_scraper" },
            social: {
                twitter: {
                    success: true,
                    status: "completed",
                    platform: "twitter",
                    username: "target",
                    full_name: "Neutral Twitter Profile",
                    tweets: [{ id: "neutral-tweet", text: "neutral source" }]
                }
            }
        },
        apify_social_results: {
            status: "completed_with_warnings",
            actors: {
                twitter_profile_and_replies: {
                    success: true,
                    status: "completed",
                    platform: "twitter",
                    full_name: "Stale Legacy Profile",
                    tweets: [{ id: "legacy-tweet", text: "legacy source" }]
                }
            }
        }
    };

    const twitter = mappers.getRenderablePlatformData(response, "twitter");
    assert.equal(twitter.full_name, "Neutral Twitter Profile");
    assert.deepEqual(twitter.tweets.map(item => item.id), ["neutral-tweet"]);

    const collection = mappers.resolveSocialCollection(response);
    assert.equal(collection.source, "provider_results");
    assert.equal(collection.status, "completed");
    assert.deepEqual(collection.entries.map(([key]) => key), ["twitter"]);
    assert.deepEqual(collection.routing, { twitter: "apify_x_scraper" });
});

test("provider-neutral nested social payloads render TikTok and split combined collectors", () => {
    const response = {
        provider_results: {
            social: {
                instagram: {
                    profile: {
                        success: true,
                        status: "completed",
                        platform: "instagram",
                        username: "target",
                        full_name: "Instagram Profile"
                    },
                    posts: {
                        success: true,
                        status: "completed",
                        posts: [{ id: "ig-neutral", text: "Instagram post" }]
                    }
                },
                tiktok: {
                    success: true,
                    status: "completed",
                    platform: "tiktok",
                    username: "target",
                    full_name: "TikTok Profile",
                    posts: [{ id: "tt-neutral", text: "TikTok video" }]
                }
            }
        }
    };

    const instagram = mappers.getRenderablePlatformData(response, "instagram");
    const tiktok = mappers.getRenderablePlatformData(response, "tiktok");
    assert.equal(instagram.full_name, "Instagram Profile");
    assert.equal(instagram.posts[0].id, "ig-neutral");
    assert.equal(tiktok.full_name, "TikTok Profile");
    assert.equal(tiktok.posts[0].id, "tt-neutral");
    assert.equal(mappers.buildPlatformEntries(response).find(entry => entry.platform === "tiktok").exists, true);
    assert.deepEqual(
        mappers.resolveSocialCollection(response).entries.map(([key]) => key),
        ["instagram_profile", "instagram_posts", "tiktok"]
    );
});

test("GitHub specialized provider results create a renderable confirmed platform entry", () => {
    const response = {
        provider_results: {
            specialized: {
                github: {
                    success: true,
                    status: "completed",
                    username: "octocat",
                    profile: {
                        username: "octocat",
                        full_name: "The Octocat",
                        avatar_url: "https://avatars.example/octocat.png",
                        public_repos: 1
                    },
                    repositories: [{ id: 1, name: "hello-world", stars: 80 }],
                    organizations: [{ id: 2, username: "github" }],
                    contributions: {
                        total_contributions: 148,
                        commit_contributions: 120
                    }
                }
            }
        }
    };

    const github = mappers.getRenderablePlatformData(response, "github");
    const [entry] = mappers.buildPlatformEntries(response);
    assert.equal(github.full_name, "The Octocat");
    assert.equal(github.repositories[0].name, "hello-world");
    assert.equal(github.organizations[0].username, "github");
    assert.equal(github.contributions.total_contributions, 148);
    assert.equal(entry.platform, "github");
    assert.equal(entry.exists, true);
    assert.equal(entry.scraper_confirmed, true);
});

test("provider-neutral YouTube and Reddit results expose channel and OAuth-plus-activity data", () => {
    const response = {
        provider_results: {
            social: {
                reddit: {
                    success: true,
                    status: "completed",
                    exists: true,
                    platform: "reddit",
                    username: "canonical_redditor",
                    bio: "OAuth profile biography",
                    total_karma: 15123,
                    account_age_days: 3650,
                    profile: {
                        avatar_url: "https://styles.redditmedia.com/avatar.png"
                    },
                    posts: [{ id: "reddit-post", title: "Public submission" }]
                },
                youtube: {
                    success: true,
                    status: "completed",
                    exists: true,
                    platform: "youtube",
                    username: "canonicalchannel",
                    full_name: "Canonical YouTube Channel",
                    subscriber_count: 1234,
                    channel: {
                        channel_id: "UC1234567890123456789012",
                        published_at: "2018-05-04T10:00:00Z"
                    },
                    recent_videos: [{
                        video_id: "video-1",
                        url: "https://www.youtube.com/watch?v=video-1",
                        title: "Recent video"
                    }]
                }
            }
        }
    };

    const reddit = mappers.getRenderablePlatformData(response, "reddit");
    const youtube = mappers.getRenderablePlatformData(response, "youtube");
    const entries = mappers.buildPlatformEntries(response);

    assert.equal(reddit.bio, "OAuth profile biography");
    assert.equal(reddit.total_karma, 15123);
    assert.equal(reddit.avatar_url, "https://styles.redditmedia.com/avatar.png");
    assert.equal(reddit.posts[0].id, "reddit-post");
    assert.equal(youtube.full_name, "Canonical YouTube Channel");
    assert.equal(youtube.channel_id, "UC1234567890123456789012");
    assert.equal(youtube.recent_videos[0].title, "Recent video");
    assert.equal(youtube.posts[0].video_id, "video-1");
    assert.equal(entries.find(entry => entry.platform === "reddit").scraper_confirmed, true);
    assert.equal(entries.find(entry => entry.platform === "youtube").scraper_confirmed, true);
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
