Hashtag Connection classification

SECTION 1: HASHTAG CONNECTION CLASSIFICATION:----

Connection Types:----
                      SAME PERSON	    90-100%	Exact unique hashtag match + same PFP + same bio keywords	Merge identities, create master profile
                      SAME PERSON	    80-89%	5+ identical hashtags + username pattern match	Flag for manual verification
                      CLOSE ASSOCIATE	70-79%	Tagged in 10+ posts + mutual follows + same events	Mark as inner circle, prioritize
                      CLOSE ASSOCIATE	60-69%	Comment frequency high + similar content style	Note as strong connection
                      ASSOCIATE	50-59%	3-5 common hashtags + occasional tags	Add to network map
                      ASSOCIATE	40-49%	1-2 common hashtags + weak interaction	Keep in watchlist
                      ORGANIZATION	    80-95%	Official username + multiple employees tagged	Identify as corporate/brand account
                      ORGANIZATION	    70-79%	Bio mentions company + professional content	Flag for business mapping
                      COMPETITOR	40-59%	Similar niche, different content style	Monitor for competitive intelligence
                      UNRELATED	0-29%	Random overlap, no other connections	Ignore, don't waste time

Classification Rules:----

                      Rule 1: Same Person Detection (Expanded)

                             Indicator	Points	Example:----
                                                              Unique hashtag (used by <5 accounts globally)	+30	              ex:---    #MySecretAlias2024
                                                              Rare hashtag (used 5-100 times)	+20	                          ex:---    #JohnDoeNYC
                                                              8+ identical hashtags across profiles	+25                       ex:---  	#travel #photography #nyc #coffee...
                                                              Same username pattern (e.g., @johndoe, @johndoe_off)	+20       ex:--- 	@realsmith vs @smith_real
                                                              Same profile picture (exact match)	+25	                          ex:---    Same headshot in both
                                                              Similar profile picture (same person, diff angle)	+15	          ex:---    Different photo, same face
                                                              Same bio keywords (3+ exact matches)	+15	                      ex:---   "Photographer	Traveler	Foodie"
                                                              Same location hashtags (2+ matches)	+10    	                  ex:---   #NYC #Manhattan
                                                              Same link in bio (URL match)	+20	                              ex:---   linktr.ee/johndoe
                                                              Same email pattern	+15                                           ex:---	  johndoe@ vs john.doe@
Threshold Calculation:----

                              >70 points - SAME PERSON (High Confidence)
                               60-69 points - SAME PERSON (Moderate Confidence)     - Manual verify 
                               40-59 points - POSSIBLE SAME PERSON                  - Investigate further
                               <40 points - NOT SAME PERSON
                               
                
                
                      Rule 2:  Close Associate Detection:----
                                                    Indicator:---	                             Points:---     	    Example:---
                                                    Tagged together in 1-2 posts	                 +20                @john and @jane in 15 Instagram posts
                                                    Tagged together in 5-9 posts               	 +25	                -
                                                    Mutual follows on 3+ platforms	             +20                	Instagram, Twitter, LinkedIn
                                                    Mutual follows on 1-2 platforms	             +10             	-
                                                    Same event hashtags (3+ events)	             +20	                #NYE2025 #BeachParty #Wedding
                                                    Same event hashtags (1-2 events)              +10	            -
                                                    Similar content posting time (±1 hour) 	      +10	            Both active 8-10 PM daily
                                                    Comments on each other's posts (5+ last month)+15	            Regular interaction
                                                    Mentions in stories (3+ times)	              +10	            Tagged in IG stories
                                                    Same group (tagged in same 3+ group photos)	  +15	            Group photos with 5+ mutual friends
                                                    Shared interests (3+ same subcategories)	      +10	            Both into #Fitness, #Tech, #Cooking
                                                    
                                                    
                      Rule 3:   Organization Detection:----
                                                    Indicator:---                                   Points:---        Example:---
                                  Username contains: official, team, hq, org, corp, ltd, inc, co	    +20	              @apple, @google, @tesla_official
                                                     Bio mentions company/brand name	                +20	             "We build AI solutions"
                                                     Multiple employees tagged (5+ employees)	    +20	              CFO, CTO, HR tagged separately 
                                                     Employees tagged (2-4 distinct)              	+10	              -
                                                     Professional content only (no personal photos)	+15	              All posts are about work
                                                     No personal content (vacation, family, etc.)	+15	              Strictly business
                                                     Business hashtags (3+ like #startup #tech #innovation)	+15	      -
                                                     Location is office/business address	            +10	              "123 Business St, SF"
                                                     Link to official website	                     10	              Company domain in bio
                                                     
                                

Tagged User Relationship Detetmination:----
                         Relationship Types:----  
                                                  Realtionship:---                        Indicator:---                               Confidence:---
                                                                                          - Same surname (last name) - +25
                                                                                          - Tagged in family holiday posts - +20 
                                                      Family                              - Mentions "bro/sis/mom/dad/uncle" - +20         80-95%
                                                                                          - Childhood photos - +15
                                                                                          - Family reunion hashtags - +10
                                                                                          - Similar facial features - +10
                                                                                          
                                                                                          - Romantic photos together → +25
                                                                                          - Heart emojis in captions/comments → +20
                                                      Partner/Spouce                      - Frequent tags (5+ in last month) → +20         80-95%
                                                                                          - Wedding/anniversary posts → +20
                                                                                          - Couple hashtags (#couplegoals, #love) → +15

                                                                                          - Casual hangout photos → +20
                                                                                          - Inside jokes in comments → +15
                                                      Close Friend                        - Tagged in 10+ posts → +20                       70-85%
                                                                                          - Similar interests → +15
                                                                                          - Same friend group → +10
                                
                                                                                          - Same company hashtags → +20
                                                                                          - Professional photos (office, events) → +15
                                                     Colleague                            - LinkedIn connection → +15                       70-85%
                                                                                          - Work-related captions → +10
                                                                                          - Tagged in work group photos → +10
                                                                                          
                                                                                          - Brand collab tags → +20
                                                                                          - Business hashtags (#business, #collab) → +15
                                                    Business contact                      - Formal photos → +10                             60-75%
                                                                                          - Minimal personal interaction → +10
                                                                                          - Mention of products/services → +10
                                                                                          
                                                                                          - Tagged 1-2 times → +5
                                                                                          - Event photos (wedding, party) → +5
                                                    Acquaintance                          - Minimal comments → +5                           30-50%
                                                                                          - No mutual connections → +5
                                                                                          
                                                                                          
                                                                       
Advance Relationship Scoring:----
def determine_relationship_advanced(user1, user2, interaction_data):
    """
    Returns relationship type with confidence percentage
    """
    score = 0
    indicators = []
    
    # --- FAMILY INDICATORS ---
    if same_surname(user1['full_name'], user2['full_name']):
        score += 25
        indicators.append("Same surname")
    
    if 'family' in interaction_data['post_captions']:
        score += 20
        indicators.append("Family mentioned in posts")
    
    # --- PARTNER INDICATORS ---
    if interaction_data['romantic_tags'] > 3:
        score += 25
        indicators.append("Multiple romantic tags")
    
    if 'heart_emoji' in interaction_data['comment_patterns']:
        score += 20
        indicators.append("Heart emojis used")
    
    # --- FREQUENCY INDICATORS ---
    if interaction_data['tag_count'] >= 10:
        score += 20
    elif interaction_data['tag_count'] >= 5:
        score += 15
    elif interaction_data['tag_count'] >= 2:
        score += 5
    
    # --- PLATFORM INDICATORS ---
    if interaction_data['mutual_platforms'] >= 3:
        score += 15
        indicators.append("Connected on 3+ platforms")
    
    # --- CONTENT INDICATORS ---
    if interaction_data['shared_interests'] >= 3:
        score += 10
        indicators.append("3+ shared interests")
    
    # --- DETERMINE RELATIONSHIP ---
    if score > 70:
        if 'surname' in indicators and 'family' in interaction_data['keywords']:
            relationship = "Family"
            confidence = "85-95%"
        elif 'romantic_tags' in indicators:
            relationship = "Partner/Spouse"
            confidence = "85-95%"
        else:
            relationship = "Very Close Connection"
            confidence = "80-90%"
    
    elif score > 50:
        if 'company_hashtags' in interaction_data['post_types']:
            relationship = "Colleague"
            confidence = "70-80%"
        else:
            relationship = "Close Friend"
            confidence = "70-85%"
    
    elif score > 30:
        relationship = "Associate"
        confidence = "50-70%"
    
    elif score > 15:
        relationship = "Acquaintance"
        confidence = "30-50%"
    
    else:
        relationship = "Minimal Connection"
        confidence = "0-30%"
    
    return {
        "relationship": relationship,
        "confidence": confidence,
        "score": score,
        "indicators": indicators
    }
    
    
    
    
Associated Account Confidence Scoring:----
     
                                        Factor:---          Weight:---         Sub-factor:---                                          Example:---
                                                                               - Exact match (100%) → 30/30
                                                                               - Levenshtein distance ≤2 (90%) → 27/30
                                        Username Similarity   30%              - Same pattern (80%) → 24/30                             @john_doe vs @johndoe (95%)
                                                                               - Contains same base name (60%) → 18/30
                                             
                                                                               - Same photo (100%) → 25/25
                                                                               - Same face, different photo (80%) → 20/25
                                        Profile Picture match  25%             - Same style (60%) → 15/25                               Both have same wedding photo
                                                                               - No match (0%) → 0/25
                                             
                                                                               - 70%+ keyword overlap → 20/20
                                                                               - 40-69% overlap → 14/20 
                                        Bio Similarity         20%             - 10-39% overlap → 8/20                                  Both say "Tech enthusiast	Traveler"  
                                                                               - <10% overlap → 0/20
                                             
                                                                               - Exact same → 10/10
                                                                               - Same city → 8/10
                                        Location Match         10%             - Same state/region → 5/10                               Both in "Austin, TX"
                                                                               - Different → 0/10     
                                                                               
                                                                               - 5+ mutual followers → 10/10
                                                                               - 3-4 mutual → 7/10 
                                        Mutual connections      10%            - 1-2 mutual → 4/10                                      8 Common Friends
                                                                               - 0 mutual → 0/10
                                             
                                                                               - Same posting schedule (same times) → 5/5
                                                                               - Same topics (70%+) → 4/5
                                        Content Similarity      5%             - Similar hashtags → 3/5                                 both post at 8 am daily
                                                                               - No similarity → 0/5     
                                                                               
                                                                               
                                                                               
Scoring Alogritham:----

import re
from difflib import SequenceMatcher
from imagehash import average_hash
from PIL import Image

def confidence_score_advanced(account1, account2):
    """
    Returns confidence score (0-100) with breakdown
    """
    score = 0
    breakdown = {}
    
    # 1. Username Similarity (30%)
    username_sim = calculate_username_similarity(
        account1['username'], 
        account2['username']
    )
    username_score = username_sim * 0.30 * 100
    score += username_score
    breakdown['username'] = round(username_score, 2)
    
    # 2. Profile Picture Match (25%)
    if account1.get('profile_pic_url') and account2.get('profile_pic_url'):
        pfp_match = compare_profile_pictures(
            account1['profile_pic_url'], 
            account2['profile_pic_url']
        )
        pfp_score = pfp_match * 0.25 * 100
        score += pfp_score
        breakdown['profile_picture'] = round(pfp_score, 2)
    else:
        breakdown['profile_picture'] = 0
    
    # 3. Bio Similarity (20%)
    bio_sim = calculate_text_similarity(
        account1.get('bio', ''), 
        account2.get('bio', '')
    )
    bio_score = bio_sim * 0.20 * 100
    score += bio_score
    breakdown['bio'] = round(bio_score, 2)
    
    # 4. Location Match (10%)
    if account1.get('location') and account2.get('location'):
        if account1['location'] == account2['location']:
            loc_score = 10
        elif account1['location'].split(',')[0] == account2['location'].split(',')[0]:
            loc_score = 8  # Same city
        else:
            loc_score = 0
        score += loc_score
        breakdown['location'] = loc_score
    else:
        breakdown['location'] = 0
    
    # 5. Mutual Connections (10%)
    mutual = len(set(account1.get('followers', [])) & set(account2.get('followers', [])))
    if mutual >= 5:
        mutual_score = 10
    elif mutual >= 3:
        mutual_score = 7
    elif mutual >= 1:
        mutual_score = 4
    else:
        mutual_score = 0
    score += mutual_score
    breakdown['mutual_connections'] = mutual_score
    
    # 6. Content Similarity (5%)
    content_sim = compare_content_patterns(
        account1.get('recent_posts', []),
        account2.get('recent_posts', [])
    )
    content_score = content_sim * 5
    score += content_score
    breakdown['content_similarity'] = round(content_score, 2)
    
    # Final confidence
    final_score = min(100, score)
    
    # Confidence Level
    if final_score >= 75:
        level = "HIGH CONFIDENCE - Same Person"
        action = "Merge identities"
    elif final_score >= 55:
        level = "MODERATE CONFIDENCE - Likely Same Person"
        action = "Manual verification required"
    elif final_score >= 35:
        level = "LOW CONFIDENCE - Possible Connection"
        action = "Investigate further"
    else:
        level = "VERY LOW - Unlikely Connection"
        action = "Ignore"
    
    return {
        "total_score": round(final_score, 2),
        "breakdown": breakdown,
        "confidence_level": level,
        "recommended_action": action
    }


# helper Function
def calculate_username_similarity(u1, u2):
    """Levenshtein-based similarity"""
    from Levenshtein import ratio
    return ratio(u1.lower(), u2.lower())

def compare_profile_pictures(url1, url2):
    """Image hash comparison"""
    img1 = Image.open(requests.get(url1, stream=True).raw)
    img2 = Image.open(requests.get(url2, stream=True).raw)
    hash1 = average_hash(img1)
    hash2 = average_hash(img2)
    return 1 - (hash1 - hash2) / 64  # 0-1 scale

def calculate_text_similarity(text1, text2):
    """Semantic similarity using SequenceMatcher"""
    return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()

def compare_content_patterns(posts1, posts2):
    """Compare posting times and hashtags"""
    # Simplified: returns 0.5 if both have similar topics
    hashtags1 = set(' '.join(posts1).split())
    hashtags2 = set(' '.join(posts2).split())
    overlap = len(hashtags1 & hashtags2)
    total = len(hashtags1 | hashtags2)
    return overlap / total if total > 0 else 0
                 
                 
                 
Interest Cluster Mapping:----
From Hashtags to Interest Profile:----

INTEREST_HIERARCHY = {
    "Technology": {
        "subcategories": {
            "Programming": ["python", "javascript", "java", "coding", "developer", "programmer"],
            "AI/ML": ["artificial intelligence", "machine learning", "deep learning", "neural networks"],
            "Cybersecurity": ["security", "hacking", "ethical hacking", "cyber", "firewall"],
            "Hardware": ["arduino", "raspberry pi", "electronics", "circuit"],
            "Mobile": ["android", "ios", "mobile app", "app development"]
        },
        "related_professions": ["Developer", "Engineer", "Data Scientist", "Security Analyst", "Tech Lead"],
        "confidence_boost": 0.8  # Higher weight for tech hashtags
    },
    
    "Creative Arts": {
        "subcategories": {
            "Photography": ["photography", "photographer", "street photography", "portrait", "landscape"],
            "Design": ["graphic design", "ui/ux", "user interface", "illustration"],
            "Music": ["music", "singer", "guitar", "piano", "producer", "musician"],
            "Writing": ["writer", "author", "blogger", "story", "poetry"],
            "Video": ["videography", "film", "director", "youtube", "editor"]
        },
        "related_professions": ["Photographer", "Designer", "Artist", "Content Creator", "Filmmaker"],
        "confidence_boost": 0.7
    },
    
    "Business": {
        "subcategories": {
            "Entrepreneurship": ["startup", "founder", "entrepreneur", "business owner"],
            "Marketing": ["marketing", "social media", "seo", "brand", "advertising"],
            "Finance": ["finance", "investing", "trading", "bitcoin", "crypto", "stocks"],
            "Management": ["management", "leadership", "business strategy", "operations"]
        },
        "related_professions": ["Founder", "CEO", "Manager", "Consultant", "Analyst"],
        "confidence_boost": 0.9
    },
    
    "Lifestyle": {
        "subcategories": {
            "Fitness": ["gym", "fitness", "yoga", "workout", "nutrition", "health"],
            "Travel": ["travel", "wanderlust", "explore", "adventure", "backpacking"],
            "Food": ["food", "cooking", "chef", "restaurant", "foodie"],
            "Fashion": ["fashion", "style", "outfit", "model", "fashionista"]
        },
        "related_professions": ["Trainer", "Influencer", "Chef", "Blogger", "Model"],
        "confidence_boost": 0.6
    }
}

def map_interest_profile(hashtags, bio, posts):
    """
    Maps an account to interest clusters
    Returns: {
        "primary_interest": "Technology",
        "sub_interest": "Programming",
        "profession": "Developer",
        "confidence": 85
    }
    """
    interests = {}
    total_mentions = 0
    
    # Combine all text data
    text_data = ' '.join(hashtags) + ' ' + bio + ' ' + ' '.join(posts)
    text_data = text_data.lower()
    
    # Count occurrences of each subcategory
    for interest, data in INTEREST_HIERARCHY.items():
        for subcat, keywords in data['subcategories'].items():
            count = sum(1 for kw in keywords if kw in text_data)
            if count > 0:
                interests[subcat] = count
                total_mentions += count
    
    if total_mentions == 0:
        return {"primary_interest": "Unknown", "confidence": 0}
    
    # Find primary subcategory
    primary_subcat = max(interests, key=interests.get)
    
    # Find primary interest category
    for interest, data in INTEREST_HIERARCHY.items():
        if primary_subcat in data['subcategories']:
            primary_interest = interest
            confidence = (interests[primary_subcat] / total_mentions) * 100 * data['confidence_boost']
            
            # Suggest profession
            related_professions = data['related_professions']
            suggested_profession = related_professions[0]
            
            return {
                "primary_interest": primary_interest,
                "sub_interest": primary_subcat,
                "all_interests": interests,
                "suggested_profession": suggested_profession,
                "confidence": round(min(100, confidence), 2)
            }
                                             
                                             
                                             
