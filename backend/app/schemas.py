"""API response models. These mirror the database enums exactly so a bad
value fails loudly here rather than reaching the React client."""

from __future__ import annotations

from datetime import date, datetime, time
from enum import Enum
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# --- enums, mirroring schema.sql -------------------------------------------


class ContentType(str, Enum):
    word = "word"
    phrase = "phrase"
    proverb = "proverb"
    story = "story"


class Difficulty(str, Enum):
    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"
    native = "native"


class StudyMode(str, Enum):
    flashcard = "flashcard"
    quiz = "quiz"
    phrase_practice = "phrase_practice"
    proverbs = "proverbs"


class StudyDirection(str, Enum):
    target_to_meta = "target_to_meta"
    meta_to_target = "meta_to_target"


class FlagReason(str, Enum):
    bad_audio = "bad_audio"
    wrong_translation = "wrong_translation"
    cultural_inaccuracy = "cultural_inaccuracy"
    spelling_or_tone = "spelling_or_tone"
    offensive = "offensive"
    other = "other"


class AgeBand(str, Enum):
    child_u13 = "child_u13"
    young_adult_13_25 = "young_adult_13_25"
    adult_25_plus = "adult_25_plus"


class Connection(str, Enum):
    complete_beginner = "complete_beginner"
    language_enthusiast = "language_enthusiast"
    connected_to_igbo_family = "connected_to_igbo_family"
    igbo_heritage_speaker = "igbo_heritage_speaker"
    igbo_parent_abroad = "igbo_parent_abroad"
    mixed_parent_abroad = "mixed_parent_abroad"
    aboriginal_native = "aboriginal_native"
    other_african_heritage = "other_african_heritage"


class Goal(str, Enum):
    family_and_culture = "family_and_culture"
    teach_my_children = "teach_my_children"
    visiting_nigeria = "visiting_nigeria"
    academic_professional = "academic_professional"
    cultural_pride = "cultural_pride"
    new_language = "new_language"
    improve_proverbs_vocab = "improve_proverbs_vocab"


class Style(str, Enum):
    game_points = "game_points"
    structured_lessons = "structured_lessons"
    mixed = "mixed"


# --- resources --------------------------------------------------------------


class Language(BaseModel):
    code: str
    name: str
    endonym: str | None = None
    flag_emoji: str | None = None
    is_active: bool


class MetaLanguageCoverage(Language):
    translated_count: int
    total_count: int


class CatalogueLanguage(BaseModel):
    code: str
    name: str
    endonym: str | None = None
    flag_emoji: str | None = None
    available: bool
    content_count: int


class CatalogueMetaLanguage(BaseModel):
    code: str
    name: str
    endonym: str | None = None
    flag_emoji: str | None = None
    available: bool
    translated_count: int
    total_count: int


class LanguageCatalogue(BaseModel):
    learnable: list[CatalogueLanguage]
    meta: list[CatalogueMetaLanguage]


class Category(BaseModel):
    slug: str
    name: str
    icon: str | None = None
    item_count: int = 0


class ContentItem(BaseModel):
    id: int
    source_key: str
    language: str
    content_type: ContentType
    difficulty: Difficulty
    category: str | None = None

    target_text: str
    target_text_toned: str | None = None
    translation: str
    meta_language: str
    meta_language_used: str
    literal_translation: str | None = None
    cultural_note: str | None = None
    example_sentence: str | None = None
    example_translation: str | None = None

    audio_url: str | None = None
    image_url: str | None = None
    image_attribution: str | None = None
    audio_state: str
    verified: bool
    flag_count: int


class ContentPage(BaseModel):
    items: list[ContentItem]
    total: int
    limit: int
    offset: int


class ContentFlagCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: FlagReason
    note: str | None = None
    meta_language: str | None = None


class ContentFlag(BaseModel):
    id: int
    content_id: int
    reason: FlagReason
    note: str | None
    meta_language: str | None
    status: str
    created_at: datetime


class ContentFlagDelete(BaseModel):
    deleted: bool


class TrackUnit(BaseModel):
    position: int
    title: str
    mode: StudyMode
    category: str | None = None
    content_type: ContentType | None = None
    difficulty: Difficulty | None = None
    item_count: int
    available: int = Field(
        description="Items actually available for this unit's filters. "
        "Lower than item_count means the unit is under-served."
    )


class Track(BaseModel):
    slug: str
    name: str
    description: str | None = None
    min_difficulty: Difficulty
    max_difficulty: Difficulty
    is_default: bool
    units: list[TrackUnit] = []


class ResolvedTrack(BaseModel):
    track: Track
    matched_priority: int | None = None
    is_fallback: bool = Field(
        description="True when no persona rule matched and the default "
        "track was used — expected for a skipped onboarding."
    )


class UnitProgress(BaseModel):
    done: int
    total: int


class UserTrackUnit(TrackUnit):
    completed: bool
    progress: UnitProgress


class UserTrack(Track):
    units: list[UserTrackUnit] = []


class ResolvedUserTrack(ResolvedTrack):
    track: UserTrack


class QuizOption(BaseModel):
    text: str
    is_correct: bool


class StudyItem(BaseModel):
    """A content item shaped for the mode it will be studied in."""

    id: int
    content_type: ContentType
    prompt: str
    answer: str
    meta_language: str
    meta_language_used: str
    audio_url: str | None = None
    image_url: str | None = None
    image_attribution: str | None = None
    audio_state: str

    # phrase practice and proverbs
    target_text_toned: str | None = None
    literal_translation: str | None = None
    cultural_note: str | None = None
    example_sentence: str | None = None
    example_translation: str | None = None

    # quiz only
    options: list[QuizOption] | None = None

    verified: bool
    flag_count: int


class StudySession(BaseModel):
    track: str
    unit_position: int
    unit_title: str
    mode: StudyMode
    items: list[StudyItem]


class DueStudyItems(BaseModel):
    items: list[StudyItem]


class StudyAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_id: int
    correct: bool
    mode: StudyMode
    duration_ms: int | None = None
    client_answer_id: str | None = None


class StudyAnswersRequest(BaseModel):
    answers: list[StudyAnswer] = Field(max_length=100)


class StudyAnswerResult(BaseModel):
    content_id: int
    client_answer_id: str | None
    status: Literal["accepted", "duplicate", "unknown_content", "id_conflict"]
    leitner_box: int | None
    due_at: datetime | None
    mastered: bool


class StudyAnswersResponse(BaseModel):
    results: list[StudyAnswerResult]
    accepted_count: int
    skipped_count: int
    current_streak: int
    today_xp: int


class UserStats(BaseModel):
    current_streak: int
    longest_streak: int
    total_items_seen: int
    total_mastered: int
    total_xp: int
    today_items_reviewed: int
    today_goal_met: bool
    activity_dates: list[date]


class UserPreferences(BaseModel):
    active_language: str
    meta_language: str | None = None
    active_dialect_id: int | None = None
    age_band: AgeBand | None = None
    connection: Connection | None = None
    goal: Goal | None = None
    style: Style | None = None
    daily_minutes: int | None = None
    reminder_enabled: bool
    reminder_time: time | None = None
    timezone: str
    placement_level: Difficulty | None = None
    placement_skipped: bool
    onboarding_status: str
    onboarding_last_screen: int | None = None
    completed_at: datetime | None = None
    updated_at: datetime


class UserProfile(BaseModel):
    id: UUID
    email: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    role: str
    share_slug: str | None = None
    is_active: bool
    created_at: datetime
    last_seen_at: datetime | None = None
    preferences: UserPreferences


class PublicProfile(BaseModel):
    display_name: str | None
    current_streak: int
    longest_streak: int
    total_mastered: int
    language: str
    language_name: str
    language_endonym: str | None
    joined_month: str = Field(pattern=r"^\d{4}-\d{2}$")


class PreferencesPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active_language: str | None = None
    meta_language: str | None = None
    age_band: AgeBand | None = None
    connection: Connection | None = None
    goal: Goal | None = None
    style: Style | None = None
    daily_minutes: Literal[5, 15, 30] | None = None
    reminder_enabled: bool | None = None
    reminder_time: time | None = None
    timezone: str | None = None
    placement_level: Difficulty | None = None
    # 20 is a sanity bound against absurd input, not the number of onboarding screens.
    onboarding_last_screen: int | None = Field(default=None, ge=1, le=20)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                ZoneInfo(value)
            except (ZoneInfoNotFoundError, ValueError) as exc:
                raise ValueError("timezone must be a valid IANA timezone") from exc
        return value

    @model_validator(mode="after")
    def reject_null_required_selections(self) -> PreferencesPatch:
        cannot_clear = {
            "active_language",
            "age_band",
            "connection",
            "goal",
            "style",
            "reminder_enabled",
            "timezone",
        }
        for field in cannot_clear & self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class SkipOnboarding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # 20 is a sanity bound against absurd input, not the number of onboarding screens.
    onboarding_last_screen: int | None = Field(default=None, ge=1, le=20)


def patch_values(model: BaseModel) -> dict[str, Any]:
    """Return only explicitly supplied fields, retaining explicit nulls."""
    return {field: getattr(model, field) for field in model.model_fields_set}
