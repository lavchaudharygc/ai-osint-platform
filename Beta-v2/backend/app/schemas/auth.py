"""Validated API models for SOC operator authentication."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


RoleName = Literal["investigator", "breach_pii_viewer"]


class LoginRequest(BaseModel):
    """Credentials accepted by the local operator login endpoint."""

    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=64)
    password: SecretStr = Field(min_length=1, max_length=1024)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not normalized or not all(
            character.isascii() and (character.isalnum() or character in "._-")
            for character in normalized
        ):
            raise ValueError("username must use ASCII letters, numbers, dot, dash, or underscore")
        return normalized


class SessionResponse(BaseModel):
    """Public, non-secret session state returned to the browser."""

    model_config = ConfigDict(extra="forbid")

    user: str
    roles: list[RoleName]
    csrf_token: str
    expires_at: datetime


class LogoutResponse(BaseModel):
    """Logout confirmation."""

    status: Literal["logged_out"] = "logged_out"
