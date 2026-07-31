"""API response models. These mirror the database enums exactly so a bad
value fails loudly here rather than reaching the React client."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

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
    audio_state: str
    verified: bool
    flag_count: int


class ContentPage(BaseModel):
    items: list[ContentItem]
    total: int
    limit: int
    offset: int


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
