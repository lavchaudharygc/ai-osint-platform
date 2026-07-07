# backend/app/services/intelligence/hashtag_analyzer.py

"""
Hashtag Intelligence Analyzer
Extracts deep intelligence from hashtags across platforms
"""

import re
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass, field
from collections import Counter
from datetime import datetime
import asyncio

from backend.services.ai_analyzer import AIAnalyzer
from backend.schemas.intelligence_models import (
    HashtagIntelligence,
    UsernameVariation,
    EntityMention,
    PersonalityIndicator
)

@dataclass
class HashtagAnalysis:
    """Complete hashtag analysis result"""
    source: str
    total_hashtags: int
    unique_hashtags: int
    
    # Username variations discovered
    potential_usernames: List[UsernameVariation] = field(default_factory=list)
    
    # Associated entities (people, companies, brands)
    associated_entities: List[EntityMention] = field(default_factory=list)
    
    # Personality and interest indicators
    personality_indicators: List[PersonalityIndicator] = field(default_factory=list)
    
    # Professional indicators
    professional_indicators: List[Dict] = field(default_factory=list)
    
    # Location hints
    location_hints: List[str] = field(default_factory=list)
    
    # Event mentions
    event_mentions: List[str] = field(default_factory=list)
    
    # Sentiment and emotion
    sentiment_indicators: List[str] = field(default_factory=list)
    
    # Frequency analysis
    hashtag_frequency: Dict[str, int] = field(default_factory=dict)
    
    # Categorized hashtags
    categorized_hashtags: Dict[str, List[str]] = field(default_factory=dict)

class HashtagIntelligenceAnalyzer:
    """
    Advanced hashtag analysis for intelligence gathering
    """
    
    def __init__(self):
        self.ai_analyzer = AIAnalyzer()
        
        # Classification patterns
        self.username_patterns = [
            r'@([a-zA-Z0-9._]+)',  # Direct @mentions
            r'#([a-zA-Z0-9._]+)',   # Hashtag that looks like username
        ]
        
        # Known username format indicators
        self.username_indicators = [
            '_', '.', 'official', 'real', 'its', 'the',
            'team', 'org', 'inc', 'co', 'io'
        ]
        
        # Keyword categories for profiling
        self.interest_categories = {
            'technology': [
                'cyber', 'security', 'hacking', 'coding', 'developer',
                'tech', 'software', 'programming', 'ai', 'machine',
                'blockchain', 'crypto', 'web3', 'devops', 'cloud',
                'google', 'android', 'ios', 'app', 'startup'
            ],
            'cybersecurity_specific': [
                'redteam', 'blueteam', 'pentest', 'vulnerability',
                'exploit', 'malware', 'forensics', 'incident',
                'threat', 'soc', 'dfir', 'cti', 'bugbounty',
                'ethicalhacking', 'infosec', 'opsec', 'privacy',
                'encryption', 'darkweb', 'tor', 'osint'
            ],
            'creative': [
                'design', 'art', 'photography', 'video', 'editing',
                'graphic', 'animation', 'creative', 'music', 'writing',
                'content', 'reels', 'viral', 'trending'
            ],
            'business': [
                'startup', 'business', 'entrepreneur', 'marketing',
                'sales', 'branding', 'seo', 'growth', 'hiring',
                'jobs', 'career', 'fresher', 'remote', 'wfh',
                'company', 'team', 'founder', 'ceo'
            ],
            'personal': [
                'birthday', 'family', 'friend', 'love', 'life',
                'motivation', 'fitness', 'health', 'travel', 'food',
                'brother', 'sister', 'mother', 'father', 'sibling',
                'bhai', 'bhaichara', 'brotherhood', 'friendship'
            ],
            'education': [
                'student', 'college', 'university', 'school', 'study',
                'learning', 'certification', 'course', 'exam', 'degree',
                'campus', 'alumni', 'batch', 'class'
            ],
            'indian_context': [
                'india', 'indian', 'bharat', 'desi', 'hindi',
                'hinglish', 'delhi', 'mumbai', 'bangalore', 'startupindia',
                'madeinindia', 'vocalforlocal', 'digitalindia'
            ]
        }
        
    async def analyze_hashtags(
        self,
        hashtags: List[str],
        source: str = "instagram",
        context: Optional[Dict] = None
    ) -> HashtagAnalysis:
        """
        Comprehensive hashtag analysis
        """
        analysis = HashtagAnalysis(
            source=source,
            total_hashtags=len(hashtags),
            unique_hashtags=len(set(hashtags))
        )
        
        # Calculate frequency
        analysis.hashtag_frequency = dict(Counter(hashtags))
        
        # Step 1: Extract potential usernames
        analysis.potential_usernames = await self._extract_usernames(hashtags, context)
        
        # Step 2: Extract associated entities
        analysis.associated_entities = await self._extract_entities(hashtags, context)
        
        # Step 3: Analyze personality indicators
        analysis.personality_indicators = await self._analyze_personality(hashtags)
        
        # Step 4: Extract professional indicators
        analysis.professional_indicators = await self._extract_professional_info(hashtags)
        
        # Step 5: Categorize all hashtags
        analysis.categorized_hashtags = self._categorize_hashtags(hashtags)
        
        # Step 6: Extract location hints
        analysis.location_hints = self._extract_location_hints(hashtags)
        
        # Step 7: Extract event mentions
        analysis.event_mentions = self._extract_event_mentions(hashtags)
        
        # Step 8: Analyze sentiment
        analysis.sentiment_indicators = self._analyze_sentiment(hashtags)
        
        # Step 9: AI-powered deep analysis
        if context:
            ai_insights = await self._ai_deep_analysis(analysis, context)
            analysis.personality_indicators.extend(ai_insights)
        
        return analysis
    
    async def _extract_usernames(
        self,
        hashtags: List[str],
        context: Optional[Dict]
    ) -> List[UsernameVariation]:
        """
        Extract potential username variations from hashtags
        """
        usernames = []
        known_username = context.get('username', '') if context else ''
        
        for hashtag in hashtags:
            tag = hashtag.lower().replace('#', '')
            
            # Check if hashtag looks like a username
            confidence = self._calculate_username_confidence(tag, known_username)
            
            if confidence > 0.3:  # Threshold for username-like
                # Determine if it's a variation of known username
                is_variation = self._is_username_variation(tag, known_username)
                
                usernames.append(UsernameVariation(
                    value=tag,
                    confidence=confidence,
                    is_known_variation=is_variation,
                    source='hashtag',
                    platform_hint=self._detect_platform(tag)
                ))
        
        # Sort by confidence
        usernames.sort(key=lambda x: x.confidence, reverse=True)
        
        return usernames
    
    def _calculate_username_confidence(self, tag: str, known_username: str) -> float:
        """
        Calculate confidence that a hashtag is a username
        """
        confidence = 0.0
        
        # Check for username patterns
        if re.match(r'^[a-zA-Z][a-zA-Z0-9._]{2,30}$', tag):
            confidence += 0.3
        
        # Check for username indicators
        for indicator in self.username_indicators:
            if indicator in tag:
                confidence += 0.1
                break
        
        # Check similarity to known username
        if known_username:
            similarity = self._string_similarity(tag, known_username)
            confidence += similarity * 0.3
        
        # Check if it contains numbers (common in usernames)
        if re.search(r'\d', tag):
            confidence += 0.1
        
        # Check length (typical username length)
        if 5 <= len(tag) <= 30:
            confidence += 0.1
        
        return min(confidence, 1.0)
    
    def _is_username_variation(self, tag: str, known_username: str) -> bool:
        """
        Check if hashtag is a variation of known username
        """
        if not known_username:
            return False
        
        known_lower = known_username.lower()
        tag_lower = tag.lower()
        
        # Direct match
        if tag_lower == known_lower:
            return True
        
        # Contains known username
        if known_lower in tag_lower:
            return True
        
        # Known username contains tag
        if tag_lower in known_lower:
            return True
        
        # Common variations
        variations = [
            known_lower,
            known_lower.replace('_', ''),
            known_lower.replace('.', ''),
            known_lower.replace('-', ''),
            f"@{known_lower}",
            f"official{known_lower}",
            f"real{known_lower}",
            f"its{known_lower}",
            f"the{known_lower}",
        ]
        
        return tag_lower in variations
    
    async def _extract_entities(
        self,
        hashtags: List[str],
        context: Optional[Dict]
    ) -> List[EntityMention]:
        """
        Extract associated entities from hashtags
        Companies, brands, organizations, people
        """
        entities = []
        
        # Known entity patterns
        entity_patterns = {
            'company': [
                'hiring', 'jobs', 'career', 'startup', 'company',
                'team', 'corporate', 'business', 'agency', 'studio',
                'overseas', 'international', 'global', 'solutions'
            ],
            'organization': [
                'police', 'government', 'ngo', 'foundation', 'institute',
                'academy', 'university', 'college', 'school', 'training'
            ],
            'brand': [
                'official', 'store', 'shop', 'products', 'services',
                'brand', 'marketing', 'launch', 'new'
            ]
        }
        
        for hashtag in hashtags:
            tag = hashtag.lower().replace('#', '')
            
            # Check for company indicators
            entity_type = self._detect_entity_type(tag, entity_patterns)
            
            if entity_type:
                entities.append(EntityMention(
                    name=tag,
                    type=entity_type,
                    confidence=self._calculate_entity_confidence(tag, entity_type),
                    source='hashtag',
                    context=self._extract_entity_context(tag, hashtags)
                ))
        
        # AI-powered entity extraction
        if context:
            ai_entities = await self._ai_extract_entities(hashtags, context)
            entities.extend(ai_entities)
        
        # Deduplicate
        seen = set()
        unique_entities = []
        for entity in entities:
            if entity.name not in seen:
                seen.add(entity.name)
                unique_entities.append(entity)
        
        return unique_entities

    async def _ai_extract_entities(self, hashtags: List[str], context: Dict) -> List[EntityMention]:
        """AI-powered entity extraction helper."""
        return []
    
    def _detect_entity_type(self, tag: str, patterns: Dict) -> Optional[str]:
        """
        Detect what type of entity a hashtag represents
        """
        for entity_type, indicators in patterns.items():
            for indicator in indicators:
                if indicator in tag:
                    return entity_type
        return None
    
    async def _analyze_personality(
        self,
        hashtags: List[str]
    ) -> List[PersonalityIndicator]:
        """
        Analyze personality traits from hashtags
        """
        indicators = []
        
        # Professional personality indicators
        professional_tags = {
            'hacker_enthusiast': ['hacking', 'hacker', 'cyber', 'security', 'redteam', 'pentest'],
            'developer': ['coding', 'developer', 'programming', 'software', 'webdev', 'appdev'],
            'designer': ['design', 'graphic', 'creative', 'art', 'illustration'],
            'entrepreneur': ['startup', 'business', 'founder', 'entrepreneur', 'ceo'],
            'student': ['student', 'learning', 'study', 'college', 'university'],
            'job_seeker': ['jobs', 'hiring', 'career', 'fresher', 'opportunity'],
        }
        
        for trait, keywords in professional_tags.items():
            score = sum(1 for h in hashtags if any(k in h.lower() for k in keywords))
            if score > 0:
                indicators.append(PersonalityIndicator(
                    category='professional',
                    trait=trait,
                    confidence=min(score / 5, 1.0),
                    evidence=[h for h in hashtags if any(k in h.lower() for k in keywords)]
                ))
        
        # Personal personality indicators
        personal_tags = {
            'family_oriented': ['family', 'brother', 'sister', 'mother', 'father', 'bhai', 'bhaichara'],
            'social': ['friend', 'party', 'celebration', 'birthday', 'fun'],
            'tech_lover': ['tech', 'gadget', 'laptop', 'coding', 'developer'],
            'creative_soul': ['creative', 'art', 'music', 'design', 'reels'],
            'privacy_conscious': ['privacy', 'security', 'encryption', 'opsec'],
        }
        
        for trait, keywords in personal_tags.items():
            score = sum(1 for h in hashtags if any(k in h.lower() for k in keywords))
            if score > 0:
                indicators.append(PersonalityIndicator(
                    category='personal',
                    trait=trait,
                    confidence=min(score / 5, 1.0),
                    evidence=[h for h in hashtags if any(k in h.lower() for k in keywords)]
                ))
        
        return indicators
    
    async def _extract_professional_info(self, hashtags: List[str]) -> List[Dict]:
        """
        Extract professional information from hashtags
        """
        professional_info = []
        
        # Skills detection
        skills = {
            'cybersecurity': ['cybersecurity', 'infosec', 'security', 'ethicalhacking', 'pentest'],
            'programming': ['python', 'javascript', 'java', 'coding', 'developer'],
            'cloud': ['aws', 'azure', 'gcp', 'cloud', 'devops'],
            'data': ['data', 'analytics', 'bigdata', 'machinelearning', 'ai'],
            'design': ['graphicdesign', 'videoediting', 'uiux', 'photoshop'],
            'marketing': ['seo', 'digitalmarketing', 'socialmedia', 'contentmarketing'],
        }
        
        detected_skills = []
        for skill, keywords in skills.items():
            if any(any(k in h.lower() for k in keywords) for h in hashtags):
                evidence = [h for h in hashtags if any(k in h.lower() for k in keywords)]
                detected_skills.append({
                    'skill': skill,
                    'confidence': len(evidence) / len(hashtags),
                    'evidence': evidence[:5]
                })
        
        if detected_skills:
            professional_info.append({
                'type': 'skills',
                'data': detected_skills
            })
        
        # Certifications
        cert_keywords = ['certification', 'certified', 'ceh', 'oscp', 'google', 'skillshop']
        certifications = [h for h in hashtags if any(k in h.lower() for k in cert_keywords)]
        if certifications:
            professional_info.append({
                'type': 'certifications',
                'data': certifications
            })
        
        # Employment status
        job_keywords = ['hiring', 'jobs', 'fresher', 'intern', 'remote', 'wfh', 'opportunity']
        job_tags = [h for h in hashtags if any(k in h.lower() for k in job_keywords)]
        if job_tags:
            professional_info.append({
                'type': 'employment_interest',
                'data': job_tags
            })
        
        return professional_info
    
    def _categorize_hashtags(self, hashtags: List[str]) -> Dict[str, List[str]]:
        """
        Categorize hashtags into groups
        """
        categorized = {category: [] for category in self.interest_categories}
        categorized['uncategorized'] = []
        
        for hashtag in hashtags:
            tag = hashtag.lower().replace('#', '')
            categorized_flag = False
            
            for category, keywords in self.interest_categories.items():
                if any(keyword in tag for keyword in keywords):
                    categorized[category].append(hashtag)
                    categorized_flag = True
                    break
            
            if not categorized_flag:
                categorized['uncategorized'].append(hashtag)
        
        return categorized
    
    def _extract_location_hints(self, hashtags: List[str]) -> List[str]:
        """
        Extract location hints from hashtags
        """
        location_hints = []
        
        # Indian cities
        indian_cities = [
            'delhi', 'mumbai', 'bangalore', 'hyderabad', 'chennai',
            'kolkata', 'pune', 'lucknow', 'jaipur', 'ahmedabad',
            'noida', 'gurgaon', 'chandigarh', 'indore', 'bhopal'
        ]
        
        for hashtag in hashtags:
            tag = hashtag.lower().replace('#', '')
            for city in indian_cities:
                if city in tag:
                    location_hints.append(city.title())
                    break
        
        return list(set(location_hints))
    
    def _extract_event_mentions(self, hashtags: List[str]) -> List[str]:
        """
        Extract event mentions
        """
        event_keywords = [
            'birthday', 'anniversary', 'celebration', 'party',
            'conference', 'workshop', 'meetup', 'hackathon',
            'festival', 'holiday', 'diwali', 'holi'
        ]
        
        events = []
        for hashtag in hashtags:
            tag = hashtag.lower().replace('#', '')
            for event in event_keywords:
                if event in tag:
                    events.append(hashtag)
                    break
        
        return events
    
    def _analyze_sentiment(self, hashtags: List[str]) -> List[str]:
        """
        Analyze sentiment from hashtags
        """
        sentiment_keywords = {
            'positive': ['love', 'happy', 'best', 'awesome', 'amazing', 'beautiful', '❤️', '💪'],
            'emotional': ['emotional', 'heartfelt', 'feel', 'yaar', 'mera', 'tu'],
            'motivational': ['motivation', 'success', 'goal', 'dream', 'hustle'],
            'humorous': ['funny', 'meme', 'joke', 'lol'],
        }
        
        sentiments = []
        for hashtag in hashtags:
            tag = hashtag.lower().replace('#', '')
            for sentiment, keywords in sentiment_keywords.items():
                if any(k in tag for k in keywords):
                    sentiments.append(sentiment)
                    break
        
        return list(set(sentiments))
    
    async def _ai_deep_analysis(
        self,
        analysis: HashtagAnalysis,
        context: Dict
    ) -> List[PersonalityIndicator]:
        """
        Use AI for deep analysis of hashtag patterns
        """
        prompt = f"""
        Analyze these hashtags from a social media profile and provide insights:
        
        Username: {context.get('username', 'Unknown')}
        Hashtags: {', '.join(context.get('hashtags', []))}
        
        Provide analysis in JSON format:
        1. Primary interests (top 3)
        2. Professional field
        3. Personality traits (3-5)
        4. Social connections indicated
        5. Geographic location hints
        6. Age group estimate
        7. Cultural indicators
        8. Potential associated accounts/brands
        
        Focus on Indian context and cybersecurity domain if relevant.
        """
        
        try:
            response = await self.ai_analyzer.analyze_text(prompt)
            # Parse AI response into PersonalityIndicator objects
            return self._parse_ai_insights(response)
        except:
            return []
    
    def _string_similarity(self, s1: str, s2: str) -> float:
        """Calculate string similarity"""
        from difflib import SequenceMatcher
        return SequenceMatcher(None, s1.lower(), s2.lower()).ratio()
    
    def _detect_platform(self, tag: str) -> Optional[str]:
        """Detect which platform a username might belong to"""
        platform_indicators = {
            'instagram': ['insta', 'ig', 'reels', 'instagram'],
            'twitter': ['tw', 'twitter', 'tweet'],
            'github': ['gh', 'github', 'dev'],
            'linkedin': ['li', 'linkedin', 'in'],
        }
        
        for platform, indicators in platform_indicators.items():
            if any(ind in tag.lower() for ind in indicators):
                return platform
        
        return None
    
    def _calculate_entity_confidence(self, tag: str, entity_type: str) -> float:
        """Calculate confidence of entity detection"""
        confidence = 0.5
        
        # Longer tags are more likely to be entities
        if len(tag) > 5:
            confidence += 0.2
        
        # Contains business indicators
        business_indicators = ['inc', 'llc', 'ltd', 'pvt', 'co', 'org', 'com']
        if any(ind in tag for ind in business_indicators):
            confidence += 0.2
        
        return min(confidence, 1.0)
    
    def _extract_entity_context(self, tag: str, all_hashtags: List[str]) -> List[str]:
        """Extract context around entity mention"""
        # Find related hashtags
        related = [h for h in all_hashtags if tag.lower() in h.lower()]
        return related[:5]
    
    def _parse_ai_insights(self, ai_response: str) -> List[PersonalityIndicator]:
        """Parse AI response into structured indicators"""
        # Implementation depends on AI response format
        return []
    
    