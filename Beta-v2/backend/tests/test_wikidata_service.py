"""Unit tests for WikidataService in Beta-v2."""

import pytest
import httpx
from app.services.wikidata_service import WikidataService


@pytest.mark.anyio
async def test_wikidata_search_epimystic(monkeypatch):
    class MockResponse:
        def __init__(self, url, status_code=200):
            self.url = str(url)
            self.status_code = status_code

        def json(self):
            if "api.php" in self.url:
                return {
                    "search": [
                        {
                            "id": "Q140185456",
                            "label": "Rohan Jha",
                            "description": "Indian author and civil servant",
                            "aliases": ["Epimystic"],
                        }
                    ]
                }
            return {
                "entities": {
                    "Q140185456": {
                        "labels": {"en": {"value": "Rohan Jha"}},
                        "descriptions": {"en": {"value": "Indian author and civil servant"}},
                        "aliases": {"en": [{"value": "Epimystic"}]},
                        "claims": {
                            "P2037": [{"mainsnak": {"datavalue": {"value": "epimystic"}}}],
                            "P2003": [{"mainsnak": {"datavalue": {"value": "epimystic"}}}],
                        },
                    }
                }
            }

    async def mock_get(self, url, **kwargs):
        return MockResponse(url)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    service = WikidataService()
    res = await service.search_and_get_profile("epimystic")

    assert res["success"] is True
    assert res["found"] is True
    assert res["entity_id"] == "Q140185456"
    assert res["full_name"] == "Rohan Jha"
    assert res["description"] == "Indian author and civil servant"
    assert "Epimystic" in res["aliases"]
    assert res["social_handles"].get("github_username") == "epimystic"
