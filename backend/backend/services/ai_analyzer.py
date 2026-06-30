"""AI-powered profile correlation and risk analysis."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
import json
import re

import httpx

from backend.core.config import settings
from backend.services.training_dataset_service import get_training_dataset_service

REPO_ROOT = Path(__file__).resolve().parents[2]


class AIAnalyzer:
    """Groq-backed analyzer with deterministic fallback behavior."""

    def __init__(self) -> None:
        self.api_key = settings.groq_api_key
        self.api_url = settings.groq_api_url
        self.model = settings.groq_model
        self.training_examples = self._load_training_examples()
        self.system_prompt = self._load_system_prompt()
        self.correlation_rules = self._load_correlation_rules()

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _load_training_examples(self) -> list[dict[str, Any]]:
        jsonl_path = REPO_ROOT / "docs" / "ai-prompts" / "ai_training_examples.jsonl"
        if jsonl_path.exists():
            examples = []
            with jsonl_path.open(encoding="utf-8") as file_obj:
                for line in file_obj:
                    if line.strip():
                        examples.append(json.loads(line))
            return examples
        return get_training_dataset_service().load_examples()

    def _load_system_prompt(self) -> str:
        prompt_path = REPO_ROOT / "docs" / "ai-prompts" / "ai_prompts_v1.0.md"
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        return (
            "You are a senior OSINT investigator. Analyze public profile signals and respond with "
            "DECISION, CONFIDENCE, REASONS, and NEXT STEPS. Never claim certainty without evidence."
        )

    def _load_correlation_rules(self) -> str:
        rules_path = REPO_ROOT / "docs" / "methodology" / "correlation_rules_v1.0.md"
        if rules_path.exists():
            return rules_path.read_text(encoding="utf-8")
        return """
Email/phone match = CONFIRMED (95%+)
Exact username + same name = HIGH (85%+)
Same username, different name = MEDIUM (50-70%)
Different usernames, similar bio = MODERATE (40-60%)
Only first name matches = LOW (<30%)
Conflicting locations = reduce confidence
""".strip()

    async def analyze_correlation(self, primary_profile: dict[str, Any], discovered_profiles: list[dict[str, Any]]) -> dict[str, Any]:
        if not self.is_configured():
            return self._fallback_correlation(primary_profile, discovered_profiles, "missing GROQ_API_KEY")

        messages = self._build_correlation_messages(primary_profile, discovered_profiles)
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    self.api_url,
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json={"model": self.model, "messages": messages, "temperature": 0.3, "max_tokens": 1000},
                )
            if response.status_code != 200:
                return {"success": False, "error": f"AI API returned status {response.status_code}", "details": response.text[:200]}
            ai_response = response.json()["choices"][0]["message"]["content"]
            return {
                "success": True,
                "raw_response": ai_response,
                "parsed": self._parse_ai_response(ai_response),
                "model_used": self.model,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        except httpx.TimeoutException:
            return {"success": False, "error": "AI API timeout - please try again"}
        except httpx.HTTPError as exc:
            return {"success": False, "error": str(exc)}

    async def assess_risk(self, profile_data: dict[str, Any]) -> dict[str, Any]:
        if not self.is_configured():
            return self._fallback_risk(profile_data, "missing GROQ_API_KEY")

        prompt = self._build_risk_prompt(profile_data)
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    self.api_url,
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": "You are a cyber threat analyst for lawful OSINT investigations."},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.3,
                        "max_tokens": 500,
                    },
                )
            if response.status_code == 200:
                return {"success": True, "analysis": response.json()["choices"][0]["message"]["content"]}
            return {"success": False, "error": f"AI API returned status {response.status_code}", "details": response.text[:200]}
        except httpx.HTTPError as exc:
            return {"success": False, "error": str(exc)}

    def _build_correlation_messages(self, primary_profile: dict[str, Any], discovered_profiles: list[dict[str, Any]]) -> list[dict[str, str]]:
        messages = [{"role": "system", "content": self.system_prompt[:2000]}]
        for example in self.training_examples[:5]:
            if example.get("system"):
                messages.append({"role": "system", "content": str(example["system"])[:500]})
            if example.get("user"):
                messages.append({"role": "user", "content": str(example["user"])})
            if example.get("assistant"):
                messages.append({"role": "assistant", "content": str(example["assistant"])})
        messages.append({"role": "user", "content": self._build_correlation_query(primary_profile, discovered_profiles)})
        return messages

    def _build_correlation_query(self, primary_profile: dict[str, Any], discovered_profiles: list[dict[str, Any]]) -> str:
        discovered_summary = "\n".join(
            f"{index}. Platform: {profile.get('platform')} | Username: {profile.get('username')} | URL: {profile.get('url')} | Exists: {profile.get('exists')}"
            for index, profile in enumerate(discovered_profiles, 1)
        )
        return f"""
INSTAGRAM PROFILE:
Username: {primary_profile.get('username')}
Full Name: {primary_profile.get('full_name', 'N/A')}
Bio: {str(primary_profile.get('bio', 'N/A'))[:200]}
Followers: {primary_profile.get('followers') or primary_profile.get('follower_count', 'N/A')}
Posts: {primary_profile.get('posts_count') or primary_profile.get('post_count', 'N/A')}
Business Category: {primary_profile.get('business_category', 'N/A')}

DISCOVERED PROFILES:
{discovered_summary}

CORRELATION RULES:
{self.correlation_rules}

RESPOND IN THIS EXACT FORMAT:
DECISION: [DEFINITELY SAME / VERY LIKELY SAME / PROBABLY SAME / POSSIBLY SAME / UNLIKELY SAME / DEFINITELY DIFFERENT]
CONFIDENCE: [0-100%]
REASONS:
- [reason 1]
NEXT STEPS:
- [step 1]
""".strip()

    def _build_risk_prompt(self, profile_data: dict[str, Any]) -> str:
        return f"""
Assess the risk level of this social media profile for investigation purposes.
Username: {profile_data.get('username')}
Full Name: {profile_data.get('full_name', 'N/A')}
Bio: {str(profile_data.get('bio', 'N/A'))[:300]}
Followers: {profile_data.get('followers') or profile_data.get('follower_count', 'N/A')}
Following: {profile_data.get('following') or profile_data.get('following_count', 'N/A')}
Is Verified: {profile_data.get('is_verified', False)}
Account Type: {profile_data.get('business_category', 'Personal')}

Return:
RISK LEVEL: [LOW / MEDIUM / HIGH / CRITICAL]
RISK SCORE: [0-100]
INDICATORS FOUND:
- [indicator]
RECOMMENDATIONS:
- [recommendation]
""".strip()

    def _parse_ai_response(self, response_text: str) -> dict[str, Any]:
        result: dict[str, Any] = {"decision": "UNKNOWN", "confidence": 0, "reasons": [], "next_steps": []}
        current_section = None
        for line in response_text.splitlines():
            line = line.strip()
            if line.startswith("DECISION:"):
                result["decision"] = line.replace("DECISION:", "", 1).strip()
            elif line.startswith("CONFIDENCE:"):
                confidence_text = re.sub(r"[^0-9]", "", line.replace("CONFIDENCE:", "", 1))
                result["confidence"] = int(confidence_text) if confidence_text else 50
            elif line.startswith("REASONS:"):
                current_section = "reasons"
            elif line.startswith("NEXT STEPS:"):
                current_section = "next_steps"
            elif line.startswith("-") and current_section:
                result[current_section].append(line.replace("-", "", 1).strip())
        return result

    def _fallback_correlation(self, primary_profile: dict[str, Any], discovered_profiles: list[dict[str, Any]], reason: str) -> dict[str, Any]:
        positive_matches = [profile for profile in discovered_profiles if profile.get("exists")]
        confidence = min(95, 35 + (len(positive_matches) * 10))
        return {
            "success": False,
            "status": "not_configured",
            "reason": reason,
            "parsed": {
                "decision": "PROBABLY SAME" if confidence >= 60 else "POSSIBLY SAME",
                "confidence": confidence,
                "reasons": [f"{len(positive_matches)} public username matches found"],
                "next_steps": ["Configure GROQ_API_KEY for full AI analysis", "Manually verify profile photos, bios, and linked URLs"],
            },
            "model_used": "rules_fallback",
            "training_context": get_training_dataset_service().build_correlation_context(len(positive_matches)),
        }

    def _fallback_risk(self, profile_data: dict[str, Any], reason: str) -> dict[str, Any]:
        return {
            "success": False,
            "status": "not_configured",
            "reason": reason,
            "analysis": "Configure GROQ_API_KEY for AI risk assessment.",
            "parsed": {"risk_level": "UNKNOWN", "risk_score": 0, "indicators": [], "recommendations": []},
        }
