# backend/app/models/intelligence_models.py

"""
Intelligence Models for Report Generation
"""

from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum

class IntelligenceSource(str, Enum):
    HASHTAG = "hashtag"
    CONTENT = "content"
    DORKING = "dorking"
    PLATFORM_SCRAPING = "platform_scraping"
    CTI_BOT = "cti_bot"
    REVERSE_LOOKUP = "reverse_lookup"
    AI_ANALYSIS = "ai_analysis"

class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class UsernameVariation(BaseModel):
    value: str
    confidence: float
    is_known_variation: bool
    source: str
    platform_hint: Optional[str] = None

class EntityMention(BaseModel):
    name: str
    type: str  # company, organization, brand, person
    confidence: float
    source: str
    context: List[str] = []

class PersonalityIndicator(BaseModel):
    category: str  # professional, personal
    trait: str
    confidence: float
    evidence: List[str] = []

class AssociatedAccount(BaseModel):
    username: str
    platform: str
    confidence: float
    source: str
    evidence: str = ""
    relationship: Optional[str] = None

class ProfileType(BaseModel):
    primary_type: str
    confidence: float
    description: str
    secondary_types: Dict[str, float] = {}
    ai_analysis: Optional[Any] = None
    professional_field: str = ""
    interests: List[str] = []
    risk_indicators: List[str] = []

class KeywordProfile(BaseModel):
    username_variations: List[str] = []
    interest_keywords: List[str] = []
    professional_keywords: List[str] = []
    associated_entities: List[str] = []
    location_keywords: List[str] = []
    profile_type_indicators: Dict[str, float] = {}

class HashtagIntelligence(BaseModel):
    source: str
    total_hashtags: int
    unique_hashtags: int
    potential_usernames: List[UsernameVariation] = []
    associated_entities: List[EntityMention] = []
    personality_indicators: List[PersonalityIndicator] = []
    professional_indicators: List[Dict] = []
    location_hints: List[str] = []
    event_mentions: List[str] = []
    sentiment_indicators: List[str] = []
    categorized_hashtags: Dict[str, List[str]] = {}

class ContentIntelligence(BaseModel):
    source: str
    emails: List[str] = []
    phone_numbers: List[str] = []
    mentioned_usernames: List[Dict] = []
    organizations: List[Dict] = []
    locations: List[str] = []
    job_titles: List[str] = []
    skills: List[str] = []
    education: List[Dict] = []
    urls: List[str] = []
    key_phrases: List[str] = []

class ReverseLookupResult(BaseModel):
    username: str
    timestamp: datetime
    keyword_profile: Optional[KeywordProfile] = None
    associated_accounts: List[AssociatedAccount] = []
    profile_type: Optional[ProfileType] = None
    intelligence_summary: Dict = {}

class ComprehensiveIntelligence(BaseModel):
    """Complete intelligence package for report generation"""
    investigation_id: str
    target_username: str
    timestamp: datetime = Field(default_factory=datetime.now)
    
    # Platform intelligence
    platform_results: Dict[str, Any] = {}
    
    # Hashtag intelligence
    hashtag_intelligence: Optional[HashtagIntelligence] = None
    
    # Content intelligence
    content_intelligence: Optional[ContentIntelligence] = None
    
    # Dorking intelligence
    dorking_intelligence: Dict[str, Any] = {}
    
    # CTI intelligence
    cti_intelligence: Dict[str, Any] = {}
    
    # Reverse lookup results
    reverse_lookup: Optional[ReverseLookupResult] = None
    
    # AI analysis
    ai_analysis: Dict[str, Any] = {}
    
    # Summary
    executive_summary: Dict[str, Any] = {}
    
    # Confidence scores
    confidence_scores: Dict[str, float] = {}
    
    class Config:
        arbitrary_types_allowed = True