(function attachOSINTDataMappers(root, factory) {
    const api = factory();
    if (typeof module !== "undefined" && module.exports) {
        module.exports = api;
    }
    if (root) {
        root.OSINTDataMappers = api;
    }
})(typeof globalThis !== "undefined" ? globalThis : this, function createOSINTDataMappers() {
    const isRecord = value => Boolean(value) && typeof value === "object" && !Array.isArray(value);
    const asList = value => Array.isArray(value) ? value : [];
    const ACTOR_PLATFORM_MAP = {
        instagram_profile: "instagram",
        instagram_posts: "instagram",
        twitter_profile_and_replies: "twitter",
        twitter_tweet_search_v2: "twitter",
        reddit: "reddit",
        linkedin_profiles: "linkedin",
        linkedin_posts_search: "linkedin",
        facebook_pages: "facebook",
        facebook_posts: "facebook"
    };
    const NON_EVIDENCE_STATUSES = new Set([
        "not_configured", "empty_dataset", "skipped", "disabled",
        "provider_error", "orchestration_error", "error", "failed",
        "timeout", "timed-out", "aborted"
    ]);

    function firstDefined(...values) {
        return values.find(value => value !== undefined && value !== null && value !== "");
    }

    function firstList(...values) {
        return values.find(value => Array.isArray(value) && value.length > 0) || [];
    }

    function itemIdentity(item) {
        if (!isRecord(item)) return String(item);
        const stableId = firstDefined(
            item.id,
            item.shortcode,
            item.url,
            item.twitter_url,
            item.facebook_url,
            item.permalink
        );
        if (stableId !== undefined) return String(stableId);
        return [
            firstDefined(item.created_at, item.created_utc, item.taken_at, ""),
            firstDefined(item.text, item.full_text, item.caption, item.title, item.body, item.selftext, "")
        ].join("|");
    }

    function mergeUniqueItems(...collections) {
        const seen = new Set();
        const merged = [];
        collections.flatMap(asList).forEach(item => {
            const identity = itemIdentity(item);
            if (seen.has(identity)) return;
            seen.add(identity);
            merged.push(item);
        });
        return merged;
    }

    function confidencePercent(aiResult) {
        if (!isRecord(aiResult)) return null;
        const parsed = isRecord(aiResult.ai_analysis) && isRecord(aiResult.ai_analysis.parsed)
            ? aiResult.ai_analysis.parsed
            : (isRecord(aiResult.parsed) ? aiResult.parsed : null);
        const rawValue = firstDefined(parsed && parsed.confidence, aiResult.confidence);
        if (rawValue === undefined) return null;
        const numeric = Number(rawValue);
        if (!Number.isFinite(numeric)) return null;
        const percent = numeric >= 0 && numeric <= 1 ? numeric * 100 : numeric;
        return Math.max(0, Math.min(100, Math.round(percent)));
    }

    function telegramDataScore(payload) {
        if (!isRecord(payload) || Object.keys(payload).length === 0) return -1;
        let score = 0;
        if (payload.target_type === "invite_link" || payload.invite_hash_redacted) score += 8;
        if (payload.username) score += 6;
        if (payload.full_name || payload.display_name) score += 4;
        if (payload.bio || payload.description) score += 2;
        if (payload.exists === true) score += 3;
        if (payload.member_count !== undefined || payload.subscriber_count !== undefined) score += 2;
        if (payload.mtproto_status || payload.intelligence_analysis) score += 1;
        if (payload.exists === false) score += 0.5;
        return score;
    }

    function resolveTelegramData(response) {
        if (!isRecord(response)) return {};
        const scraped = response.scraped_data && response.scraped_data.telegram;
        const primary = response.platform_data;
        const envelopeTelegram = response.apify_social_results && response.apify_social_results.telegram;
        const candidates = [
            isRecord(scraped) ? scraped : null,
            isRecord(primary) && String(primary.platform || "").toLowerCase() === "telegram" ? primary : null,
            isRecord(envelopeTelegram) ? envelopeTelegram : null
        ].filter(Boolean);
        if (candidates.length === 0) return {};

        return candidates.reduce((best, candidate) => (
            telegramDataScore(candidate) > telegramDataScore(best) ? candidate : best
        ));
    }

    function actorSourcesFor(response, platform) {
        const actors = response && response.apify_social_results && response.apify_social_results.actors;
        const actorMap = isRecord(actors) ? actors : {};
        const normalizedPlatform = String(platform || "").toLowerCase();
        if (normalizedPlatform === "instagram") {
            return [actorMap.instagram_profile, actorMap.instagram_posts];
        }
        if (normalizedPlatform === "twitter") {
            return [actorMap.twitter_profile_and_replies, actorMap.twitter_tweet_search_v2];
        }
        if (normalizedPlatform === "reddit") return [actorMap.reddit];
        if (normalizedPlatform === "linkedin") {
            return [actorMap.linkedin_profiles, actorMap.linkedin_posts_search];
        }
        if (normalizedPlatform === "facebook") {
            return [actorMap.facebook_pages, actorMap.facebook_posts];
        }
        if (normalizedPlatform === "telegram") {
            return [response && response.apify_social_results && response.apify_social_results.telegram];
        }
        return [];
    }

    function nestedProfile(payload, platform) {
        if (!isRecord(payload)) return {};
        const normalizedPlatform = String(platform || "").toLowerCase();
        if (normalizedPlatform === "linkedin") {
            return firstList(payload.profiles)[0] || payload.profile || {};
        }
        if (normalizedPlatform === "facebook") {
            return firstList(payload.pages)[0] || payload.page || payload.profile || {};
        }
        return payload.profile || {};
    }

    function actorOutcome(payload) {
        if (!isRecord(payload)) return "unknown";
        const status = String(payload.status || "").toLowerCase();
        if (status === "not_configured" || payload.configured === false) return "not_configured";
        if (["empty_dataset", "skipped", "disabled"].includes(status)) return "empty";
        if (["provider_error", "orchestration_error", "error", "failed", "timeout", "timed-out", "aborted"].includes(status)) {
            return "failed";
        }
        if (payload.error && !["completed", "found", "succeeded"].includes(status)) return "failed";
        if (payload.success === true || ["completed", "found", "succeeded"].includes(status)) return "completed";
        return "unknown";
    }

    function domainPayload(payload) {
        if (!isRecord(payload)) return {};
        const {
            success, status, error, configured, run, runs, raw_data, apify_error,
            ...domain
        } = payload;
        return domain;
    }

    function getRenderablePlatformData(response, platform) {
        if (!isRecord(response)) return null;
        const normalizedPlatform = String(platform || "").toLowerCase();
        if (!normalizedPlatform) return null;

        const actorSources = actorSourcesFor(response, normalizedPlatform).filter(isRecord);
        const scraped = isRecord(response.scraped_data) && isRecord(response.scraped_data[normalizedPlatform])
            ? response.scraped_data[normalizedPlatform]
            : {};
        const primary = isRecord(response.platform_data)
            && String(response.platform_data.platform || "").toLowerCase() === normalizedPlatform
            ? response.platform_data
            : {};
        const primaryContent = isRecord(response.platform_content)
            && String(response.platform_content.platform || "").toLowerCase() === normalizedPlatform
            ? response.platform_content
            : {};

        let merged = { platform: normalizedPlatform };
        const orderedActorSources = [...actorSources].sort((left, right) => {
            const rank = source => actorOutcome(source) === "completed" ? 2 : (actorOutcome(source) === "unknown" ? 1 : 0);
            return rank(left) - rank(right);
        });
        orderedActorSources.forEach(source => {
            merged = {
                ...merged,
                ...domainPayload(nestedProfile(source, normalizedPlatform)),
                ...domainPayload(source)
            };
        });
        merged = {
            ...merged,
            ...domainPayload(nestedProfile(scraped, normalizedPlatform)),
            ...domainPayload(scraped)
        };
        merged = {
            ...merged,
            ...domainPayload(nestedProfile(primary, normalizedPlatform)),
            ...domainPayload(primary)
        };

        const actorPosts = actorSources.flatMap(source => firstList(source.posts, source.recent_posts));
        const actorTweets = actorSources.flatMap(source => firstList(source.tweets, source.recent_posts));
        const actorReplies = actorSources.flatMap(source => asList(source.replies));
        const actorComments = actorSources.flatMap(source => asList(source.comments));

        const primaryPosts = firstList(primaryContent.posts, primaryContent.tweets);
        const primaryReplies = asList(primaryContent.replies);
        const primaryComments = asList(primaryContent.comments);

        if (normalizedPlatform === "twitter") {
            merged.tweets = mergeUniqueItems(
                merged.tweets,
                merged.recent_posts,
                actorTweets,
                primaryPosts
            );
            merged.replies = mergeUniqueItems(merged.replies, actorReplies, primaryReplies);
            merged.recent_posts = merged.tweets;
        } else {
            let extraPosts = actorPosts;
            if (normalizedPlatform === "instagram" && isRecord(response.instagram_posts)) {
                extraPosts = extraPosts.concat(firstList(response.instagram_posts.posts, response.instagram_posts.reels));
                merged.all_hashtags = firstList(
                    response.instagram_posts.all_hashtags,
                    merged.all_hashtags
                );
            }
            merged.posts = mergeUniqueItems(merged.posts, merged.recent_posts, extraPosts, primaryPosts);
            merged.recent_posts = merged.posts;
            merged.replies = mergeUniqueItems(merged.replies, actorReplies, primaryReplies);
            merged.comments = mergeUniqueItems(merged.comments, actorComments, primaryComments);
        }

        const operationalSources = [
            ...actorSources,
            ...(Object.keys(scraped).length > 0 ? [scraped] : []),
            ...(Object.keys(primary).length > 0 ? [primary] : [])
        ];
        const positiveSource = [...operationalSources].reverse().find(hasPositivePlatformEvidence);
        const hasContentEvidence = hasPositivePlatformEvidence(primaryContent);
        if (positiveSource || hasContentEvidence) {
            merged.success = true;
            merged.status = firstDefined(positiveSource && positiveSource.status, "completed");
            delete merged.error;
        } else {
            const preferredSource = [primary, scraped, ...actorSources]
                .find(source => isRecord(source) && Object.keys(source).length > 0);
            if (preferredSource) {
                if (preferredSource.success !== undefined) merged.success = preferredSource.success;
                if (preferredSource.status !== undefined) merged.status = preferredSource.status;
                if (preferredSource.error !== undefined) merged.error = preferredSource.error;
                if (preferredSource.exists !== undefined) merged.exists = preferredSource.exists;
            }
        }

        const hasSource = actorSources.length > 0
            || Object.keys(scraped).length > 0
            || Object.keys(primary).length > 0
            || Object.keys(primaryContent).length > 0;
        return hasSource ? merged : null;
    }

    function hasPositivePlatformEvidence(payload) {
        if (!isRecord(payload)) return false;
        const status = String(payload.status || "").toLowerCase();
        if (payload.exists === false || NON_EVIDENCE_STATUSES.has(status)) return false;
        if (payload.exists === true) return true;
        const hasContent = ["posts", "tweets", "replies", "comments", "recent_posts", "profiles", "pages"].some(
            key => Array.isArray(payload[key]) && payload[key].length > 0
        );
        if (hasContent) return true;

        const hasIdentityMetadata = [
            "full_name", "display_name", "name", "bio", "description",
            "profile_pic_url", "profile_pic_hd", "profile_url",
            "follower_count", "member_count", "subscriber_count"
        ].some(key => payload[key] !== undefined && payload[key] !== null && payload[key] !== "");
        return payload.success === true && hasIdentityMetadata;
    }

    function profileEvidenceSourcesFor(response, platform) {
        if (!isRecord(response)) return [];
        const normalizedPlatform = String(platform || "").toLowerCase();
        const actors = response.apify_social_results && response.apify_social_results.actors;
        const actorMap = isRecord(actors) ? actors : {};
        const profileActors = {
            instagram: [actorMap.instagram_profile],
            twitter: [actorMap.twitter_profile_and_replies],
            reddit: [actorMap.reddit],
            linkedin: [actorMap.linkedin_profiles],
            facebook: [actorMap.facebook_pages],
            telegram: [response.apify_social_results && response.apify_social_results.telegram]
        };
        const sources = [...(profileActors[normalizedPlatform] || [])];
        if (isRecord(response.scraped_data) && isRecord(response.scraped_data[normalizedPlatform])) {
            sources.push(response.scraped_data[normalizedPlatform]);
        }
        if (isRecord(response.platform_data)
            && String(response.platform_data.platform || "").toLowerCase() === normalizedPlatform) {
            sources.push(response.platform_data);
        }
        return sources.filter(isRecord);
    }

    function hasConfirmedProfileEvidence(response, platform) {
        return profileEvidenceSourcesFor(response, platform).some(hasPositivePlatformEvidence);
    }

    function buildPlatformEntries(response) {
        if (!isRecord(response)) return [];
        const entries = [];
        const byPlatform = new Map();

        asList(response.cross_platform_matches).forEach(match => {
            if (!isRecord(match) || !match.platform) return;
            const key = String(match.platform).toLowerCase();
            const entry = { ...match, platform: key };
            entries.push(entry);
            byPlatform.set(key, entry);
        });

        const candidates = new Set();
        if (isRecord(response.scraped_data)) {
            Object.keys(response.scraped_data).forEach(platform => candidates.add(platform.toLowerCase()));
        }
        if (isRecord(response.platform_data) && response.platform_data.platform) {
            candidates.add(String(response.platform_data.platform).toLowerCase());
        }
        if (isRecord(response.platform_content) && response.platform_content.platform) {
            candidates.add(String(response.platform_content.platform).toLowerCase());
        }
        const actors = response.apify_social_results && response.apify_social_results.actors;
        if (isRecord(actors)) {
            Object.entries(actors).forEach(([actorKey, actor]) => {
                const actorPlatform = isRecord(actor) && actor.platform
                    ? String(actor.platform).toLowerCase()
                    : ACTOR_PLATFORM_MAP[actorKey];
                if (actorPlatform) candidates.add(actorPlatform);
            });
        }
        if (isRecord(response.apify_social_results) && isRecord(response.apify_social_results.telegram)) {
            candidates.add("telegram");
        }

        candidates.forEach(platform => {
            const details = getRenderablePlatformData(response, platform);
            const profileConfirmed = hasConfirmedProfileEvidence(response, platform);
            let entry = byPlatform.get(platform);
            if (!entry) {
                const detailStatus = String((details && details.status) || "").toLowerCase();
                const hasDefinitiveAbsence = details
                    && details.exists === false
                    && !details.error
                    && !NON_EVIDENCE_STATUSES.has(detailStatus);
                entry = {
                    platform,
                    exists: profileConfirmed
                        ? true
                        : (hasDefinitiveAbsence ? false : null),
                    url: details && firstDefined(details.profile_url, details.url)
                };
                entries.push(entry);
                byPlatform.set(platform, entry);
            }
            if (profileConfirmed) {
                entry.exists = true;
                entry.scraper_confirmed = true;
            }
            if (!entry.url && details) {
                entry.url = firstDefined(details.profile_url, details.url);
            }
        });

        return entries;
    }

    function actorItemCount(actor) {
        if (!isRecord(actor)) return 0;
        const keys = ["posts", "tweets", "replies", "comments", "pages", "profiles", "companies", "reels"];
        const arrayTotal = keys.reduce((total, key) => total + asList(actor[key]).length, 0);
        if (arrayTotal > 0) return arrayTotal;
        const reported = Number(firstDefined(actor.total, actor.result_count, 0));
        return Number.isFinite(reported) ? reported : 0;
    }

    return {
        actorItemCount,
        actorOutcome,
        asList,
        buildPlatformEntries,
        confidencePercent,
        firstDefined,
        firstList,
        getRenderablePlatformData,
        hasConfirmedProfileEvidence,
        hasPositivePlatformEvidence,
        mergeUniqueItems,
        resolveTelegramData
    };
});
