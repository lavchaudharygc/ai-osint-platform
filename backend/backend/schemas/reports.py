"""Pydantic models for report generation."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

ReportFormat = Literal["pdf", "html"]


class ReportGenerationResponse(BaseModel):
    investigation_id: str
    format: ReportFormat
    report_url: str
    generated_at: datetime
    status: str = "generated"
