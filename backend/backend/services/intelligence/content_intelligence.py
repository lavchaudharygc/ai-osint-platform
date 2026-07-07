# backend/app/services/intelligence/content_intelligence.py

"""
Content Intelligence Extractor
Extracts intelligence from post content, bios, and Google dorking results
"""

import re
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime
import asyncio

from backend.services.ai_analyzer import AIAnalyzer

@dataclass
class ContentIntelligence:
    """Intelligence extracted from content analysis"""
    source: str
    
    # Extracted emails
    emails: List[str] = field(default_factory=list)
    
    # Extracted phone numbers
    phone_numbers: List[str] = field(default_factory=list)
    
    # Extracted usernames (@mentions)
    mentioned_usernames: List[Dict] = field(default_factory=list)
    
    # Extracted organizations/companies
    organizations: List[Dict] = field(default_factory=list)
    
    # Extracted locations
    locations: List[str] = field(default_factory=list)
    
    # Extracted job titles/roles
    job_titles: List[str] = field(default_factory=list)
    
    # Extracted skills
    skills: List[str] = field(default_factory=list)
    
    # Extracted education
    education: List[Dict] = field(default_factory=list)
    
    # Extracted URLs
    urls: List[str] = field(default_factory=list)
    
    # Key phrases
    key_phrases: List[str] = field(default_factory=list)
    
    # Named entities
    named_entities: List[Dict] = field(default_factory=list)

class ContentIntelligenceExtractor:
    """
    Extracts structured intelligence from unstructured content
    """
    
    def __init__(self):
        self.ai_analyzer = AIAnalyzer()
        
        # Regex patterns
        self.email_pattern = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
        self.phone_pattern = re.compile(r'[\+\(]?[1-9][0-9 .\-\(\)]{8,}[0-9]')
        self.url_pattern = re.compile(r'https?://[^\s<>"]+|www\.[^\s<>"]+')
        self.mention_pattern = re.compile(r'@([a-zA-Z0-9._]+)')
        self.hashtag_pattern = re.compile(r'#([a-zA-Z0-9_]+)')
        
        # Location patterns
        self.indian_cities = [
            'Delhi', 'Mumbai', 'Bangalore', 'Hyderabad', 'Chennai',
            'Kolkata', 'Pune', 'Lucknow', 'Jaipur', 'Ahmedabad',
            'Noida', 'Gurgaon', 'Chandigarh', 'Indore', 'Bhopal',
            'Amroha', 'Meerut', 'Agra', 'Varanasi', 'Kanpur'
        ]
        
        # Organization indicators
        self.org_indicators = [
            'Police', 'University', 'College', 'Institute', 'Academy',
            'Company', 'Ltd', 'Pvt', 'Inc', 'Corporation', 'Studio',
            'Agency', 'Foundation', 'NGO', 'Startup', 'Overseas',
            'International', 'School', 'Hospital', 'Bank'
        ]
        
    async def extract_from_content(
        self,
        content: str,
        source: str,
        context: Optional[Dict] = None
    ) -> ContentIntelligence:
        """
        Extract intelligence from any text content
        """
        intelligence = ContentIntelligence(source=source)
        
        # Extract structured data
        intelligence.emails = self._extract_emails(content)
        intelligence.phone_numbers = self._extract_phones(content)
        intelligence.urls = self._extract_urls(content)
        intelligence.mentioned_usernames = self._extract_mentions(content, context)
        intelligence.organizations = self._extract_organizations(content)
        intelligence.locations = self._extract_locations(content)
        intelligence.job_titles = self._extract_job_titles(content)
        intelligence.skills = self._extract_skills(content)
        intelligence.education = self._extract_education(content)
        
        # AI-powered extraction
        if context:
            ai_intel = await self._ai_extract(content, context)
            self._merge_intelligence(intelligence, ai_intel)
        
        return intelligence
    
    def _extract_emails(self, content: str) -> List[str]:
        """Extract email addresses"""
        emails = self.email_pattern.findall(content)
        return list(set(emails))
    
    def _extract_phones(self, content: str) -> List[str]:
        """Extract phone numbers"""
        phones = self.phone_pattern.findall(content)
        # Filter valid Indian numbers
        valid_phones = [p for p in phones if len(re.sub(r'[^\d]', '', p)) >= 10]
        return list(set(valid_phones))
    
    def _extract_urls(self, content: str) -> List[str]:
        """Extract URLs"""
        urls = self.url_pattern.findall(content)
        return list(set(urls))
    
    def _extract_mentions(
        self,
        content: str,
        context: Optional[Dict]
    ) -> List[Dict]:
        """
        Extract @mentions and determine relationship
        """
        mentions = self.mention_pattern.findall(content)
        known_username = context.get('username', '') if context else ''
        
        mention_data = []
        for mention in mentions:
            if mention.lower() != known_username.lower():
                # Determine if associated account
                relationship = self._determine_relationship(mention, known_username, content)
                
                mention_data.append({
                    'username': mention,
                    'relationship': relationship,
                    'confidence': 0.7 if relationship != 'unknown' else 0.3
                })
        
        return mention_data
    
    def _determine_relationship(
        self,
        mention: str,
        known_username: str,
        content: str
    ) -> str:
        """
        Determine relationship between mentioned user and target
        """
        content_lower = content.lower()
        
        # Check for relationship indicators
        relationship_indicators = {
            'colleague': ['team', 'colleague', 'coworker', 'work', 'company', 'together'],
            'friend': ['friend', 'brother', 'bhai', 'buddy', 'bhaichara', 'brotherhood'],
            'family': ['family', 'brother', 'sister', 'cousin', 'relative'],
            'business_partner': ['partner', 'cofounder', 'business', 'startup'],
            'employee': ['hiring', 'intern', 'employee', 'team member', 'reporting'],
            'mentor': ['mentor', 'guide', 'teacher', 'guru', 'sir'],
            'student': ['student', 'learning', 'training', 'course'],
        }
        
        for relationship, keywords in relationship_indicators.items():
            if any(k in content_lower for k in keywords):
                return relationship
        
        return 'associated'  # Default for close interactions
    
    def _extract_organizations(self, content: str) -> List[Dict]:
        """
        Extract organization names
        """
        organizations = []
        
        # Look for organization indicators
        for indicator in self.org_indicators:
            pattern = re.compile(
                rf'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:{indicator})',
                re.IGNORECASE
            )
            matches = pattern.findall(content)
            
            for match in matches:
                organizations.append({
                    'name': match.strip(),
                    'type': indicator.lower(),
                    'confidence': 0.6
                })
        
        # Look for company names in hashtags
        hashtags = self.hashtag_pattern.findall(content)
        company_hashtags = [h for h in hashtags if any(
            ind in h.lower() for ind in ['official', 'team', 'co', 'inc', 'studio']
        )]
        
        for hashtag in company_hashtags:
            organizations.append({
                'name': hashtag.replace('_', ' ').title(),
                'type': 'hashtag_mention',
                'confidence': 0.4
            })
        
        return organizations
    
    def _extract_locations(self, content: str) -> List[str]:
        """Extract location mentions"""
        locations = []
        
        for city in self.indian_cities:
            if city.lower() in content.lower():
                locations.append(city)
        
        # Look for "in <location>" patterns
        location_pattern = re.compile(r'(?:in|at|from|near)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)')
        matches = location_pattern.findall(content)
        locations.extend(matches)
        
        return list(set(locations))
    
    def _extract_job_titles(self, content: str) -> List[str]:
        """Extract job titles and roles"""
        job_titles = []
        
        title_patterns = [
            r'(?:Cyber\s+)?(?:Crime\s+)?Investigator',
            r'(?:Ethical\s+)?Hacker',
            r'(?:Security\s+)?Analyst',
            r'(?:Security\s+)?Engineer',
            r'(?:Security\s+)?Researcher',
            r'(?:Software\s+)?(?:Engineer|Developer)',
            r'(?:Graphic\s+)?Designer',
            r'(?:Video\s+)?Editor',
            r'(?:SEO|Marketing)\s+Specialist',
            r'(?:Red|Blue)\s+Team',
            r'Pentester',
            r'Intern',
            r'Fresher',
            r'Student',
            r'Founder',
            r'CEO',
            r'CTO',
        ]
        
        for pattern in title_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            job_titles.extend(matches)
        
        return list(set(job_titles))
    
    def _extract_skills(self, content: str) -> List[str]:
        """Extract skills from content"""
        skills = []
        
        skill_keywords = [
            'OSINT', 'Python', 'JavaScript', 'Java', 'C++',
            'CEH', 'OSCP', 'Security+', 'CISSP',
            'Pentesting', 'Vulnerability Assessment',
            'Network Security', 'Web Security', 'Cloud Security',
            'Digital Forensics', 'Incident Response',
            'Google Analytics', 'SEO', 'Content Marketing',
            'Video Editing', 'Graphic Design', 'UI/UX',
            'Ethical Hacking', 'Red Teaming', 'Blue Teaming',
            'Threat Intelligence', 'Malware Analysis',
            'Encryption', 'Cryptography', 'Blockchain'
        ]
        
        for skill in skill_keywords:
            if skill.lower() in content.lower():
                skills.append(skill)
        
        return skills
    
    def _extract_education(self, content: str) -> List[Dict]:
        """Extract education information"""
        education = []
        
        # College/University patterns
        edu_patterns = [
            r'(?:B\.?Tech|M\.?Tech|B\.?E|M\.?E|B\.?Sc|M\.?Sc|BCA|MCA|MBA)',
            r'(?:Bachelor|Master)(?:\s+of\s+\w+)?',
            r'(?:University|College|Institute)\s+of\s+\w+',
        ]
        
        for pattern in edu_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches:
                education.append({
                    'qualification': match,
                    'confidence': 0.5
                })
        
        return education
    
    async def _ai_extract(
        self,
        content: str,
        context: Dict
    ) -> Dict:
        """
        Use AI to extract additional intelligence
        """
        prompt = f"""
        Extract structured information from this social media content:
        
        Content: {content[:1000]}
        Known Username: {context.get('username', '')}
        
        Extract and return JSON:
        1. Real name (if mentioned)
        2. Associated accounts/people
        3. Organizations/companies
        4. Locations
        5. Job/role
        6. Skills
        7. Contact information
        8. Key relationships
        9. Sentiment
        10. Any other intelligence
        
        Focus on accuracy and only extract if confident.
        """
        
        try:
            response = await self.ai_analyzer.analyze_text(prompt)
            return self._parse_ai_extraction(response)
        except:
            return {}
    
    def _merge_intelligence(
        self,
        intelligence: ContentIntelligence,
        ai_intel: Dict
    ):
        """Merge AI-extracted intelligence"""
        if not ai_intel:
            return
        
        # Merge new findings
        for key, value in ai_intel.items():
            if hasattr(intelligence, key):
                existing = getattr(intelligence, key)
                if isinstance(existing, list) and isinstance(value, list):
                    existing.extend(value)
                    setattr(intelligence, key, list(set(existing)))
    
    def _parse_ai_extraction(self, ai_response: str) -> Dict:
        """Parse AI extraction response"""
        # Implementation depends on AI response format
        import json
        try:
            return json.loads(ai_response)
        except:
            return {}
        
        