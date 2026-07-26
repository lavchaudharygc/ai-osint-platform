# backend/app/services/intelligence/reverse_lookup.py

"""
Reverse Keyword Lookup System
Uses extracted keywords to find associated accounts and profile type
"""

import re
from typing import Any, Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import parse_qs, unquote, urlparse

from .hashtag_analyzer import HashtagIntelligenceAnalyzer
from .content_intelligence import ContentIntelligenceExtractor
from backend.services.ai_analyzer import AIAnalyzer
from backend.schemas.intelligence_models import (
    AssociatedAccount,
    ProfileType,
    ReverseLookupResult
)

@dataclass
class KeywordProfile:
    """Profile built from keyword analysis"""
    # Keywords similar to username (variations)
    username_variations: List[str] = field(default_factory=list)
    
    # Keywords not similar to username (interests)
    interest_keywords: List[str] = field(default_factory=list)
    
    # Professional keywords
    professional_keywords: List[str] = field(default_factory=list)
    
    # Associated entities
    associated_entities: List[str] = field(default_factory=list)
    
    # Location keywords
    location_keywords: List[str] = field(default_factory=list)
    
    # Profile type indicators
    profile_type_indicators: Dict[str, float] = field(default_factory=dict)

class ReverseKeywordLookup:
    """
    Reverse keyword lookup to find associated accounts and profile type
    """

    # Keep the profile taxonomy and its evidence rules in one place.  Matching is
    # boundary-aware (see _matching_keywords), so a word such as "art" does not
    # accidentally classify "startup" as an arts profile.
    PROFILE_KEYWORDS = {
        'cyber_security_professional': (
            'cybersecurity', 'cyber security', 'infosec', 'security analyst',
            'security engineer', 'soc analyst', 'incident response', 'dfir',
            'threat intelligence', 'threat hunting', 'digital forensics',
        ),
        'hacker_enthusiast': (
            'hacker', 'hacking', 'ethical hacking', 'ethicalhacking', 'pentest',
            'penetration testing', 'red team', 'redteam', 'bug bounty',
            'bugbounty', 'ctf', 'capture the flag',
        ),
        'developer': (
            'developer', 'software developer', 'programmer', 'programming',
            'coding', 'software engineer', 'web developer', 'webdev', 'appdev',
            'python', 'javascript', 'java', 'devops', 'cloud engineer',
        ),
        'politics': (
            'politics', 'political', 'political science', 'political news',
            'politicalnews', 'public affairs', 'publicaffairs', 'public policy',
            'publicpolicy', 'governance',
            'government', 'election', 'elections', 'democracy', 'parliament',
            'lok sabha', 'loksabha', 'rajya sabha', 'rajyasabha', 'legislature',
            'civic engagement', 'voter', 'voting',
        ),
        'student': (
            'student', 'student life', 'studentlife', 'learner', 'studying',
            'college', 'university', 'school', 'campus', 'academic', 'course',
            'learning', 'training', 'certification', 'exam', 'degree',
            'undergraduate', 'postgraduate', 'graduate student', 'scholarship',
            'semester', 'btech', 'b tech',
            'mtech', 'm tech', 'bca', 'mca', 'mba', 'intern', 'fresher',
        ),
        'art': (
            'art', 'artist', 'artwork', 'digitalart', 'fineart', 'visualart',
            'creative arts', 'creative',
            'photography', 'photographer', 'street photography', 'portrait',
            'graphic design', 'graphicdesign', 'designer', 'ui ux', 'uiux',
            'illustration', 'illustrator', 'music', 'singer', 'guitar', 'piano',
            'producer', 'musician', 'writer', 'writing', 'author', 'blogger', 'poetry',
            'videography', 'filmmaker', 'film director', 'video editor',
        ),
        'business': (
            'startup', 'startupindia', 'startup founder', 'startupfounder',
            'founder', 'cofounder', 'co founder',
            'entrepreneur', 'business', 'business owner', 'marketing',
            'digital marketing', 'digitalmarketing', 'social media marketing',
            'seo', 'brand', 'branding', 'advertising', 'finance', 'investing',
            'trading', 'bitcoin', 'crypto', 'stocks', 'management', 'leadership',
            'business strategy', 'operations', 'ceo', 'company', 'sales',
        ),
        'job_seeker': (
            'job seeker', 'jobseeker', 'open to work', 'opentowork',
            'seeking opportunities', 'looking for work', 'hiring', 'career',
        ),
        'content_creator': (
            'content creator', 'contentcreator', 'influencer', 'youtuber',
            'podcaster', 'reels creator', 'video creator',
        ),
        'privacy_advocate': (
            'privacy advocate', 'privacy', 'encryption', 'opsec',
            'digital rights', 'data protection',
        ),
    }

    PROFILE_TEXT_FIELDS = {
        'bio', 'biography', 'about', 'description', 'headline', 'occupation',
        'title', 'job_title', 'profession', 'role', 'category',
        'business_category', 'account_type', 'page_category',
    }
    MIN_CLASSIFICATION_SCORE = 0.20
    
    def __init__(self):
        self.hashtag_analyzer = HashtagIntelligenceAnalyzer()
        self.content_extractor = ContentIntelligenceExtractor()
        self.ai_analyzer = AIAnalyzer()
        
    async def perform_reverse_lookup(
        self,
        username: str,
        hashtags: List[str],
        recent_posts: List[str],
        dorking_results: List[Dict],
        context: Optional[Dict] = None
    ) -> ReverseLookupResult:
        """
        Main method: Perform reverse keyword lookup
        """
        result = ReverseLookupResult(
            username=username,
            timestamp=datetime.now()
        )
        
        # Step 1: Analyze hashtags
        hashtag_analysis = await self.hashtag_analyzer.analyze_hashtags(
            hashtags=hashtags,
            source="instagram",
            context={'username': username, 'hashtags': hashtags}
        )
        
        # Step 2: Analyze content
        all_content = ' '.join(recent_posts)
        content_analysis = await self.content_extractor.extract_from_content(
            content=all_content,
            source="recent_posts",
            context={'username': username}
        )
        
        # Step 3: Analyze dorking results
        dorking_analysis = await self._analyze_dorking_results(dorking_results, username)
        
        # Step 4: Classify keywords
        keyword_profile = await self._classify_keywords(
            username=username,
            hashtag_analysis=hashtag_analysis,
            content_analysis=content_analysis,
            dorking_analysis=dorking_analysis,
            recent_posts=recent_posts,
            context=context,
        )
        
        result.keyword_profile = keyword_profile
        
        # Step 5: Find associated accounts using similar keywords
        associated_accounts = await self._find_associated_accounts(
            username=username,
            keyword_profile=keyword_profile,
            context=context,
            dorking_results=dorking_results,
        )
        
        result.associated_accounts = associated_accounts
        
        # Step 6: Determine profile type
        profile_type = await self._determine_profile_type(
            username=username,
            keyword_profile=keyword_profile,
            hashtag_analysis=hashtag_analysis,
            content_analysis=content_analysis
        )
        
        result.profile_type = profile_type
        
        # Step 7: Generate intelligence summary
        result.intelligence_summary = self._generate_intelligence_summary(
            keyword_profile=keyword_profile,
            profile_type=profile_type,
            associated_accounts=associated_accounts
        )
        
        return result
    
    async def _analyze_dorking_results(
        self,
        dorking_results: List[Dict],
        username: str
    ) -> Dict:
        """
        Extract intelligence from dorking results
        """
        analysis = {
            'emails': [],
            'organizations': [],
            'names': [],
            'usernames': [],
            'locations': [],
            'key_phrases': []
        }
        
        for result in dorking_results:
            snippet = result.get('snippet', '')
            
            # Extract emails
            content_intel = await self.content_extractor.extract_from_content(
                content=snippet,
                source='dorking',
                context={'username': username}
            )
            
            analysis['emails'].extend(content_intel.emails)
            analysis['organizations'].extend([org['name'] for org in content_intel.organizations])
            analysis['usernames'].extend([m['username'] for m in content_intel.mentioned_usernames])
            analysis['locations'].extend(content_intel.locations)
        
        # Deduplicate
        for key in analysis:
            analysis[key] = list(set(analysis[key]))
        
        return analysis
    
    async def _classify_keywords(
        self,
        username: str,
        hashtag_analysis,
        content_analysis,
        dorking_analysis: Dict,
        recent_posts: Optional[List[str]] = None,
        context: Optional[Dict] = None,
    ) -> KeywordProfile:
        """
        Classify keywords into similar vs different from username
        """
        profile = KeywordProfile()
        
        # Get all keywords from various sources
        all_keywords = set()
        
        # From all hashtag categories, including education, politics and creative.
        for category_keywords in hashtag_analysis.categorized_hashtags.values():
            all_keywords.update(category_keywords)
        
        # From content
        all_keywords.update(content_analysis.skills)
        all_keywords.update(content_analysis.job_titles)
        all_keywords.update(content_analysis.key_phrases)
        for education in content_analysis.education:
            if isinstance(education, dict):
                all_keywords.update(str(value) for value in education.values() if value)
        
        # From dorking
        all_keywords.update(dorking_analysis.get('key_phrases', []))

        # Bios and other profile metadata are real classification evidence, but
        # store only matched terms in the keyword profile rather than exposing a
        # complete bio again in this section of the API response.
        profile_evidence, _ = self._extract_profile_evidence(context)
        profile_terms = set()
        for keywords in self.PROFILE_KEYWORDS.values():
            profile_terms.update(self._matching_keywords(profile_evidence, keywords))
        all_keywords.update(profile_terms)
        
        # Classify each keyword
        for keyword in all_keywords:
            keyword_clean = keyword.lower().replace('#', '').replace('@', '')
            
            # Check similarity to username
            similarity = self._calculate_similarity(keyword_clean, username.lower())
            
            if similarity > 0.5:  # Similar to username
                profile.username_variations.append(keyword)
            else:
                profile.interest_keywords.append(keyword)
        
        # Classify professional keywords
        professional_keywords = set()
        professional_keywords.update(hashtag_analysis.categorized_hashtags.get('technology', []))
        professional_keywords.update(hashtag_analysis.categorized_hashtags.get('cybersecurity_specific', []))
        professional_keywords.update(hashtag_analysis.categorized_hashtags.get('creative', []))
        professional_keywords.update(hashtag_analysis.categorized_hashtags.get('business', []))
        professional_keywords.update(hashtag_analysis.categorized_hashtags.get('education', []))
        professional_keywords.update(hashtag_analysis.categorized_hashtags.get('politics', []))
        professional_keywords.update(content_analysis.skills)
        professional_keywords.update(content_analysis.job_titles)
        professional_keywords.update(profile_terms)
        profile.professional_keywords = list(professional_keywords)
        
        # Extract associated entities
        associated = set()
        associated.update(dorking_analysis.get('organizations', []))
        associated.update([e.name for e in hashtag_analysis.associated_entities])
        profile.associated_entities = list(associated)
        
        # Extract locations
        locations = set()
        locations.update(hashtag_analysis.location_hints)
        locations.update(content_analysis.locations)
        locations.update(dorking_analysis.get('locations', []))
        profile.location_keywords = list(locations)
        
        # Calculate profile type indicators
        profile.profile_type_indicators = self._calculate_profile_indicators(
            hashtag_analysis,
            content_analysis,
            recent_posts=recent_posts,
            context=context,
        )
        
        return profile
    
    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """Calculate string similarity"""
        from difflib import SequenceMatcher
        return SequenceMatcher(None, str1, str2).ratio()
    
    def _calculate_profile_indicators(
        self,
        hashtag_analysis,
        content_analysis,
        recent_posts: Optional[List[str]] = None,
        context: Optional[Dict] = None,
    ) -> Dict[str, float]:
        """
        Calculate absolute, evidence-weighted indicators for profile types.

        Scores are deliberately not normalized against the largest result.  The
        previous normalization turned a single weak clue into 100% confidence and
        made the first zero-valued type (hacker_enthusiast) win empty analyses.
        """
        hashtag_evidence = []
        for category_keywords in hashtag_analysis.categorized_hashtags.values():
            hashtag_evidence.extend(str(value) for value in category_keywords if value)

        content_evidence = [str(value) for value in (recent_posts or []) if value]
        content_evidence.extend(str(value) for value in content_analysis.skills if value)
        content_evidence.extend(str(value) for value in content_analysis.job_titles if value)
        content_evidence.extend(str(value) for value in content_analysis.key_phrases if value)
        for education in content_analysis.education:
            if isinstance(education, dict):
                content_evidence.extend(str(value) for value in education.values() if value)

        profile_evidence, explicit_business = self._extract_profile_evidence(context)
        indicators = {}

        for profile_type, keywords in self.PROFILE_KEYWORDS.items():
            hashtag_matches = self._matching_keywords(hashtag_evidence, keywords)
            content_matches = self._matching_keywords(content_evidence, keywords)
            profile_matches = self._matching_keywords(profile_evidence, keywords)

            # Independent sources have separate caps so repeated keywords in a
            # single long post cannot manufacture high confidence.
            score = min(len(hashtag_matches) * 0.25, 0.55)
            score += min(len(content_matches) * 0.20, 0.50)
            score += min(len(profile_matches) * 0.25, 0.55)

            source_count = sum(bool(matches) for matches in (
                hashtag_matches, content_matches, profile_matches
            ))
            if source_count >= 2:
                score += 0.10
            if profile_type == 'business' and explicit_business:
                score += 0.40

            indicators[profile_type] = round(min(score, 0.95), 2)

        return indicators

    @staticmethod
    def _normalize_evidence(value: Any) -> str:
        """Normalize free text while preserving word boundaries."""
        return re.sub(r'[^a-z0-9]+', ' ', str(value).lower()).strip()

    def _matching_keywords(self, evidence: List[str], keywords) -> Set[str]:
        """Return unique taxonomy terms found as complete words or phrases."""
        normalized_evidence = [self._normalize_evidence(value) for value in evidence if value]
        matches = set()
        for keyword in keywords:
            normalized_keyword = self._normalize_evidence(keyword)
            if not normalized_keyword:
                continue
            needle = f' {normalized_keyword} '
            if any(needle in f' {text} ' for text in normalized_evidence):
                matches.add(normalized_keyword)
        return matches

    def _extract_profile_evidence(
        self,
        context: Optional[Dict]
    ) -> Tuple[List[str], bool]:
        """Collect bios/headlines/categories from nested platform payloads."""
        evidence = []
        explicit_business = False

        def visit(value: Any) -> None:
            nonlocal explicit_business
            if isinstance(value, dict):
                for raw_key, nested in value.items():
                    key = str(raw_key).lower()
                    if key in {'is_business', 'is_business_account', 'business_account'}:
                        explicit_business = explicit_business or nested is True
                    if key in self.PROFILE_TEXT_FIELDS:
                        if isinstance(nested, str) and nested.strip():
                            evidence.append(nested.strip())
                        elif isinstance(nested, (list, tuple, set)):
                            evidence.extend(str(item) for item in nested if item)
                    visit(nested)
            elif isinstance(value, (list, tuple, set)):
                for item in value:
                    visit(item)

        visit(context or {})
        # Preserve order while avoiding multiple copies of the same cross-platform bio.
        return list(dict.fromkeys(evidence)), explicit_business
    
    async def _find_associated_accounts(
        self,
        username: str,
        keyword_profile: KeywordProfile,
        context: Optional[Dict],
        dorking_results: Optional[List[Dict]] = None,
    ) -> List[AssociatedAccount]:
        """
        Infer associated accounts from evidence already collected upstream.

        Reverse lookup is deliberately a pure enrichment step: it must never
        start another search-provider request.  Account candidates therefore
        come only from supplied dork results, collected platform profiles, and
        entities extracted while analysing those inputs.
        """
        associated_accounts = []

        # Reuse profile URLs from the dorking phase rather than repeating the
        # same searches for each username variation.
        for item in dorking_results or []:
            if not isinstance(item, dict):
                continue
            url = str(item.get('url') or item.get('link') or '')
            platform = self._detect_platform_from_url(url)
            if platform == 'unknown':
                platform = self._normalize_platform(item.get('platform'))
            if platform == 'unknown':
                continue

            account_username = self._account_username_from_result(item, platform, url)
            if not account_username:
                continue
            evidence = str(item.get('snippet') or item.get('title') or url)[:200]
            associated_accounts.append(AssociatedAccount(
                username=account_username,
                platform=platform,
                confidence=0.6,
                source='provided_dork_result',
                evidence=evidence,
            ))

        # The investigation endpoint supplies normalized primary and
        # cross-platform profile payloads.  These are already-paid-for results,
        # so they are safe evidence for associated-account candidates.
        for platform, payload in self._context_profiles(context):
            account_username = self._username_from_profile_payload(payload, platform)
            if not account_username:
                continue
            associated_accounts.append(AssociatedAccount(
                username=account_username,
                platform=platform,
                confidence=0.7,
                source='provided_platform_context',
                evidence=f'Username present in supplied {platform} profile data',
            ))
        
        # Use professional keywords to find associated organizations
        for entity in keyword_profile.associated_entities[:3]:
            associated_accounts.append(AssociatedAccount(
                username=entity,
                platform='organization',
                confidence=0.5,
                source='entity_extraction',
                evidence=f'Found in keywords: {entity}'
            ))
        
        # Deduplicate per platform: the same handle on two services represents
        # two distinct account candidates.
        seen = set()
        unique_accounts = []
        for account in associated_accounts:
            identity = (account.platform.casefold(), account.username.casefold())
            if identity not in seen:
                seen.add(identity)
                unique_accounts.append(account)
        
        return unique_accounts

    @staticmethod
    def _normalize_platform(value: Any) -> str:
        """Normalize supported platform labels without guessing categories."""
        normalized = str(value or '').strip().casefold()
        aliases = {
            'x': 'twitter',
            'twitter/x': 'twitter',
            'twitter': 'twitter',
            'instagram': 'instagram',
            'linkedin': 'linkedin',
            'facebook': 'facebook',
            'telegram': 'telegram',
            'tiktok': 'tiktok',
            'github': 'github',
            'youtube': 'youtube',
            'reddit': 'reddit',
        }
        return aliases.get(normalized, 'unknown')

    def _account_username_from_result(
        self,
        item: Dict,
        platform: str,
        url: str,
    ) -> Optional[str]:
        """Extract one account identifier from a supplied search result."""
        for key in ('username', 'handle', 'screen_name', 'login'):
            candidate = self._clean_account_username(item.get(key))
            if candidate:
                return candidate

        candidate = self._username_from_profile_url(url, platform)
        if candidate:
            return candidate

        # Normalized dork results carry the original exact-match value.  Use it
        # only when it looks like a handle, never when it is a name or email.
        match_value = self._clean_account_username(item.get('match_value'))
        if match_value and re.fullmatch(r'[A-Za-z0-9._-]{1,64}', match_value):
            return match_value
        return None

    @staticmethod
    def _clean_account_username(value: Any) -> Optional[str]:
        candidate = str(value or '').strip().lstrip('@')
        if not candidate or any(character.isspace() for character in candidate):
            return None
        return candidate[:100]

    def _username_from_profile_url(self, url: str, platform: str) -> Optional[str]:
        """Extract a handle from common public profile URL shapes."""
        if not url:
            return None
        try:
            parsed = urlparse(url)
        except ValueError:
            return None

        segments = [unquote(segment).strip() for segment in parsed.path.split('/') if segment]
        if platform == 'facebook' and segments[:1] == ['profile.php']:
            return self._clean_account_username(parse_qs(parsed.query).get('id', [None])[0])

        prefixed_paths = {
            'linkedin': {'in', 'company'},
            'reddit': {'user', 'u'},
            'youtube': {'user', 'c', 'channel'},
        }
        prefixes = prefixed_paths.get(platform, set())
        if segments and segments[0].casefold() in prefixes:
            segments = segments[1:]
        if not segments:
            return None

        candidate = segments[0].lstrip('@')
        reserved_paths = {
            'instagram': {'accounts', 'explore', 'p', 'reel', 'reels', 'stories'},
            'twitter': {'compose', 'explore', 'home', 'i', 'intent', 'search', 'share'},
            'linkedin': {'feed', 'jobs', 'learning', 'posts', 'pulse'},
            'facebook': {'groups', 'login', 'marketplace', 'pages', 'reel', 'share', 'watch'},
            'telegram': {'addstickers', 'joinchat', 'proxy', 'share'},
            'tiktok': {'discover', 'foryou', 'login', 'music', 'tag'},
            'github': {'about', 'apps', 'collections', 'enterprise', 'features', 'login', 'marketplace', 'organizations', 'search', 'settings', 'topics'},
            'youtube': {'feed', 'results', 'shorts', 'watch'},
            'reddit': {'r', 'search'},
        }
        if candidate.casefold() in reserved_paths.get(platform, set()):
            return None
        return self._clean_account_username(candidate)

    def _context_profiles(
        self,
        context: Optional[Dict],
    ) -> List[Tuple[str, Dict]]:
        """Return normalized platform profile payloads from supplied context."""
        if not isinstance(context, dict):
            return []

        profiles = []
        primary = context.get('platform_data')
        if isinstance(primary, dict) and primary.get('success') is not False:
            platform = self._normalize_platform(primary.get('platform'))
            if platform != 'unknown':
                profiles.append((platform, primary))

        scraped = context.get('scraped_data')
        if isinstance(scraped, dict):
            for raw_platform, payload in scraped.items():
                platform = self._normalize_platform(raw_platform)
                if (
                    platform != 'unknown'
                    and isinstance(payload, dict)
                    and payload.get('success') is not False
                ):
                    profiles.append((platform, payload))
        return profiles

    def _username_from_profile_payload(
        self,
        payload: Dict,
        platform: str,
    ) -> Optional[str]:
        """Read a username from a normalized profile payload or its envelope."""
        for key in ('username', 'user_name', 'handle', 'screen_name', 'login'):
            candidate = self._clean_account_username(payload.get(key))
            if candidate:
                return candidate

        for key in ('profile', 'user', 'account', 'page', 'data'):
            nested = payload.get(key)
            if isinstance(nested, dict):
                candidate = self._username_from_profile_payload(nested, platform)
                if candidate:
                    return candidate
            elif isinstance(nested, list):
                for item in nested[:1]:
                    if isinstance(item, dict):
                        candidate = self._username_from_profile_payload(item, platform)
                        if candidate:
                            return candidate

        for key in ('url', 'profile_url', 'profileUrl'):
            candidate = self._username_from_profile_url(str(payload.get(key) or ''), platform)
            if candidate:
                return candidate
        return None
    
    async def _determine_profile_type(
        self,
        username: str,
        keyword_profile: KeywordProfile,
        hashtag_analysis,
        content_analysis
    ) -> ProfileType:
        """
        Determine the type of profile based on all analysis
        """
        indicators = keyword_profile.profile_type_indicators

        # Do not let dictionary order decide an empty analysis.  This was the
        # source of the old "Hacker Enthusiast" result for profiles with no data.
        ranked_types = sorted(
            indicators.items(),
            key=lambda item: (-float(item[1]), item[0])
        )
        if not ranked_types or ranked_types[0][1] < self.MIN_CLASSIFICATION_SCORE:
            return ProfileType(
                primary_type='unknown',
                confidence=0.0,
                description='Insufficient public evidence to classify this profile.',
                secondary_types={},
                ai_analysis=None,
                professional_field='Unknown',
                interests=[],
                risk_indicators=['No significant risk indicators'],
            )

        dominant_type, dominant_score = ranked_types[0]
        
        # Surface other evidence-backed classifications without zero-score noise.
        secondary_types = {
            k: v for k, v in indicators.items()
            if v >= self.MIN_CLASSIFICATION_SCORE and k != dominant_type
        }
        
        # Build profile type description
        type_descriptions = {
            'cyber_security_professional': 'Cybersecurity professional with technical expertise',
            'hacker_enthusiast': 'Technology enthusiast with hacking/security interests',
            'developer': 'Software developer or programmer',
            'politics': 'Profile with evidenced interests in politics, governance, or public affairs',
            'student': 'Student or active learner',
            'art': 'Creative arts profile spanning design, photography, music, writing, or video',
            'business': 'Business, entrepreneurship, management, finance, or marketing profile',
            'job_seeker': 'Actively seeking job opportunities',
            'content_creator': 'Content creator or influencer',
            'privacy_advocate': 'Privacy and security conscious individual',
        }
        
        # AI-powered profile typing
        ai_prompt = f"""
        Based on this analysis, determine the most accurate profile type:
        
        Username: {username}
        Dominant Type: {dominant_type} ({dominant_score:.2f})
        Secondary Types: {secondary_types}
        Professional Keywords: {keyword_profile.professional_keywords[:10]}
        Interest Keywords: {keyword_profile.interest_keywords[:10]}
        
        Provide:
        1. Primary profile type
        2. Confidence score
        3. Detailed description
        4. What this person likely does
        5. Their probable interests
        6. Risk indicators (if any)
        """
        
        ai_analysis = None
        analyze_text = getattr(self.ai_analyzer, 'analyze_text', None)
        if callable(analyze_text):
            try:
                ai_analysis = await analyze_text(ai_prompt)
            except Exception:
                ai_analysis = None
        
        return ProfileType(
            primary_type=dominant_type,
            confidence=dominant_score,
            description=type_descriptions.get(dominant_type, 'Unknown'),
            secondary_types=secondary_types,
            ai_analysis=ai_analysis,
            professional_field=self._determine_professional_field(dominant_type, keyword_profile),
            interests=self._extract_interests(keyword_profile, dominant_type),
            risk_indicators=self._extract_risk_indicators(keyword_profile)
        )
    
    def _determine_professional_field(
        self,
        dominant_type: str,
        keyword_profile: KeywordProfile
    ) -> str:
        """Determine professional field"""
        profile_fields = {
            'cyber_security_professional': 'Cybersecurity',
            'hacker_enthusiast': 'Technology/Cybersecurity',
            'developer': 'Software Development',
            'politics': 'Politics/Public Affairs',
            'student': 'Education',
            'art': 'Creative Arts',
            'business': 'Business/Entrepreneurship',
            'job_seeker': 'Career/Employment',
            'content_creator': 'Media/Content Creation',
            'privacy_advocate': 'Privacy/Digital Rights',
        }
        if dominant_type in profile_fields:
            return profile_fields[dominant_type]

        professional_keywords = ' '.join(keyword_profile.professional_keywords).lower()
        
        if any(k in professional_keywords for k in ['cyber', 'security', 'hack', 'infosec']):
            return 'Cybersecurity'
        elif any(k in professional_keywords for k in ['code', 'developer', 'software', 'programming']):
            return 'Software Development'
        elif any(k in professional_keywords for k in ['design', 'graphic', 'video', 'creative']):
            return 'Creative/Design'
        elif any(k in professional_keywords for k in ['business', 'startup', 'entrepreneur']):
            return 'Business/Entrepreneurship'
        elif any(k in professional_keywords for k in ['marketing', 'seo', 'content']):
            return 'Marketing'
        else:
            return 'General'
    
    def _extract_interests(
        self,
        keyword_profile: KeywordProfile,
        dominant_type: Optional[str] = None
    ) -> List[str]:
        """Extract interests from keywords"""
        interests = set()
        
        interest_mapping = {
            'hacking': ['hack', 'cyber', 'security', 'redteam', 'pentest'],
            'coding': ['code', 'programming', 'developer', 'software'],
            'politics': ['politics', 'political', 'governance', 'election', 'parliament'],
            'education': ['student', 'college', 'university', 'study', 'course', 'degree'],
            'creative_arts': ['design', 'graphic', 'creative', 'art', 'music', 'writer', 'photography'],
            'business': ['business', 'startup', 'entrepreneur', 'marketing'],
            'privacy': ['privacy', 'encryption', 'opsec', 'secure'],
            'social_media': ['instagram', 'reels', 'content', 'viral'],
            'technology': ['tech', 'ai', 'blockchain', 'crypto'],
        }
        
        for interest, keywords in interest_mapping.items():
            if any(k in ' '.join(keyword_profile.interest_keywords).lower() for k in keywords):
                interests.add(interest)

        primary_interest = {
            'politics': 'politics',
            'student': 'education',
            'art': 'creative_arts',
            'business': 'business',
            'developer': 'coding',
            'cyber_security_professional': 'cybersecurity',
            'hacker_enthusiast': 'hacking',
            'content_creator': 'social_media',
            'privacy_advocate': 'privacy',
        }.get(dominant_type)
        if primary_interest:
            interests.add(primary_interest)

        return sorted(interests)
    
    def _extract_risk_indicators(self, keyword_profile: KeywordProfile) -> List[str]:
        """Extract risk indicators"""
        risks = []
        
        # Check for high-risk indicators
        high_risk_keywords = ['hacking', 'darkweb', 'exploit', 'malware', 'anonymous']
        if any(k in ' '.join(keyword_profile.professional_keywords).lower() for k in high_risk_keywords):
            risks.append('HIGH: Mentions of potentially illegal activities')
        
        # Check for medium risk
        medium_risk = ['leaked', 'breach', 'dump', 'database']
        if any(k in ' '.join(keyword_profile.interest_keywords).lower() for k in medium_risk):
            risks.append('MEDIUM: Interest in data breaches/leaks')
        
        # Check for personal information exposure
        if any(k in ' '.join(keyword_profile.location_keywords).lower() for k in ['address', 'home', 'personal']):
            risks.append('LOW: Potential personal information exposure')
        
        return risks if risks else ['No significant risk indicators']
    
    def _generate_intelligence_summary(
        self,
        keyword_profile: KeywordProfile,
        profile_type: ProfileType,
        associated_accounts: List[AssociatedAccount]
    ) -> Dict:
        """
        Generate comprehensive intelligence summary
        """
        return {
            'entity_name': 'Target Profile',
            'profile_classification': {
                'primary_type': profile_type.primary_type,
                'confidence': profile_type.confidence,
                'professional_field': profile_type.professional_field
            },
            'key_findings': {
                'username_variations_found': len(keyword_profile.username_variations),
                'associated_accounts_found': len(associated_accounts),
                'organizations_linked': len(keyword_profile.associated_entities),
                'locations_identified': keyword_profile.location_keywords
            },
            'interest_profile': {
                'primary_interests': profile_type.interests,
                'professional_keywords': keyword_profile.professional_keywords[:10],
                'personal_interests': keyword_profile.interest_keywords[:10]
            },
            'risk_assessment': {
                'level': 'HIGH' if len(profile_type.risk_indicators) > 2 else 'MEDIUM' if len(profile_type.risk_indicators) > 1 else 'LOW',
                'indicators': profile_type.risk_indicators
            },
            'associated_entities': {
                'accounts': [{'username': a.username, 'platform': a.platform, 'confidence': a.confidence} 
                           for a in associated_accounts],
                'organizations': keyword_profile.associated_entities
            }
        }
    
    def _detect_platform_from_url(self, url: str) -> str:
        """Detect platform from URL"""
        platform_patterns = {
            'instagram': ['instagram.com'],
            'twitter': ['twitter.com', 'x.com'],
            'linkedin': ['linkedin.com'],
            'github': ['github.com'],
            'facebook': ['facebook.com'],
            'telegram': ['t.me', 'telegram.me'],
            'tiktok': ['tiktok.com'],
            'reddit': ['reddit.com'],
            'youtube': ['youtube.com'],
        }
        
        for platform, patterns in platform_patterns.items():
            if any(p in url.lower() for p in patterns):
                return platform
        
        return 'unknown'
