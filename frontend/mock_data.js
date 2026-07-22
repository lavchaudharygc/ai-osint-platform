// ─── MOCK DATA & CONTROL HOOKS FOR FRONTEND TESTING (NO BACKEND REQUIRED) ─────────────────────
const MOCK_DATA = {
    investigation_id: "inv_mock_test_0001",
    status: "completed_with_warnings",
    platform_data: {
        success: true, platform: "instagram", username: "arkagrawall",
        full_name: "Ark Agrawal 🤸‍♂️",
        bio: "Coffee . Sunset . Music\n@arksscameraroll 😼",
        profile_pic_url: "https://i.pravatar.cc/150?u=arkagrawall",
        profile_pic_hd: "https://i.pravatar.cc/320?u=arkagrawall",
        follower_count: 142, following_count: 238, post_count: 0,
        is_verified: false, is_private: true, is_business: false,
        source: "mock_data", scraped_at: new Date().toISOString()
    },
    cross_platform_matches: [
        { platform: "instagram", url: "https://www.instagram.com/arkagrawall/", exists: true, status_code: 200 },
        { platform: "twitter", url: "https://x.com/arkagrawall", exists: true, status_code: 200 },
        { platform: "linkedin", url: "https://www.linkedin.com/in/arkagrawall/", exists: null, status_code: 999, status: "blocked_by_platform", note: "LinkedIn blocks direct HTTP checks (HTTP 999). Use the scraper for accurate results." },
        { platform: "telegram", url: "https://t.me/arkagrawall", exists: true, status_code: 200 },
        { platform: "github", url: "https://github.com/arkagrawall", exists: true, status_code: 200 },
        { platform: "pinterest", url: "https://www.pinterest.com/arkagrawall/", exists: true, status_code: 200 },
        { platform: "youtube", url: "https://www.youtube.com/@arkagrawall", exists: false, status_code: 404 },
        { platform: "reddit", url: "https://www.reddit.com/user/arkagrawall", exists: false, status_code: 404 },
        { platform: "facebook", url: "https://www.facebook.com/arkagrawall/", exists: false, status_code: 400 }
    ],
    ai_correlation_result: {
        confidence: 0.85, summary: "AI correlation completed using mock model.",
        matching_platforms: ["instagram", "twitter", "telegram", "github", "pinterest"],
        primary_platform: "instagram",
        ai_analysis: {
            success: true,
            parsed: {
                decision: "HIGHLY LIKELY MATCH", confidence: 85,
                reasons: [
                    "Same username 'arkagrawall' found on Instagram, Twitter, Telegram, GitHub, and Pinterest.",
                    "Twitter bio '19, chasing code & chaos' aligns with GitHub developer activity.",
                    "Instagram bio references secondary account @arksscameraroll — consistent multi-account pattern.",
                    "Telegram account exists with confirmed active handle @arkagrawall."
                ],
                next_steps: [
                    "Scrape Twitter tweets to get more content for AI analysis.",
                    "Investigate GitHub repositories for personal info or location clues.",
                    "Approve LinkedIn scraper to confirm LinkedIn profile."
                ]
            },
            model_used: "llama-3.3-70b-versatile (mock)"
        }
    },
    risk_assessment: {
        level: "medium", score: 75,
        factors: ["cross_platform_presence", "multiple_platforms_confirmed"],
        requires_human_review: true,
        ai_risk_analysis: {
            success: true,
            analysis: "RISK LEVEL: MEDIUM\nRISK SCORE: 75\n\nINDICATORS:\n- Subject present on 5+ platforms with consistent username.\n- Private Instagram account; limited public content.\n- Active GitHub with multiple repos (TripChain, NeuroDrishti, Swasthya-setu).\n- Telegram handle active.\n\nRECOMMENDATIONS:\n- Monitor for new platform registrations.\n- Investigate GitHub repositories for code containing personal data."
        }
    },
    internal_database_matches: { database_path: "./osint.db", by_username: [], by_phone: [], by_email: [], by_name: [], by_location: [], hitek_filtered: false },
    hashtag_analysis: { original_username: "arkagrawall", hashtags_analyzed: [], platforms_checked: ["twitter"], findings: {}, potential_connections: [] },
    dorking_results: {
        status: "completed", queries_run: 50, result_count: 6,
        results: [
            { query: 'site:github.com "arkagrawall"', platform: "GitHub", category: "developer_tech", title: "arkagrawall/TripChain", url: "https://github.com/arkagrawall/TripChain", domain: "github.com", snippet: "Contribute to arkagrawall/TripChain development by creating an account on GitHub.", position: 1, source: "google_apify" },
            { query: 'site:github.com "arkagrawall"', platform: "GitHub", category: "developer_tech", title: "arkagrawall/NeuroDrishti: GLANHE008", url: "https://github.com/arkagrawall/NeuroDrishti", domain: "github.com", snippet: "GLANHE008. Contribute to arkagrawall/NeuroDrishti — AI-based visual intelligence project.", position: 2, source: "google_apify" },
            { query: 'site:github.com "arkagrawall"', platform: "GitHub", category: "developer_tech", title: "arkagrawall/Swasthya-setu", url: "https://github.com/arkagrawall/Swasthya-setu", domain: "github.com", snippet: "A project which helps intern doctors. Healthcare management system.", position: 3, source: "google_apify" },
            { query: 'site:instagram.com "arkagrawall"', platform: "Instagram", category: "social_media", title: "From Classroom to Code — AI/ML Learning", url: "https://www.instagram.com/p/DXblaS4kySU/", domain: "www.instagram.com", snippet: "congratulations @arkagrawall — tagged in AI/ML university post 3 days ago.", position: 1, source: "google_apify" },
            { query: 'site:instagram.com "arkagrawall"', platform: "Instagram", category: "social_media", title: "Greenfields ka best Trio 🔥", url: "https://www.instagram.com/p/CP2N94bjtHM/", domain: "www.instagram.com", snippet: "arkagrawall.. September 2021 — Greenfields Public School, Dilshad Garden.", position: 2, source: "google_apify" },
            { query: 'site:pinterest.com "arkagrawall"', platform: "Pinterest", category: "social_media", title: "Ark agrawal (arkagrawall) – Profile", url: "https://in.pinterest.com/arkagrawall/", domain: "in.pinterest.com", snippet: "DUMPING MY TIME HERE. 101 Pins — Recreate When?, PINS that got me.", position: 1, source: "google_apify" }
        ],
        grouped_by_category: { developer_tech: [], social_media: [] }
    },
    instagram_posts: {
        configured: true, username: "arkagrawall", total: 2,
        posts: [
            {
                shortcode: "DXblaS4kySU", url: "https://www.instagram.com/p/DXblaS4kySU/",
                taken_at: 1782290000, media_type: "photo",
                caption: "🎓 Congratulations to @arkagrawall for completing the AI/ML certification! #aiml #coding #university",
                hashtags: ["aiml", "coding", "university"], mentions: ["arkagrawall"],
                like_count: 47, comment_count: 12, location: { name: "Greater Noida, India" }
            },
            {
                shortcode: "CP2N94bjtHM", url: "https://www.instagram.com/p/CP2N94bjtHM/",
                taken_at: 1622900000, media_type: "photo",
                caption: "Greenfields ka best Trio 🔥 Memories from school",
                hashtags: ["greenfields", "school", "memories"], mentions: [],
                like_count: 88, comment_count: 19, location: { name: "Greenfields Public School, Dilshad Garden" }
            }
        ],
        all_hashtags: ["aiml", "coding", "university", "greenfields", "school", "memories"],
        success: true, status: "completed"
    },
    scraped_data: {
        telegram: {
            exists: true, username: "arkagrawall", full_name: "Ark Agrawal",
            bio: "Coffee . Sunset . Music 🎧", entity_type: "user", subscriber_count: null,
            verification_signals: { is_verified: false, is_scam: false, is_fake: false },
            mtproto_status: { enabled: true, dependency_available: true, credentials_configured: true, session_file_present: true }
        },
        twitter: {
            success: true, platform: "twitter", username: "arkagrawall", full_name: "Ark agrawal",
            bio: "19, chasing code & chaos, save me!", follower_count: 89, following_count: 123, post_count: 34, joined_at: "2022-01-15T09:00:00Z", is_verified: false,
            tweets: [
                { id: "tw-1", text: "just shipped my first ML model 🎉 #machinelearning #python", created_at: "2026-07-10T12:30:00Z", like_count: 12, retweet_count: 3, reply_count: 2 },
                { id: "tw-2", text: "coffee + sunset = peak productivity ☕🌅", created_at: "2026-07-08T18:00:00Z", like_count: 34, retweet_count: 5, reply_count: 1 }
            ]
        },
        linkedin: {
            success: true, exists: true, platform: "linkedin", username: "arkagrawall",
            full_name: "Ark Agrawal", headline: "AI/ML Student", bio: "Building applied machine-learning projects.",
            connections_count: 218, location: "Greater Noida", experience: []
        },
        reddit: {
            success: true, exists: true, platform: "reddit", username: "arkagrawall",
            profile_metadata_note: "Reddit karma was not returned by the selected public actor.",
            posts: [{ id: "rd-1", title: "My first ML project", text: "A short project write-up.", subreddit: "MachineLearning", score: 21, comment_count: 7, created_at: "2026-07-09T08:15:00Z" }],
            comments: [{ id: "rd-c1", text: "Thanks for the feedback!", subreddit: "MachineLearning", score: 4, created_at: "2026-07-09T10:30:00Z" }]
        },
        facebook: {
            success: true, exists: true, platform: "facebook", username: "arkagrawall", full_name: "Ark Agrawal",
            posts: [{ id: "fb-1", text: "Public project update", created_at: "2026-07-07T11:00:00Z", like_count: 14, reaction_count: 18, comment_count: 3, share_count: 2 }]
        }
    },
    platform_content: {
        platform: "instagram",
        source: "apify_instagram_scraper",
        posts: [{ id: "primary-content-1", caption: "Normalized primary post content #aiml", created_at: "2026-07-11T12:00:00Z" }],
        replies: [],
        comments: []
    },
    intelligence_report: {
        report_metadata: { target_username: "arkagrawall", generated_at: new Date().toISOString() },
        executive_summary: {
            target_identification: { username: "arkagrawall", real_name: "Ark Agrawal", aliases: ["arks_cameraroll"] },
            profile_classification: { type: "tech_developer", professional_field: "Software / AI-ML", confidence: 0.85 },
            key_findings: { total_platforms_found: 9, associated_accounts: 2, organizations_linked: 2, locations_identified: ["Greater Noida", "Dilshad Garden, Delhi"], risk_level: "MEDIUM" },
            contact_information: {
                emails: ["arkagrawall@gmail.com", "arkagrawall@outlook.com", "ark.agrawal@gmail.com", "arkagrawall@hotmail.com", "arkagrawall@yahoo.com"],
                phone_numbers: [], social_profiles: ["https://github.com/arkagrawall", "https://in.pinterest.com/arkagrawall/", "https://t.me/arkagrawall"]
            }
        },
        intelligence_sections: {
            hashtag_intelligence: {
                statistics: { total_hashtags: 6, unique_hashtags: 6 },
                key_discoveries: {
                    personality_indicators: [
                        { trait: "Tech Enthusiast", category: "Professional", confidence: "HIGH" },
                        { trait: "Creative / Aesthetic", category: "Personal", confidence: "MEDIUM" },
                        { trait: "Academic Achiever", category: "Education", confidence: "HIGH" }
                    ],
                    locations_hinted: ["Greater Noida", "Dilshad Garden"]
                },
                categorized_hashtags: { technology: ["aiml", "coding"], personal: ["memories", "school"] }
            }
        }
    },
    reverse_lookup_results: {
        associated_accounts: [
            { username: "arksscameraroll", platform: "instagram", confidence: "95%", source: "bio_mention", evidence: "Directly mentioned in Instagram bio: '@arksscameraroll'" },
            { username: "memes_greenarians", platform: "instagram", confidence: "60%", source: "dorking", evidence: "Tagged arkagrawall in school reel (Sep 2021)" }
        ],
        keyword_profile: {
            username_variations: ["arks_agrawall", "ark_agrawall", "arkagrawal", "arksscameraroll"],
            interest_keywords: ["coffee", "sunset", "music", "photography", "coding"]
        },
        profile_type: {
            primary_type: "tech_creative", confidence: 0.85,
            description: "Young tech-oriented creative — active developer with aesthetic photography interests. Likely CS/AI student.",
            professional_field: "Software Development / AI-ML",
            interests: ["Photography", "Music", "Coding", "AI/ML", "Coffee", "Travel"]
        }
    },
    apify_social_results: {
        status: "completed_with_warnings",
        mode: "automatic_all_actors",
        identity_notice: "Same usernames across platforms remain unverified candidates until corroborated.",
        summary: { total: 4, completed: 3, empty: 0, failed: 1, not_configured: 0 },
        actors: {
            twitter_profile_and_replies: {
                success: true, status: "completed", actor_id: "mock/twitter-profile", tweets: []
            },
            twitter_tweet_search_v2: {
                success: true, status: "completed", actor_id: "mock/twitter-search",
                tweets: [{ id: "tw-search-1", text: "Actor-only Twitter search result", created_at: "2026-07-12T12:00:00Z", like_count: 9 }]
            },
            linkedin_posts_search: {
                success: true, status: "completed", actor_id: "mock/linkedin-posts",
                posts: [{ id: "li-post-1", text: "Actor-only LinkedIn public post", created_at: "2026-07-13T12:00:00Z", reaction_count: 11, comment_count: 2, repost_count: 1 }]
            },
            facebook_posts: {
                success: false, status: "provider_error", actor_id: "mock/facebook-posts",
                error: { code: "mock_provider_error", message: "Mock provider failure for UI verification" }, posts: []
            }
        },
        telegram: {
            success: true, exists: true, status: "found", platform: "telegram", username: "arkagrawall", full_name: "Ark Agrawal"
        }
    },
    timestamp: new Date().toISOString()
};

function injectMock() {
    currentInvestigationData = MOCK_DATA;
    currentCaseId = "MOCK-2026-0001";

    const workspaceEl = document.getElementById("results-workspace-grid");
    const emptyStateEl = document.getElementById("results-empty-state");
    if (workspaceEl) workspaceEl.style.display = "grid";
    if (emptyStateEl) emptyStateEl.style.display = "none";

    if (typeof renderInvestigationResults === "function") {
        renderInvestigationResults(MOCK_DATA);
    }
    if (typeof renderInstagramPosts === "function") {
        renderInstagramPosts(MOCK_DATA.instagram_posts);
    }
    console.log("[MOCK] Inject completed successfully.");
}

function testSkeletonState() {
    const workspaceEl = document.getElementById("results-workspace-grid");
    const emptyStateEl = document.getElementById("results-empty-state");
    if (workspaceEl) workspaceEl.style.display = "grid";
    if (emptyStateEl) emptyStateEl.style.display = "none";

    if (typeof renderSkeletonDossier === "function") {
        renderSkeletonDossier();
    }
}

// Override triggerInvestigation for Mock Mode (NO real API network calls)
window.triggerInvestigation = async function() {
    const usernameInput = document.getElementById("target-username");
    const username = (usernameInput && usernameInput.value.trim()) || "arkagrawall";
    const platform = document.getElementById("target-platform")?.value || "instagram";

    // 1. Instantly show workspace grid & hide empty standby state
    testSkeletonState();

    // 2. Show console loader with simulated logs
    const loader = document.getElementById("console-loader");
    const stream = document.getElementById("console-stream");
    if (stream) stream.innerHTML = "";
    if (loader) loader.style.display = "flex";

    function logLine(text, delay = 0) {
        return new Promise(resolve => {
            setTimeout(() => {
                if (stream) {
                    const line = document.createElement("div");
                    line.className = "console-line";
                    line.innerText = `[${new Date().toLocaleTimeString()}] ${text}`;
                    stream.appendChild(line);
                    stream.scrollTop = stream.scrollHeight;
                }
                resolve();
            }, delay);
        });
    }

    await logLine(`[SYS] (MOCK TEST MODE) ENGAGE TARGET: ${username}`, 50);
    await logLine(`[NET] SIMULATING INTERCEPT HOOK ON PLATFORM: ${platform.toUpperCase()}`, 100);
    await logLine(`[SYS] RENDERING PULSING SKELETON LOADERS FOR COMPONENT TESTING...`, 150);

    // 3. After 1.2s simulation delay, render full mock data
    setTimeout(() => {
        if (loader) loader.style.display = "none";
        injectMock();
        logLine(`[SYS] MOCK DATASET RENDERED SUCCESSFULLY.`, 0);
    }, 1200);
};

document.addEventListener("DOMContentLoaded", () => {
    setTimeout(injectMock, 300);
});
