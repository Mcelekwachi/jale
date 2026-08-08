from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from app.schemas import Difficulty


class FlagDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["resolved", "rejected"]
    resolution_note: str | None = None


class BulkFlagResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resolution_note: str | None = None


class AdminContentPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_text: str | None = None
    target_text_toned: str | None = None
    category: str | None = None
    difficulty_level: Difficulty | None = None
    audio_url: str | None = None
    audio_state: Literal["missing", "placeholder", "verified"] | None = None
    status: Literal["draft", "published", "hidden"] | None = None
    sort_order: int | None = None
    change_note: str | None = None

    @model_validator(mode="after")
    def reject_null_required_columns(self):
        for field in {
            "target_text",
            "difficulty_level",
            "audio_state",
            "status",
            "sort_order",
        } & self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class AdminTranslationPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    translation: str | None = None
    literal_translation: str | None = None
    cultural_note: str | None = None
    change_note: str | None = None

    @model_validator(mode="after")
    def reject_null_translation(self):
        if "translation" in self.model_fields_set and self.translation is None:
            raise ValueError("translation cannot be null")
        return self


class VerificationChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    meta_language: str | None = None
    change_note: str | None = None


class ContributorGrant(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UUID
    language: str
    can_verify: bool = False
