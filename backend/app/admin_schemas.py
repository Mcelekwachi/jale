from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from app.schemas import ContentType, Difficulty, FlagReason

FlagStatus = Literal["open", "in_review", "resolved", "rejected"]
ContentStatus = Literal["draft", "published", "hidden"]
AudioStatus = Literal["missing", "placeholder", "verified"]


class AdminFlagQueueFlag(BaseModel):
    id: int
    reason: FlagReason
    note: str | None
    reporter_id: UUID | None
    status: FlagStatus
    created_at: datetime
    meta_language: str | None


class AdminFlagQueueItem(BaseModel):
    content_id: int
    target_text: str
    content_type: ContentType
    translation: str | None
    flag_count: int
    oldest_flag_at: datetime
    reasons: list[FlagReason]
    reporter_count: int
    flags: list[AdminFlagQueueFlag]


class AdminFlagDecisionResult(BaseModel):
    id: int
    content_id: int
    user_id: UUID | None
    meta_language_id: int | None
    reason: FlagReason
    note: str | None
    status: FlagStatus
    created_at: datetime
    resolved_by: UUID | None
    resolved_at: datetime | None
    resolution_note: str | None


class BulkFlagResolutionResult(BaseModel):
    content_id: int
    resolved_count: int


class AdminContentListItem(BaseModel):
    id: int
    source_key: str
    language: str
    content_type: ContentType
    difficulty_level: Difficulty
    category: str | None
    target_text: str
    target_text_toned: str | None
    translation: str | None
    audio_url: str | None
    audio_state: AudioStatus
    status: ContentStatus
    verified: bool
    flag_count: int
    sort_order: int
    created_at: datetime
    updated_at: datetime


class AdminContentPage(BaseModel):
    items: list[AdminContentListItem]
    total: int
    limit: int
    offset: int


class AdminContentState(BaseModel):
    id: int
    source_key: str
    language_id: int
    dialect_id: int | None
    category_id: int | None
    content_type: ContentType
    difficulty_level: Difficulty
    target_text: str
    target_text_toned: str | None
    example_sentence: str | None
    example_translation: str | None
    audio_url: str | None
    audio_state: AudioStatus
    status: ContentStatus
    verified: bool
    verified_by: UUID | None
    verified_at: datetime | None
    contributor_id: UUID | None
    flag_count: int
    sort_order: int
    created_at: datetime
    updated_at: datetime


class AdminTranslationState(BaseModel):
    content_id: int
    meta_language_id: int
    translation: str
    literal_translation: str | None
    cultural_note: str | None
    verified: bool
    verified_by: UUID | None
    verified_at: datetime | None
    contributor_id: UUID | None
    created_at: datetime
    updated_at: datetime


class AdminContentRevision(BaseModel):
    id: int
    content_id: int
    changed_by: UUID | None
    changed_by_name: str | None
    change_note: str | None
    before_state: dict[str, Any]
    after_state: dict[str, Any]
    created_at: datetime


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
    audio_state: AudioStatus | None = None
    status: ContentStatus | None = None
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
