from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.db import fetch_all, fetch_one
from app.schemas import Category, Language, LanguageCatalogue, MetaLanguageCoverage

router = APIRouter(prefix="/v1/languages", tags=["languages"])

_META_COVERAGE_LATERAL = """
         CROSS JOIN LATERAL (
               SELECT count(*) FILTER (
                          WHERE ct.content_id IS NOT NULL
                            AND NULLIF(btrim(ct.translation), '') IS NOT NULL
                      )::int
                          AS translated_count,
                      count(*)::int AS total_count
                 FROM content_items c
                 JOIN languages owner ON owner.id = c.language_id
                                     AND owner.is_learnable
                 LEFT JOIN content_translations ct
                        ON ct.content_id = c.id
                       AND ct.meta_language_id = l.id
                WHERE c.status = 'published'
         ) coverage
"""


async def _meta_language_coverage(*, include_inactive: bool) -> list[dict]:
    return await fetch_all(
        f"""
        SELECT l.code, l.name, l.endonym, l.flag_emoji, l.is_active,
               coverage.translated_count, coverage.total_count
          FROM languages l
          {_META_COVERAGE_LATERAL}
         WHERE l.is_meta AND (%(all)s OR l.is_active)
         ORDER BY l.sort_order, l.name
        """,
        {"all": include_inactive},
    )


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
    return await _meta_language_coverage(include_inactive=False)


@router.get("/catalogue", response_model=LanguageCatalogue)
async def language_catalogue() -> dict:
    learnable = await fetch_all(
        """
        SELECT l.code, l.name, l.endonym, l.flag_emoji,
               l.is_active AS available, count(c.id)::int AS content_count
          FROM languages l
          LEFT JOIN content_items c
                 ON c.language_id = l.id AND c.status = 'published'
         WHERE l.is_learnable
         GROUP BY l.id
         ORDER BY l.sort_order, l.name
        """
    )
    meta = await _meta_language_coverage(include_inactive=True)
    return {
        "learnable": learnable,
        "meta": [
            {
                "code": row["code"],
                "name": row["name"],
                "endonym": row["endonym"],
                "flag_emoji": row["flag_emoji"],
                "available": row["is_active"],
                "translated_count": row["translated_count"],
                "total_count": row["total_count"],
            }
            for row in meta
        ],
    }


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
