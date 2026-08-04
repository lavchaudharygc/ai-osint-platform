"""AI behavioral analysis and personality classification for Beta-v2.
Integrates Instagram post hashtags and captions into corpus with UP Cyber HQ focus.
"""

import json
import logging
from typing import Any, Dict, List, Tuple
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

_CATEGORIES = [
    {
        "name": "Cybersecurity & Incident Response",
        "keywords": ["cyber", "security", "hacking", "osint", "redteam", "red team", "ctf", "malware", "forensics", "incident", "ceh", "ciso", "pentest", "pentesting", "exploit", "vulnerability", "threat", "soc", "siem", "firewall", "investigator", "cybercrime", "crime", "police", "law enforcement", "lea", "uppolice", "infosec", "bugbounty", "reverse engineering"]
    },
    {
        "name": "Technology & Software Engineering",
        "keywords": ["tech", "coding", "developer", "programming", "python", "javascript", "react", "node", "ai", "ml", "linux", "github", "software", "engineer", "data", "cloud", "docker", "kubernetes", "api", "backend", "frontend", "devops", "open source", "database", "algorithm"]
    },
    {
        "name": "Law Enforcement & Governance",
        "keywords": ["police", "cop", "law", "enforcement", "investigation", "bureau", "crime", "justice", "court", "government", "public service", "ias", "ips", "modi", "police", "cybercell", "hq"]
    },
    {
        "name": "Business & Entrepreneurship",
        "keywords": ["business", "entrepreneur", "startup", "founder", "ceo", "company", "marketing", "sales", "strategy", "management", "investor", "venture", "capital"]
    },
    {
        "name": "Education & Student",
        "keywords": ["student", "study", "education", "school", "college", "university", "homework", "exam", "degree", "bachelor", "master", "phd", "iit", "nit"]
    },
    {
        "name": "Arts & Creativity",
        "keywords": ["art", "artist", "creative", "painting", "design", "photography", "music", "singer", "writing", "film", "cinema", "fashion", "model"]
    },
]


class AIAnalyzer:
    def __init__(self):
        self.api_key = settings.groq_api_key or settings.deepseek_api_key
        self.api_url = settings.groq_api_url if settings.groq_api_key else settings.deepseek_api_url
        self.model = settings.groq_model if settings.groq_api_key else settings.deepseek_model

    def is_configured(self) -> bool:
        return bool(self.api_key)

    @staticmethod
    def score_categories(corpus: str) -> List[Dict[str, Any]]:
        text = " " + corpus.lower() + " "
        results = []
        for cat in _CATEGORIES:
            matched = [kw for kw in cat["keywords"] if kw in text]
            results.append({"category": cat["name"], "hits": len(matched), "matched": matched})
        return sorted(results, key=lambda x: x["hits"], reverse=True)

    @staticmethod
    def confidence_from_hits(hits: int) -> Tuple[int, str]:
        if hits >= 8: return 95, "very_high"
        if hits >= 4: return 78, "high"
        if hits >= 2: return 55, "moderate"
        if hits >= 1: return 30, "low"
        return 0, "insufficient"

    async def analyze_personality(
        self,
        profiles: Dict[str, Any],
        dorking: Dict[str, Any] | None = None,
        ig_data: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Synthesize profile text + IG post hashtags & captions into structured AI personality JSON."""
        corpus_parts: List[str] = []

        # 1. Profile bios
        for p in profiles.values():
            if isinstance(p, dict) and (p.get("bio") or p.get("description")):
                corpus_parts.append(f"[{p.get('platform', 'profile')}] {p.get('bio') or p.get('description')}")

        # 2. Instagram Hashtags & Post Captions (CRITICAL USER REQUIREMENT)
        if ig_data and isinstance(ig_data, dict):
            tags = ig_data.get("post_hashtags") or []
            if tags:
                corpus_parts.append(f"[instagram-hashtags] {' '.join(tags)}")
            captions = ig_data.get("post_captions") or []
            for cap in captions[:5]:
                corpus_parts.append(f"[instagram-caption] {cap}")

        # 3. Organic search snippets
        if dorking and isinstance(dorking, dict):
            for hit in (dorking.get("results") or [])[:5]:
                if isinstance(hit, dict) and hit.get("snippet"):
                    corpus_parts.append(f"[dork] {hit.get('title', '')} - {hit.get('snippet', '')}")

        corpus = "\n".join(corpus_parts)[:4000]
        scored = self.score_categories(corpus)
        top = scored[0] if scored else None
        secondaries = [s for s in scored[1:] if s["hits"] >= 1][:2]

        if not corpus.strip() or not top or top["hits"] == 0:
            return {
                "summary": "Insufficient public data to classify this subject.",
                "traits": [], "interests": [], "tone": "unknown", "riskFlags": [],
                "primaryCategory": "Unable to Classify",
                "confidence": 0, "confidenceLabel": "insufficient",
                "evidence": [], "secondaryCategories": [],
                "platformCount": len(profiles),
            }

        pct, label = self.confidence_from_hits(top["hits"])

        ai_extras: Dict[str, Any] = {}
        if self.is_configured():
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(
                        self.api_url,
                        headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                        json={
                            "model": self.model,
                            "messages": [
                                {
                                    "role": "system",
                                    "content": (
                                        "You are a senior behavioral analyst for a Law Enforcement & Cyber Crime Operations Center. "
                                        "Given public OSINT profile text and Instagram hashtags, return ONLY raw JSON with keys: "
                                        "summary (1-2 sentences), traits (up to 5 short strings), interests (up to 5 short strings), "
                                        "tone (one word), riskFlags (array of {label, severity: 'low'|'medium'|'high'}). "
                                        "Base fields strictly on input text. Never invent. Never misclassify cybersecurity specialists as privacy advocates. "
                                        "Return raw JSON only, no markdown formatting."
                                    ),
                                },
                                {"role": "user", "content": corpus[:3000]},
                            ],
                            "temperature": 0.2,
                            "max_tokens": 400,
                            "response_format": {"type": "json_object"},
                        },
                    )
                if resp.status_code == 200:
                    raw = resp.json()["choices"][0]["message"]["content"]
                    parsed = json.loads(raw) if isinstance(raw, str) else raw
                    if isinstance(parsed, dict):
                        ai_extras = {
                            "summary": str(parsed.get("summary") or "")[:400],
                            "traits": [str(x) for x in (parsed.get("traits") or [])[:5]],
                            "interests": [str(x) for x in (parsed.get("interests") or [])[:5]],
                            "tone": str(parsed.get("tone") or "neutral"),
                            "riskFlags": [
                                {
                                    "label": str(f.get("label") or f)[:60],
                                    "severity": f.get("severity") if f.get("severity") in {"low", "medium", "high"} else "low",
                                }
                                for f in (parsed.get("riskFlags") or [])[:5]
                                if isinstance(f, dict)
                            ],
                        }
            except Exception as exc:
                logger.warning("AI personality API call failed: %s", exc)

        return {
            "summary": ai_extras.get("summary") or f"Public profile and hashtag signals align with {top['category']}.",
            "traits": ai_extras.get("traits") or ["OSINT Subject"],
            "interests": ai_extras.get("interests") or top["matched"][:5],
            "tone": ai_extras.get("tone") or "neutral",
            "riskFlags": ai_extras.get("riskFlags") or [],
            "primaryCategory": top["category"],
            "confidence": pct,
            "confidenceLabel": label,
            "evidence": top["matched"][:8],
            "secondaryCategories": [
                {
                    "category": s["category"],
                    "confidence": self.confidence_from_hits(s["hits"])[0],
                    "evidence": ", ".join(s["matched"][:3]),
                }
                for s in secondaries
            ],
            "platformCount": len(profiles),
        }
