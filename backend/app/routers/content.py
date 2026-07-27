from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.config import get_settings
from app.db import fetch_all, fetch_one
from app.schemas import ContentItem, ContentPage, ContentType, Difficulty

router = APIRouter(prefix="/v1/content", tags=["content"])

_SELECT = """
    SELECT c.id, c.source_key, l.code AS language, c.content_type,
           c.difficulty_level AS difficulty, cat.slug AS category,
           c.target_text, c.target_text_toned, c.english_translation,
           c.literal_translation, c.cultural_note,
           c.example_sentence, c.example_translation,
           c.audio_url, c.audio_state, c.verified, c.flag_count
      FROM content_items c
      JOIN languages l ON l.id = c.language_id
      LEFT JOIN categories cat ON cat.id = c.category_id
"""

_WHERE = """
     WHERE c.status = 'published'
       AND l.code = %(language)s
       AND (%(content_type)s::content_type IS NULL OR c.content_type = %(content_type)s)
       AND (%(difficulty)s::difficulty_level IS NULL OR c.difficulty_level = %(difficulty)s)
       AND (%(category)s::text IS NULL OR cat.slug = %(category)s)
       AND (%(verified)s::boolean IS NULL OR c.verified = %(verified)s)
       AND (
             %(q)s::text IS NULL
             OR c.target_text ILIKE '%%' || %(q)s || '%%'
             OR c.english_translation ILIKE '%%' || %(q)s || '%%'
           )
"""


@router.get("", response_model=ContentPage)
async def list_content(
    language: str = Query(default=None, description="ISO 639-3 code, e.g. ibo"),
    content_type: ContentType | None = None,
    difficulty: Difficulty | None = None,
    category: str | None = None,
    verified: bool | None = None,
    q: str | None = Query(default=None, description="substring of Igbo or English text"),
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
) -> dict:
    settings = get_settings()
    limit = min(limit, settings.max_page_size)
    params = {
        "language": language or settings.default_language,
        "content_type": content_type.value if content_type else None,
        "difficulty": difficulty.value if difficulty else None,
        "category": category,
        "verified": verified,
        "q": q,
        "limit": limit,
        "offset": offset,
    }

    total_row = await fetch_one(
        "SELECT count(*)::int AS n FROM content_items c "
        "JOIN languages l ON l.id = c.language_id "
        "LEFT JOIN categories cat ON cat.id = c.category_id" + _WHERE,
        params,
    )
    rows = await fetch_all(
        _SELECT + _WHERE + " ORDER BY c.sort_order, c.id LIMIT %(limit)s OFFSET %(offset)s",
        params,
    )
    return {
        "items": rows,
        "total": total_row["n"] if total_row else 0,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{item_id}", response_model=ContentItem)
async def get_content(item_id: int) -> dict:
    row = await fetch_one(
        _SELECT + " WHERE c.id = %(id)s AND c.status = 'published'", {"id": item_id}
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"no content item {item_id}")
    return row
