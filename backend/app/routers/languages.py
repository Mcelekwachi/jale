from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.db import fetch_all, fetch_one
from app.schemas import Category, Language, MetaLanguageCoverage

router = APIRouter(prefix="/v1/languages", tags=["languages"])


@router.get("", response_model=list[Language])
async def list_languages(include_inactive: bool = False) -> list[dict]:
    """Learnable target languages, active by default.

    Inactive targets can sit in the database before launch; meta-only
    languages are never part of the learner-facing language catalog.
    """
    return await fetch_all(
        """
        SELECT code, name, endonym, flag_emoji, is_active
          FROM languages
         WHERE is_learnable AND (%(all)s OR is_active)
         ORDER BY sort_order, name
        """,
        {"all": include_inactive},
    )


@router.get("/meta", response_model=list[MetaLanguageCoverage])
async def list_meta_languages() -> list[dict]:
    return await fetch_all(
        """
        SELECT l.code, l.name, l.endonym, l.flag_emoji, l.is_active,
               coverage.translated_count, coverage.total_count
          FROM languages l
         CROSS JOIN LATERAL (
               SELECT count(*) FILTER (WHERE ct.content_id IS NOT NULL)::int
                          AS translated_count,
                      count(*)::int AS total_count
                 FROM content_items c
                 LEFT JOIN content_translations ct
                        ON ct.content_id = c.id
                       AND ct.meta_language_id = l.id
                WHERE c.status = 'published'
         ) coverage
         WHERE l.is_meta AND l.is_active
         ORDER BY l.sort_order, l.name
        """
    )


@router.get("/{code}/categories", response_model=list[Category])
async def list_categories(code: str) -> list[dict]:
    lang = await fetch_one("SELECT id FROM languages WHERE code = %(code)s", {"code": code})
    if lang is None:
        raise HTTPException(status_code=404, detail=f"unknown language {code!r}")

    # Empty categories are excluded — a category with no content is a data
    # artefact, not something a learner should be offered.
    return await fetch_all(
        """
        SELECT cat.slug, cat.name, cat.icon, count(c.id)::int AS item_count
          FROM categories cat
          LEFT JOIN content_items c
                 ON c.category_id = cat.id AND c.status = 'published'
         WHERE cat.language_id = %(lang_id)s
         GROUP BY cat.id
        HAVING count(c.id) > 0
         ORDER BY cat.sort_order, cat.name
        """,
        {"lang_id": lang["id"]},
    )
