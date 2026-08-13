"""RocketReach API Service for candidate contact discovery (email & phone numbers)."""

import logging
import httpx
from typing import Dict, Any, List
from app.config import settings

logger = logging.getLogger(__name__)

class RocketReachService:
    """Queries RocketReach API (v2) to resolve emails and phone numbers for LinkedIn candidates."""

    def __init__(self):
        self.api_key = settings.rocketreach_api_key
        self.base_url = "https://api.rocketreach.co/api/v2/person/lookup"

    async def lookup_by_linkedin_url(self, linkedin_url: str) -> Dict[str, Any]:
        if not self.api_key or not linkedin_url:
            return {"success": False, "configured": bool(self.api_key), "emails": [], "phones": []}

        # Normalize input (URL or handle) to standard LinkedIn profile URL
        formatted_url = linkedin_url.strip()
        if "linkedin.com/in/" in formatted_url:
            handle = formatted_url.split("linkedin.com/in/")[-1].strip("/").split("?")[0]
            formatted_url = f"https://www.linkedin.com/in/{handle}/"
        elif not formatted_url.startswith("http"):
            handle = formatted_url.strip("/@").split("?")[0]
            formatted_url = f"https://www.linkedin.com/in/{handle}/"

        params = {"linkedin_url": formatted_url}
        headers = {
            "accept": "application/json",
            "Api-Key": self.api_key
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(self.base_url, headers=headers, params=params)
                if res.status_code == 200:
                    data = res.json()
                    
                    raw_emails = data.get("emails") or []
                    emails = []
                    for e in raw_emails:
                        if isinstance(e, dict) and e.get("email"):
                            emails.append(e["email"])
                        elif isinstance(e, str) and e:
                            emails.append(e)
                    
                    raw_phones = data.get("phones") or []
                    phones = []
                    for p in raw_phones:
                        if isinstance(p, dict):
                            num = p.get("number") or p.get("e164") or p.get("phone")
                            if num:
                                phones.append(num)
                        elif isinstance(p, str) and p:
                            phones.append(p)
                    
                    job_history = []
                    for job in (data.get("job_history") or []):
                        if isinstance(job, dict):
                            loc_parts = [job.get("company_city"), job.get("company_region"), job.get("company_country_code")]
                            loc_str = ", ".join(str(p) for p in loc_parts if p)
                            job_history.append({
                                "title": job.get("title") or "N/A",
                                "company": job.get("company_name") or job.get("company") or "N/A",
                                "duration": f"{job.get('start_date', '')} - {job.get('end_date', '')}",
                                "location": loc_str or None,
                                "is_current": job.get("is_current", False)
                            })

                    education = []
                    for edu in (data.get("education") or []):
                        if isinstance(edu, dict):
                            education.append({
                                "school": edu.get("school") or "N/A",
                                "degree": edu.get("degree"),
                                "field_of_study": edu.get("major"),
                                "start_year": edu.get("start"),
                                "end_year": edu.get("end")
                            })

                    logger.info("RocketReach HTTP 200: resolved %d emails, %d phones for %s", len(emails), len(phones), formatted_url)
                    return {
                        "success": True,
                        "source": "rocketreach",
                        "full_name": data.get("name"),
                        "current_title": data.get("current_title"),
                        "current_employer": data.get("current_employer"),
                        "location": data.get("location"),
                        "emails": list(dict.fromkeys(emails)),
                        "phones": list(dict.fromkeys(phones)),
                        "raw_emails": raw_emails,
                        "raw_phones": raw_phones,
                        "job_history": job_history,
                        "education": education,
                        "linkedin_url": data.get("linkedin_url") or formatted_url
                    }
                else:
                    logger.warning("RocketReach HTTP %d: %s (url: %s)", res.status_code, res.text[:200], formatted_url)
                    error_msg = f"HTTP {res.status_code} Error"
                    try:
                        error_data = res.json()
                        if isinstance(error_data, dict):
                            error_msg = error_data.get("detail") or error_data.get("message") or error_msg
                    except Exception:
                        pass
                    return {"success": False, "error": error_msg, "emails": [], "phones": []}
        except Exception as exc:
            logger.warning("RocketReach error: %s", exc)
            return {"success": False, "error": str(exc), "emails": [], "phones": []}

        return {"success": False, "emails": [], "phones": []}
