"""SQLAlchemy ORM models for the AI-OSINT data model."""

from datetime import datetime
import uuid

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import relationship

from backend.database import Base


class Investigation(Base):
    __tablename__ = "investigations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(String(50), index=True)
    investigator_id = Column(String(50))
    status = Column(String(20), default="in_progress")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    investigation_metadata = Column("metadata", JSONB)

    profiles = relationship("Profile", back_populates="investigation", cascade="all, delete-orphan")
    matches = relationship("ProfileMatch", back_populates="investigation", cascade="all, delete-orphan")
    result = relationship("InvestigationResult", back_populates="investigation", uselist=False)
    scraping_logs = relationship("ScrapingLog", back_populates="investigation")


class Profile(Base):
    __tablename__ = "profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    investigation_id = Column(UUID(as_uuid=True), ForeignKey("investigations.id"))
    platform = Column(String(30), index=True)
    username = Column(String(100), index=True)
    full_name = Column(String(200))
    bio = Column(Text)
    profile_pic_url = Column(Text)
    profile_pic_hash = Column(String(64))
    follower_count = Column(Integer)
    following_count = Column(Integer)
    post_count = Column(Integer)
    is_verified = Column(Boolean, default=False)
    account_created_date = Column(Date)
    location = Column(String(200))
    external_urls = Column(ARRAY(Text))
    raw_data = Column(JSONB)
    scraped_at = Column(DateTime, default=datetime.utcnow)

    investigation = relationship("Investigation", back_populates="profiles")


class ProfileMatch(Base):
    __tablename__ = "profile_matches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    investigation_id = Column(UUID(as_uuid=True), ForeignKey("investigations.id"))
    source_profile_id = Column(UUID(as_uuid=True), ForeignKey("profiles.id"))
    matched_profile_id = Column(UUID(as_uuid=True), ForeignKey("profiles.id"))
    confidence_score = Column(Numeric(5, 2))
    matching_factors = Column(JSONB)
    ai_analysis = Column(Text)
    human_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    investigation = relationship("Investigation", back_populates="matches")


class InvestigationResult(Base):
    __tablename__ = "investigation_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    investigation_id = Column(UUID(as_uuid=True), ForeignKey("investigations.id"), unique=True)
    platform_data = Column(JSONB)
    cross_matches = Column(JSONB)
    ai_correlation = Column(JSONB)
    risk_assessment = Column(JSONB)
    report_url = Column(Text)
    completed_at = Column(DateTime, default=datetime.utcnow)

    investigation = relationship("Investigation", back_populates="result")


class ScrapingLog(Base):
    __tablename__ = "scraping_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    investigation_id = Column(UUID(as_uuid=True), ForeignKey("investigations.id"))
    platform = Column(String(30))
    endpoint = Column(String(200))
    request_timestamp = Column(DateTime, default=datetime.utcnow)
    response_status = Column(Integer)
    response_time_ms = Column(Integer)
    error_message = Column(Text)
    ip_used = Column(String(45))

    investigation = relationship("Investigation", back_populates="scraping_logs")
