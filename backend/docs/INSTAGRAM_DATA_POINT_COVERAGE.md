# Instagram Data Point Coverage

Source catalog: `docs/data_points_catalog-Instagram.csv` from the public OSINT repository.

## Implemented in `backend/services/instagram_service.py`

| Priority | Catalog data point | Backend field(s) |
| --- | --- | --- |
| P0 | Username | `username` |
| P0 | Full Name / Display Name | `full_name` |
| P0 | Bio Text | `bio` |
| P0 | Profile Picture (URL + Download) | `profile_pic_url`, `profile_pic_hd`, `profile_pic_hash` |
| P0 | Followers Count | `follower_count`, `followers` |
| P0 | Following Count | `following_count`, `following` |
| P0 | Post Count | `post_count`, `posts_count` |
| P0 | External URL in Bio | `external_url`, `external_urls` |
| P0 | Account Verified Status | `is_verified` |
| P1 | Business Category | `business_category` |
| P0 | Last 12 Posts — Captions | `recent_posts[].caption`, `last_12_posts_captions` |
| P0 | Post Hashtags | `recent_posts[].hashtags`, `post_hashtags`, `all_hashtags_used` |
| P1 | Post Timestamps | `recent_posts[].timestamp`, `post_timestamps` |
| P1 | Post Location Tags | `recent_posts[].location`, `post_location_tags` |
| P1 | Tagged Users in Posts | `recent_posts[].tagged_users`, `tagged_users_in_posts`, `all_tagged_users` |
| P1 | Mentioned Users in Captions | `recent_posts[].mentioned_users`, `mentioned_users_in_captions`, `all_mentioned_users` |
| P0 | Profile Picture Hash | `profile_pic_hash` with `profile_pic_hash_method` |
| P0 | Account Type | `account_type`, `is_business` |
| P0 | Contact Email | `contact_email`, `professional_email_in_bio` |
| P0 | Contact Phone | `contact_phone` |
| P1 | Contact Address | `contact_address` when provider exposes it |
| P1 | Pinned Posts | `pinned_posts`, `recent_posts[].is_pinned` when exposed |
| P1 | Collab Posts | `collab_posts`, `recent_posts[].coauthors` when exposed |
| P0 | LinkedIn Profile Link in Bio | `linkedin_profile_link_in_bio` |
| P0 | Professional Email in Bio | `professional_email_in_bio` |

## Implemented through FlashAPI fallback when provider returns fields

| Catalog data point | Backend field(s) |
| --- | --- |
| Username / name / bio / counts | top-level `platform_data` fields |
| External URLs / bio links | `external_url`, `external_urls` |
| Business/contact data | `contact_email`, `contact_phone`, `contact_address` |
| Account region/Facebook id if present | `account_country_region`, `linked_facebook_account` |
| Related Instagram suggestions | `related_instagram_profiles` from FlashAPI `chaining_results` |

The FlashAPI fallback returns the fields the provider actually supplied and
keeps unavailable catalog items documented in `catalog_coverage_notes` instead
of filling the API response with empty placeholder arrays/nulls. Provider access
messages such as `Access Delayed: Only owner can access` are treated as missing
data instead of being exposed as profile names.

## Returned as stable keys with coverage notes

These catalog items are not reliably available from public Instagram scraping or require extra login/authorization-specific collection. The API explains these limitations in `catalog_coverage_notes` instead of adding noisy empty placeholders when no provider data exists.

- Account Creation Date
- Tagged Photos
- Comments Made by Subject
- Story Highlights
- Reels / IGTV Count
- Account Country / Region
- Former Usernames
- Active Ads
- Followers List
- Following List
- Likes on Others' Posts
- Post Image EXIF Metadata
- Direct Message Content

## Notes

- `profile_pic_hash` is currently a SHA-256 hash of downloaded profile-picture bytes. The catalog asked for a perceptual hash; that would require adding an image processing dependency such as Pillow/imagehash in a later sprint.
- Full followers/following lists are intentionally not collected because the catalog marks them not feasible at scale and login/rate-limit constrained.
- Direct messages and private data are not OSINT-accessible and are not collected.
