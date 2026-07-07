# backend/app/services/intelligence/reverse_lookup.py

"""
Reverse Keyword Lookup System
Uses extracted keywords to find associated accounts and profile type
"""

import asyncio
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime

from .hashtag_analyzer import HashtagIntelligenceAnalyzer
from .content_intelligence import ContentIntelligenceExtractor
from backend.services.ai_analyzer import AIAnalyzer
from backend.services.google_dorking import GoogleDorkingService
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
    
    def __init__(self):
        self.hashtag_analyzer = HashtagIntelligenceAnalyzer()
        self.content_extractor = ContentIntelligenceExtractor()
        self.ai_analyzer = AIAnalyzer()
        self.dorking_engine = GoogleDorkingService()
        
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
            dorking_analysis=dorking_analysis
        )
        
        result.keyword_profile = keyword_profile
        
        # Step 5: Find associated accounts using similar keywords
        associated_accounts = await self._find_associated_accounts(
            username=username,
            keyword_profile=keyword_profile,
            context=context
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
        dorking_analysis: Dict
    ) -> KeywordProfile:
        """
        Classify keywords into similar vs different from username
        """
        profile = KeywordProfile()
        
        # Get all keywords from various sources
        all_keywords = set()
        
        # From hashtags
        all_keywords.update(hashtag_analysis.categorized_hashtags.get('technology', []))
        all_keywords.update(hashtag_analysis.categorized_hashtags.get('cybersecurity_specific', []))
        all_keywords.update(hashtag_analysis.categorized_hashtags.get('business', []))
        all_keywords.update(hashtag_analysis.categorized_hashtags.get('personal', []))
        
        # From content
        all_keywords.update(content_analysis.skills)
        all_keywords.update(content_analysis.job_titles)
        
        # From dorking
        all_keywords.update(dorking_analysis.get('key_phrases', []))
        
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
        professional_keywords.update(hashtag_analysis.categorized_hashtags.get('business', []))
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
            content_analysis
        )
        
        return profile
    
    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """Calculate string similarity"""
        from difflib import SequenceMatcher
        return SequenceMatcher(None, str1, str2).ratio()
    
    def _calculate_profile_indicators(
        self,
        hashtag_analysis,
        content_analysis
    ) -> Dict[str, float]:
        """
        Calculate indicators for different profile types
        """
        indicators = {
            'hacker_enthusiast': 0.0,
            'cyber_security_professional': 0.0,
            'developer': 0.0,
            'designer': 0.0,
            'entrepreneur': 0.0,
            'student': 0.0,
            'job_seeker': 0.0,
            'content_creator': 0.0,
            'privacy_advocate': 0.0,
        }
        
        # Analyze hashtag categories
        cybersecurity_tags = len(hashtag_analysis.categorized_hashtags.get('cybersecurity_specific', []))
        tech_tags = len(hashtag_analysis.categorized_hashtags.get('technology', []))
        business_tags = len(hashtag_analysis.categorized_hashtags.get('business', []))
        creative_tags = len(hashtag_analysis.categorized_hashtags.get('creative', []))
        
        total_tags = hashtag_analysis.total_hashtags or 1
        
        # Calculate scores
        if cybersecurity_tags > 0:
            indicators['cyber_security_professional'] = cybersecurity_tags / total_tags
            indicators['hacker_enthusiast'] = cybersecurity_tags / total_tags * 0.8
        
        if tech_tags > 0:
            indicators['developer'] = tech_tags / total_tags
        
        if business_tags > 0:
            indicators['entrepreneur'] = business_tags / total_tags
        
        if creative_tags > 0:
            indicators['content_creator'] = creative_tags / total_tags
            indicators['designer'] = creative_tags / total_tags * 0.6
        
        # Check content for additional indicators
        if content_analysis.skills:
            if any('security' in s.lower() or 'hack' in s.lower() for s in content_analysis.skills):
                indicators['cyber_security_professional'] += 0.2
                indicators['hacker_enthusiast'] += 0.2
        
        # Normalize
        max_score = max(indicators.values()) if max(indicators.values()) > 0 else 1
        indicators = {k: min(v / max_score, 1.0) for k, v in indicators.items()}
        
        return indicators
    
    async def _find_associated_accounts(
        self,
        username: str,
        keyword_profile: KeywordProfile,
        context: Optional[Dict]
    ) -> List[AssociatedAccount]:
        """
        Find associated accounts using keyword reverse lookup
        """
        associated_accounts = []
        
        # Use username variations to find associated accounts
        for variation in keyword_profile.username_variations[:5]:
            # Create dork to search for this variation
            dorks = [
                f'site:instagram.com "{variation}"',
                f'site:twitter.com "{variation}"',
                f'site:linkedin.com "{variation}"',
                f'"{variation}" social media',
            ]
            
            for dork in dorks:
                try:
                    results = await self.dorking_engine.execute_single_dork(
                        {'dork': dork, 'platform': 'reverse_lookup', 'category': 'associated'}
                    )
                    
                    if results and results.get('has_results'):
                        for item in results.get('results', [])[:3]:
                            associated_accounts.append(AssociatedAccount(
                                username=variation,
                                platform=self._detect_platform_from_url(item.get('url', '')),
                                confidence=0.6,
                                source='keyword_reverse_lookup',
                                evidence=item.get('snippet', '')[:200]
                            ))
                except:
                    pass
        
        # Use professional keywords to find associated organizations
        for entity in keyword_profile.associated_entities[:3]:
            associated_accounts.append(AssociatedAccount(
                username=entity,
                platform='organization',
                confidence=0.5,
                source='entity_extraction',
                evidence=f'Found in keywords: {entity}'
            ))
        
        # Deduplicate
        seen = set()
        unique_accounts = []
        for account in associated_accounts:
            if account.username not in seen:
                seen.add(account.username)
                unique_accounts.append(account)
        
        return unique_accounts
    
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
        
        # Find the dominant profile type
        dominant_type = max(indicators, key=indicators.get)
        dominant_score = indicators[dominant_type]
        
        # Secondary types (score > 0.3)
        secondary_types = {
            k: v for k, v in indicators.items()
            if v > 0.3 and k != dominant_type
        }
        
        # Build profile type description
        type_descriptions = {
            'cyber_security_professional': 'Cybersecurity professional with technical expertise',
            'hacker_enthusiast': 'Technology enthusiast with hacking/security interests',
            'developer': 'Software developer or programmer',
            'designer': 'Creative designer or artist',
            'entrepreneur': 'Business owner or startup founder',
            'student': 'Student or learner',
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
        
        try:
            ai_analysis = await self.ai_analyzer.analyze_text(ai_prompt)
        except:
            ai_analysis = None
        
        return ProfileType(
            primary_type=dominant_type,
            confidence=dominant_score,
            description=type_descriptions.get(dominant_type, 'Unknown'),
            secondary_types=secondary_types,
            ai_analysis=ai_analysis,
            professional_field=self._determine_professional_field(keyword_profile),
            interests=self._extract_interests(keyword_profile),
            risk_indicators=self._extract_risk_indicators(keyword_profile)
        )
    
    def _determine_professional_field(self, keyword_profile: KeywordProfile) -> str:
        """Determine professional field"""
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
    
    def _extract_interests(self, keyword_profile: KeywordProfile) -> List[str]:
        """Extract interests from keywords"""
        interests = set()
        
        interest_mapping = {
            'hacking': ['hack', 'cyber', 'security', 'redteam', 'pentest'],
            'coding': ['code', 'programming', 'developer', 'software'],
            'design': ['design', 'graphic', 'creative', 'art'],
            'business': ['business', 'startup', 'entrepreneur', 'marketing'],
            'privacy': ['privacy', 'encryption', 'opsec', 'secure'],
            'social_media': ['instagram', 'reels', 'content', 'viral'],
            'technology': ['tech', 'ai', 'blockchain', 'crypto'],
        }
        
        for interest, keywords in interest_mapping.items():
            if any(k in ' '.join(keyword_profile.interest_keywords).lower() for k in keywords):
                interests.add(interest)
        
        return list(interests)
    
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
            'youtube': ['youtube.com'],
        }
        
        for platform, patterns in platform_patterns.items():
            if any(p in url.lower() for p in patterns):
                return platform
        
        return 'unknown'