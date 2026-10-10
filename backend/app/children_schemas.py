from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_CHILD_AGE = 17


class ChildCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nickname: str = Field(min_length=1, max_length=30)
    birth_year: int
    consent: bool

    @field_validator("nickname")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("nickname must not be blank")
        return value

    @field_validator("birth_year")
    @classmethod
    def _plausible_year(cls, value: int) -> int:
        year = datetime.now(UTC).year
        if not year - MAX_CHILD_AGE <= value <= year:
            raise ValueError("birth_year is outside the range for a child profile")
        return value


class Child(BaseModel):
    id: UUID
    nickname: str
    birth_year: int
    created_at: datetime


class PinBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pin: str = Field(pattern=r"^\d{4,8}$")


class PinResult(BaseModel):
    valid: bool
