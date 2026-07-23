# backend/app/services/report/enhanced_report_generator.py

"""
Enhanced Report Generator with Intelligence Integration
"""

import json
import math
from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path
import asyncio

from backend.schemas.intelligence_models import (
    ComprehensiveIntelligence,
    ReverseLookupResult,
    HashtagIntelligence,
    ContentIntelligence,
    AssociatedAccount
)
from backend.services.ai_analyzer import AIAnalyzer

class EnhancedReportGenerator:
    """
    Generates comprehensive reports with all intelligence data
    """

    _UNCLASSIFIED_PROFILE_VALUES = {
        "",
        "unknown",
        "unclassified",
        "not_classified",
        "insufficient_evidence",
    }
    
    def __init__(self):
        self.ai_analyzer = AIAnalyzer()
        
    async def generate_comprehensive_report(
        self,
        intelligence: ComprehensiveIntelligence
    ) -> Dict:
        """
        Generate a complete intelligence report
        """
        report = {
            "report_metadata": {
                "report_id": f"RPT-{intelligence.investigation_id}",
                "generated_at": datetime.now().isoformat(),
                "target_username": intelligence.target_username,
                "investigation_date": intelligence.timestamp.isoformat()
            },
            
            "executive_summary": await self._generate_executive_summary(intelligence),
            
            "profile_overview": self._generate_profile_overview(intelligence),
            
            "intelligence_sections": {
                "hashtag_intelligence": self._format_hashtag_intelligence(
                    intelligence.hashtag_intelligence
                ),
                "content_intelligence": self._format_content_intelligence(
                    intelligence.content_intelligence
                ),
                "dorking_discoveries": self._format_dorking_intelligence(
                    intelligence.dorking_intelligence
                ),
                "associated_accounts": self._format_associated_accounts(
                    intelligence.reverse_lookup
                ),
                "profile_classification": self._format_profile_classification(
                    intelligence.reverse_lookup
                ),
                "keyword_analysis": self._format_keyword_analysis(
                    intelligence.reverse_lookup
                ),
                "cti_intelligence": self._format_cti_intelligence(
                    intelligence.cti_intelligence
                )
            },
            
            "intelligence_summary": self._generate_intelligence_summary(intelligence),
            
            "confidence_assessment": intelligence.confidence_scores,
            
            "recommendations": await self._generate_recommendations(intelligence),
            
            "appendices": {
                "raw_hashtags": self._get_raw_hashtags(intelligence),
                "all_keywords": self._get_all_keywords(intelligence),
                "platform_details": intelligence.platform_results
            }
        }
        
        return report
    
    async def _generate_executive_summary(
        self,
        intelligence: ComprehensiveIntelligence
    ) -> Dict:
        """
        Generate executive summary
        """
        summary = {
            "target_identification": {
                "username": intelligence.target_username,
                "real_name": self._extract_real_name(intelligence),
                "aliases": self._extract_aliases(intelligence)
            },
            "profile_classification": {
                "type": self._get_profile_type(intelligence),
                "professional_field": self._get_professional_field(intelligence),
                "confidence": intelligence.confidence_scores.get("profile_type", 0)
            },
            "key_findings": {
                "total_platforms_found": len(intelligence.platform_results),
                "associated_accounts": len(
                    intelligence.reverse_lookup.associated_accounts 
                    if intelligence.reverse_lookup else []
                ),
                "organizations_linked": self._count_organizations(intelligence),
                "locations_identified": self._get_locations(intelligence),
                "risk_level": self._assess_risk_level(intelligence)
            },
            "contact_information": {
                "emails": self._extract_emails(intelligence),
                "phone_numbers": self._extract_phones(intelligence),
                "social_profiles": self._get_social_profiles(intelligence)
            }
        }
        
        return summary
    
    def _generate_profile_overview(
        self,
        intelligence: ComprehensiveIntelligence
    ) -> Dict:
        """
        Generate detailed profile overview
        """
        overview = {
            "identity": {
                "primary_username": intelligence.target_username,
                "known_aliases": [],
                "real_name": None,
                "name_confidence": 0
            },
            "professional_profile": {
                "current_role": None,
                "skills": [],
                "certifications": [],
                "experience_indicators": []
            },
            "personal_profile": {
                "interests": [],
                "hobbies": [],
                "personality_traits": [],
                "social_connections": []
            },
            "geographic_profile": {
                "primary_location": None,
                "associated_locations": [],
                "location_confidence": 0
            },
            "risk_profile": {
                "overall_risk": "LOW",
                "risk_factors": [],
                "sensitive_exposure": False
            }
        }
        
        # Populate from intelligence
        if intelligence.reverse_lookup:
            rl = intelligence.reverse_lookup
            if rl.profile_type:
                overview["professional_profile"]["current_role"] = rl.profile_type.description
                overview["personal_profile"]["interests"] = rl.profile_type.interests
            
            if rl.keyword_profile:
                overview["personal_profile"]["interests"].extend(
                    rl.keyword_profile.interest_keywords[:5]
                )
                overview["geographic_profile"]["associated_locations"] = \
                    rl.keyword_profile.location_keywords
        
        if intelligence.hashtag_intelligence:
            hi = intelligence.hashtag_intelligence
            overview["personal_profile"]["personality_traits"] = [
                p.trait for p in hi.personality_indicators
            ]
        
        if intelligence.content_intelligence:
            ci = intelligence.content_intelligence
            overview["identity"]["known_aliases"] = [
                m['username'] for m in ci.mentioned_usernames
            ]
            overview["professional_profile"]["skills"] = ci.skills
        
        return overview
    
    def _format_hashtag_intelligence(
        self,
        hashtag_intel: Optional[HashtagIntelligence]
    ) -> Dict:
        """
        Format hashtag intelligence for report
        """
        if not hashtag_intel:
            return {"status": "no_data"}
        
        return {
            "statistics": {
                "total_hashtags": hashtag_intel.total_hashtags,
                "unique_hashtags": hashtag_intel.unique_hashtags,
                "source": hashtag_intel.source
            },
            "key_discoveries": {
                "potential_usernames": [
                    {
                        "username": u.value,
                        "confidence": f"{u.confidence:.0%}",
                        "is_known_variation": u.is_known_variation
                    }
                    for u in hashtag_intel.potential_usernames[:10]
                ],
                "associated_entities": [
                    {
                        "name": e.name,
                        "type": e.type,
                        "confidence": f"{e.confidence:.0%}"
                    }
                    for e in hashtag_intel.associated_entities[:10]
                ],
                "personality_indicators": [
                    {
                        "trait": p.trait,
                        "category": p.category,
                        "confidence": f"{p.confidence:.0%}"
                    }
                    for p in hashtag_intel.personality_indicators
                ],
                "locations_hinted": hashtag_intel.location_hints,
                "events_mentioned": hashtag_intel.event_mentions
            },
            "categorized_hashtags": {
                category: tags[:10]  # Show top 10 per category
                for category, tags in hashtag_intel.categorized_hashtags.items()
                if tags
            }
        }
    
    def _format_content_intelligence(
        self,
        content_intel: Optional[ContentIntelligence]
    ) -> Dict:
        """
        Format content intelligence for report
        """
        if not content_intel:
            return {"status": "no_data"}
        
        return {
            "contact_information": {
                "emails_found": content_intel.emails,
                "phone_numbers": content_intel.phone_numbers,
                "urls": content_intel.urls[:10]
            },
            "associated_people": [
                {
                    "username": m['username'],
                    "relationship": m.get('relationship', 'unknown'),
                    "confidence": f"{m.get('confidence', 0):.0%}"
                }
                for m in content_intel.mentioned_usernames
            ],
            "organizations": [
                {
                    "name": org['name'],
                    "type": org.get('type', 'unknown'),
                    "confidence": f"{org.get('confidence', 0):.0%}"
                }
                for org in content_intel.organizations
            ],
            "professional_info": {
                "job_titles": content_intel.job_titles,
                "skills": content_intel.skills,
                "education": content_intel.education
            },
            "locations_mentioned": content_intel.locations
        }
    
    def _format_dorking_intelligence(
        self,
        dorking_intel: Dict
    ) -> Dict:
        """
        Format dorking discoveries for report
        """
        if not dorking_intel:
            return {"status": "no_data"}
        
        return {
            "discoveries": {
                "emails_found": dorking_intel.get('emails', []),
                "organizations_found": dorking_intel.get('organizations', []),
                "associated_usernames": dorking_intel.get('usernames', []),
                "locations": dorking_intel.get('locations', []),
                "key_phrases": dorking_intel.get('key_phrases', [])[:10]
            },
            "search_statistics": {
                "total_searches": dorking_intel.get('total_searches', 0),
                "successful_searches": dorking_intel.get('successful_searches', 0),
                "new_discoveries": len(dorking_intel.get('emails', [])) + 
                                  len(dorking_intel.get('organizations', []))
            }
        }
    
    def _format_associated_accounts(
        self,
        reverse_lookup: Optional[ReverseLookupResult]
    ) -> Dict:
        """
        Format associated accounts for report
        """
        if not reverse_lookup or not reverse_lookup.associated_accounts:
            return {"status": "no_associated_accounts_found"}
        
        return {
            "total_associated": len(reverse_lookup.associated_accounts),
            "accounts": [
                {
                    "username": account.username,
                    "platform": account.platform,
                    "confidence": f"{account.confidence:.0%}",
                    "source": account.source,
                    "evidence": account.evidence[:200] if account.evidence else ""
                }
                for account in reverse_lookup.associated_accounts
            ],
            "relationship_analysis": self._analyze_relationships(
                reverse_lookup.associated_accounts
            )
        }
    
    def _format_profile_classification(
        self,
        reverse_lookup: Optional[ReverseLookupResult]
    ) -> Dict:
        """
        Format profile classification for report
        """
        if (
            not reverse_lookup
            or not self._is_classified_profile(reverse_lookup.profile_type)
        ):
            return {"status": "not_classified"}
        
        pt = reverse_lookup.profile_type
        
        return {
            "primary_classification": {
                "type": pt.primary_type,
                "confidence": f"{pt.confidence:.0%}",
                "description": pt.description
            },
            "secondary_classifications": {
                type_: f"{conf:.0%}"
                for type_, conf in pt.secondary_types.items()
            },
            "professional_field": pt.professional_field,
            "interests": pt.interests,
            "risk_assessment": {
                "indicators": pt.risk_indicators,
                "overall_risk": "HIGH" if len(pt.risk_indicators) > 2 
                               else "MEDIUM" if len(pt.risk_indicators) > 1 
                               else "LOW"
            },
            "ai_analysis": str(pt.ai_analysis) if pt.ai_analysis else None
        }
    
    def _format_keyword_analysis(
        self,
        reverse_lookup: Optional[ReverseLookupResult]
    ) -> Dict:
        """
        Format keyword analysis for report
        """
        if not reverse_lookup or not reverse_lookup.keyword_profile:
            return {"status": "no_keyword_data"}
        
        kp = reverse_lookup.keyword_profile
        
        return {
            "username_variations": {
                "similar_to_username": kp.username_variations[:20],
                "count": len(kp.username_variations)
            },
            "interest_keywords": {
                "different_from_username": kp.interest_keywords[:20],
                "count": len(kp.interest_keywords),
                "categories": self._categorize_interest_keywords(kp.interest_keywords)
            },
            "professional_keywords": {
                "keywords": kp.professional_keywords[:20],
                "count": len(kp.professional_keywords)
            },
            "associated_entities": {
                "entities": kp.associated_entities,
                "count": len(kp.associated_entities)
            },
            "locations": kp.location_keywords
        }
    
    def _format_cti_intelligence(self, cti_intel: Dict) -> Dict:
        """
        Format CTI intelligence for report
        """
        if not cti_intel:
            return {"status": "no_cti_data"}
        
        # Simplify CTI data for report
        return {
            "bots_queried": cti_intel.get('bots_queried', 0),
            "successful_lookups": cti_intel.get('bots_successful', 0),
            "key_findings": cti_intel.get('correlated_data', {}),
            "reliability": f"{cti_intel.get('reliability_score', 0):.0%}"
        }
    
    def _generate_intelligence_summary(
        self,
        intelligence: ComprehensiveIntelligence
    ) -> Dict:
        """
        Generate overall intelligence summary
        """
        if intelligence.reverse_lookup:
            return intelligence.reverse_lookup.intelligence_summary
        
        return {
            "status": "insufficient_data",
            "message": "Not enough data for comprehensive intelligence summary"
        }
    
    async def _generate_recommendations(
        self,
        intelligence: ComprehensiveIntelligence
    ) -> List[Dict]:
        """
        Generate investigation recommendations
        """
        recommendations = []
        
        # Based on findings, suggest next steps
        if intelligence.reverse_lookup:
            rl = intelligence.reverse_lookup
            
            if rl.associated_accounts:
                recommendations.append({
                    "priority": "HIGH",
                    "action": "Investigate associated accounts",
                    "details": f"{len(rl.associated_accounts)} associated accounts found",
                    "accounts": [a.username for a in rl.associated_accounts[:5]]
                })
            
            if rl.keyword_profile:
                if rl.keyword_profile.username_variations:
                    recommendations.append({
                        "priority": "HIGH",
                        "action": "Search for username variations",
                        "details": f"{len(rl.keyword_profile.username_variations)} variations found",
                        "variations": rl.keyword_profile.username_variations[:10]
                    })
                
                if rl.keyword_profile.associated_entities:
                    recommendations.append({
                        "priority": "MEDIUM",
                        "action": "Investigate linked organizations",
                        "entities": rl.keyword_profile.associated_entities
                    })
        
        # AI-generated recommendations
        try:
            ai_recs = await self.ai_analyzer.generate_recommendations(intelligence)
            recommendations.extend(ai_recs)
        except:
            pass
        
        return recommendations
    
    # Helper methods
    @classmethod
    def _is_classified_profile(cls, profile_type: object) -> bool:
        """Return whether a profile type contains a usable classification."""
        if not profile_type:
            return False

        primary_type = str(getattr(profile_type, "primary_type", "") or "")
        normalized_type = primary_type.strip().lower().replace("-", "_").replace(" ", "_")
        if normalized_type in cls._UNCLASSIFIED_PROFILE_VALUES:
            return False

        try:
            confidence = float(getattr(profile_type, "confidence", 0) or 0)
        except (TypeError, ValueError):
            return False

        return math.isfinite(confidence) and confidence > 0

    def _extract_real_name(self, intelligence: ComprehensiveIntelligence) -> Optional[str]:
        """Extract real name from intelligence"""
        if intelligence.content_intelligence:
            # Look for names in content
            for org in intelligence.content_intelligence.organizations:
                if org.get('type') == 'person':
                    return org['name']
        return None
    
    def _extract_aliases(self, intelligence: ComprehensiveIntelligence) -> List[str]:
        """Extract aliases/usernames"""
        aliases = []
        if intelligence.reverse_lookup and intelligence.reverse_lookup.keyword_profile:
            aliases.extend(intelligence.reverse_lookup.keyword_profile.username_variations[:5])
        return aliases
    
    def _get_profile_type(self, intelligence: ComprehensiveIntelligence) -> str:
        """Get profile type"""
        if intelligence.reverse_lookup and self._is_classified_profile(
            intelligence.reverse_lookup.profile_type
        ):
            return intelligence.reverse_lookup.profile_type.primary_type
        return "Unknown"
    
    def _get_professional_field(self, intelligence: ComprehensiveIntelligence) -> str:
        """Get professional field"""
        if intelligence.reverse_lookup and self._is_classified_profile(
            intelligence.reverse_lookup.profile_type
        ):
            professional_field = str(
                intelligence.reverse_lookup.profile_type.professional_field or ""
            ).strip()
            normalized_field = professional_field.lower().replace("-", "_").replace(" ", "_")
            if normalized_field not in self._UNCLASSIFIED_PROFILE_VALUES:
                return professional_field
        return "Unknown"
    
    def _count_organizations(self, intelligence: ComprehensiveIntelligence) -> int:
        """Count organizations"""
        count = 0
        if intelligence.content_intelligence:
            count += len(intelligence.content_intelligence.organizations)
        if intelligence.reverse_lookup and intelligence.reverse_lookup.keyword_profile:
            count += len(intelligence.reverse_lookup.keyword_profile.associated_entities)
        return count
    
    def _get_locations(self, intelligence: ComprehensiveIntelligence) -> List[str]:
        """Get locations"""
        locations = []
        if intelligence.hashtag_intelligence:
            locations.extend(intelligence.hashtag_intelligence.location_hints)
        if intelligence.content_intelligence:
            locations.extend(intelligence.content_intelligence.locations)
        return list(set(locations))
    
    def _assess_risk_level(self, intelligence: ComprehensiveIntelligence) -> str:
        """Assess overall risk level"""
        if intelligence.reverse_lookup and intelligence.reverse_lookup.profile_type:
            risk_indicators = intelligence.reverse_lookup.profile_type.risk_indicators
            if any('HIGH' in r for r in risk_indicators):
                return "HIGH"
            elif any('MEDIUM' in r for r in risk_indicators):
                return "MEDIUM"
        return "LOW"
    
    def _extract_emails(self, intelligence: ComprehensiveIntelligence) -> List[str]:
        """Extract all emails"""
        emails = []
        if intelligence.content_intelligence:
            emails.extend(intelligence.content_intelligence.emails)
        return list(set(emails))
    
    def _extract_phones(self, intelligence: ComprehensiveIntelligence) -> List[str]:
        """Extract all phone numbers"""
        phones = []
        if intelligence.content_intelligence:
            phones.extend(intelligence.content_intelligence.phone_numbers)
        return list(set(phones))
    
    def _get_social_profiles(self, intelligence: ComprehensiveIntelligence) -> List[str]:
        """Get social media profile URLs"""
        profiles = []
        if intelligence.content_intelligence:
            profiles.extend(intelligence.content_intelligence.urls)
        return profiles[:10]
    
    def _get_raw_hashtags(self, intelligence: ComprehensiveIntelligence) -> List[str]:
        """Get raw hashtags"""
        if intelligence.hashtag_intelligence:
            return list(intelligence.hashtag_intelligence.categorized_hashtags.get(
                'uncategorized', []
            ))
        return []
    
    def _get_all_keywords(self, intelligence: ComprehensiveIntelligence) -> List[str]:
        """Get all keywords"""
        keywords = []
        if intelligence.reverse_lookup and intelligence.reverse_lookup.keyword_profile:
            kp = intelligence.reverse_lookup.keyword_profile
            keywords.extend(kp.username_variations)
            keywords.extend(kp.interest_keywords)
            keywords.extend(kp.professional_keywords)
        return list(set(keywords))
    
    def _analyze_relationships(self, accounts: List[AssociatedAccount]) -> Dict:
        """Analyze relationships between accounts"""
        if not accounts:
            return {}
        
        platforms = {}
        for account in accounts:
            if account.platform not in platforms:
                platforms[account.platform] = 0
            platforms[account.platform] += 1
        
        return {
            "platform_distribution": platforms,
            "most_common_platform": max(platforms, key=platforms.get) if platforms else None,
            "total_unique_accounts": len(accounts)
        }
    
    def _categorize_interest_keywords(self, keywords: List[str]) -> Dict:
        """Categorize interest keywords"""
        categories = {
            'technology': [],
            'security': [],
            'creative': [],
            'business': [],
            'personal': [],
            'other': []
        }
        
        tech_keywords = ['cyber', 'security', 'hack', 'code', 'dev', 'tech', 'ai', 'data']
        creative_keywords = ['design', 'art', 'video', 'photo', 'music', 'creative']
        business_keywords = ['business', 'startup', 'marketing', 'sales', 'job', 'career']
        personal_keywords = ['family', 'friend', 'love', 'life', 'bhai', 'birthday']
        
        for keyword in keywords:
            kw = keyword.lower()
            if any(k in kw for k in tech_keywords):
                categories['technology'].append(keyword)
            elif any(k in kw for k in creative_keywords):
                categories['creative'].append(keyword)
            elif any(k in kw for k in business_keywords):
                categories['business'].append(keyword)
            elif any(k in kw for k in personal_keywords):
                categories['personal'].append(keyword)
            else:
                categories['other'].append(keyword)
        
        return {k: v for k, v in categories.items() if v}
