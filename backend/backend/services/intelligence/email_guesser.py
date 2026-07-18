"""Email guesser service that uses database lookups and username variations to reconstruct email addresses."""

import re
from typing import List, Optional
from backend.services.database_lookup import DatabaseLookup


class EmailGuesser:
    """Service to reconstruct and guess potential email addresses."""

    def __init__(self) -> None:
        self.db_lookup = DatabaseLookup()

    async def guess_emails(self, username: str, full_name: Optional[str] = None) -> List[str]:
        """Guess potential emails for a username and full name, checking the database first."""
        guessed = set()
        clean_user = username.strip("@").lower()

        # 1. Search database records by username
        try:
            db_records = self.db_lookup.search_by_username(clean_user)
            for record in db_records:
                if record.get("email"):
                    guessed.add(record["email"].strip().lower())
        except Exception:
            pass

        # 2. Add common domain guesses for username
        common_domains = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com"]
        for domain in common_domains:
            guessed.add(f"{clean_user}@{domain}")

        # 3. Add guesses based on full name if present
        if full_name:
            clean_name = re.sub(r"[^a-zA-Z0-9\s]", "", full_name).lower().strip()
            parts = clean_name.split()
            if len(parts) >= 2:
                first, last = parts[0], parts[-1]
                for domain in common_domains:
                    guessed.add(f"{first}.{last}@{domain}")
                    guessed.add(f"{first}{last}@{domain}")
                    guessed.add(f"{first[0]}{last}@{domain}")

        return sorted(list(guessed))
