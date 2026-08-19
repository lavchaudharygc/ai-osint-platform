"""Unit tests for AIAnalyzer Indian-centric CTI filtering in Beta-v2."""

import pytest
from app.services.ai_analyzer import AIAnalyzer


@pytest.mark.anyio
async def test_filter_indian_centric_cti_heuristic():
    analyzer = AIAnalyzer()
    analyzer.api_key = None  # Force heuristic mode

    sample_cti = [
        {"title": "Russian Dump 2024", "name": "Ivan Petrov", "phone": "+79112223344"},
        {"title": "UP Police Leaks", "name": "Rohan Jha", "phone": "+919876543210"},
        {"title": "US Combolist", "name": "John Smith", "phone": "+14155552671"},
    ]

    filtered = await analyzer.filter_indian_centric_cti(sample_cti, "epimystic")

    # Should retain the Indian record matching +91 / UP Police / Rohan Jha
    assert len(filtered) >= 1
    indian_record = next((item for item in filtered if item.get("name") == "Rohan Jha"), None)
    assert indian_record is not None
    assert indian_record["indian_centric"] is True
