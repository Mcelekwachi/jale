from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException
from psycopg.errors import RaiseException
from psycopg.types.json import Jsonb

from app.config import get_settings
from app.content_filters import content_filter_sql
from app.db import get_pool

_CONTENT_STATE_COLUMNS = """
    c.id, c.source_key, language.code AS language, dialect.code AS dialect,
    category.slug AS category, c.content_type, c.difficulty_level,
    c.target_text, c.target_text_toned, c.example_sentence,
    c.example_translation, c.audio_url, c.image_url, c.image_attribution,
    c.audio_state, c.status,
    c.verified, c.verified_by, verifier.display_name AS verified_by_name,
    c.verified_at, c.contributor_id, c.flag_count, c.sort_order,
    c.created_at, c.updated_at
"""

_TRANSLATION_STATE_COLUMNS = """
    translation.content_id, meta_language.code AS meta_language,
    translation.translation, translation.literal_translation,
    translation.cultural_note, translation.verified,
    translation.verified_by, verifier.display_name AS verified_by_name,
    translation.verified_at, translation.contributor_id,
    translation.created_at, translation.updated_at
"""


async def list_flags(
    *, status: str, reason: str | None, language: str | None, limit: int, offset: int
) -> list[dict]:
    async with get_pool().connection() as conn:
        rows = await (
            await conn.execute(
                """SELECT content_id, target_text, content_type, translation,
                      flag_count, oldest_flag_at, reasons, reporter_count, flags
                 FROM admin_flag_queue
                WHERE status=%(status)s::flag_status
                  AND (%(reason)s::text IS NULL OR %(reason)s::text = ANY(reasons))
                  AND (%(language)s::text IS NULL OR language=%(language)s)
                ORDER BY flag_count DESC, oldest_flag_at, content_id
                LIMIT %(limit)s OFFSET %(offset)s""",
                {
                    "status": status,
                    "reason": reason,
                    "language": language,
                    "limit": limit,
                    "offset": offset,
                },
            )
        ).fetchall()
        return [dict(row) for row in rows]


async def resolve_flag(flag_id: int, admin_id: UUID, status: str, note: str | None) -> dict:
    async with get_pool().connection() as conn, conn.transaction():
        row = await (
            await conn.execute(
                """
            WITH updated AS (
              UPDATE content_flags
               SET status=%(status)s::flag_status, resolution_note=%(note)s,
                   resolved_by=%(admin)s, resolved_at=now()
             WHERE id=%(id)s AND status IN ('open','in_review')
         RETURNING *
            )
            SELECT updated.id, updated.content_id, updated.user_id,
                   meta_language.code AS meta_language, updated.reason,
                   updated.note, updated.status, updated.created_at,
                   updated.resolved_by, updated.resolved_at,
                   updated.resolution_note
              FROM updated
              LEFT JOIN languages meta_language
                ON meta_language.id=updated.meta_language_id
            """,
                {"id": flag_id, "status": status, "note": note, "admin": admin_id},
            )
        ).fetchone()
        if row is not None:
            return dict(row)
        exists = await (
            await conn.execute("SELECT 1 FROM content_flags WHERE id=%s", (flag_id,))
        ).fetchone()
        if exists is None:
            raise HTTPException(status_code=404, detail="flag not found")
        raise HTTPException(status_code=409, detail="flag has already been decided")


async def bulk_resolve_flags(content_id: int, admin_id: UUID, note: str | None) -> dict:
    async with get_pool().connection() as conn, conn.transaction():
        exists = await (
            await conn.execute("SELECT 1 FROM content_items WHERE id=%s FOR UPDATE", (content_id,))
        ).fetchone()
        if exists is None:
            raise HTTPException(status_code=404, detail="content not found")
        rows = await (
            await conn.execute(
                """
            UPDATE content_flags SET status='resolved', resolution_note=%(note)s,
                   resolved_by=%(admin)s, resolved_at=now()
             WHERE content_id=%(content)s AND status IN ('open','in_review')
         RETURNING id
            """,
                {"content": content_id, "admin": admin_id, "note": note},
            )
        ).fetchall()
        return {"content_id": content_id, "resolved_count": len(rows)}


async def list_content(
    *,
    content_type: str | None,
    difficulty: str | None,
    category: str | None,
    q: str | None,
    status: str | None,
    verified: bool | None,
    audio_state: str | None,
    has_flags: bool | None,
    missing_translation: str | None,
    limit: int,
    offset: int,
) -> dict:
    params = {
        "content_type": content_type,
        "difficulty": difficulty,
        "category": category,
        "q": q,
        "status": status,
        "verified": verified,
        "audio_state": audio_state,
        "has_flags": has_flags,
        "missing_translation": missing_translation,
        "limit": limit,
        "offset": offset,
        "default_meta": get_settings().default_meta_language,
    }
    where = """
      WHERE (%(status)s::content_status IS NULL OR c.status=%(status)s)
        AND (%(audio_state)s::audio_status IS NULL OR c.audio_state=%(audio_state)s)
        AND (%(has_flags)s::boolean IS NULL OR (c.flag_count > 0)=%(has_flags)s)
        AND (
              %(missing_translation)s::text IS NULL
              OR NOT EXISTS (
                   SELECT 1
                     FROM content_translations missing_translation
                     JOIN languages missing_language
                       ON missing_language.id=missing_translation.meta_language_id
                    WHERE missing_translation.content_id=c.id
                      AND missing_language.code=%(missing_translation)s
                 )
            )
        """ + content_filter_sql("ct.translation")
    joins = """
      JOIN languages l ON l.id=c.language_id
      LEFT JOIN categories cat ON cat.id=c.category_id
      LEFT JOIN languages ml ON ml.code=%(default_meta)s
      LEFT JOIN content_translations ct ON ct.content_id=c.id AND ct.meta_language_id=ml.id
    """
    async with get_pool().connection() as conn:
        if missing_translation is not None:
            language = await (
                await conn.execute(
                    "SELECT 1 FROM languages WHERE code=%s AND is_meta",
                    (missing_translation,),
                )
            ).fetchone()
            if language is None:
                raise HTTPException(status_code=422, detail="invalid meta language")
        total = await (
            await conn.execute(
                "SELECT count(*)::int AS n FROM content_items c" + joins + where, params
            )
        ).fetchone()
        rows = await (
            await conn.execute(
                """
            SELECT c.id, c.source_key, l.code AS language, c.content_type,
                   c.difficulty_level, cat.slug AS category, c.target_text,
                   c.target_text_toned, ct.translation, c.audio_url,
                   c.image_url, c.image_attribution, c.audio_state,
                   c.status, c.verified, c.flag_count, c.sort_order,
                   c.created_at, c.updated_at
              FROM content_items c
            """
                + joins
                + where
                + " ORDER BY c.sort_order, c.id LIMIT %(limit)s OFFSET %(offset)s",
                params,
            )
        ).fetchall()
        return {
            "items": [dict(row) for row in rows],
            "total": total["n"],
            "limit": limit,
            "offset": offset,
        }


async def _raw_content_state(conn, content_id: int, *, lock: bool = False) -> dict:
    suffix = " FOR UPDATE OF c" if lock else ""
    row = await (
        await conn.execute(
            f"SELECT to_jsonb(c) AS state FROM content_items c WHERE id=%s{suffix}", (content_id,)
        )
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="content not found")
    return row["state"]


async def _content_state(conn, content_id: int) -> dict:
    row = await (
        await conn.execute(
            f"""SELECT {_CONTENT_STATE_COLUMNS}
                  FROM content_items c
                  JOIN languages language ON language.id=c.language_id
                  LEFT JOIN dialects dialect ON dialect.id=c.dialect_id
                  LEFT JOIN categories category ON category.id=c.category_id
                  LEFT JOIN app_users verifier ON verifier.id=c.verified_by
                 WHERE c.id=%s""",
            (content_id,),
        )
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="content not found")
    return dict(row)


async def _translation_state(conn, content_id: int, meta_language: str) -> dict | None:
    row = await (
        await conn.execute(
            f"""SELECT {_TRANSLATION_STATE_COLUMNS}
                  FROM content_translations translation
                  JOIN languages meta_language
                    ON meta_language.id=translation.meta_language_id
                  LEFT JOIN app_users verifier ON verifier.id=translation.verified_by
                 WHERE translation.content_id=%s AND meta_language.code=%s""",
            (content_id, meta_language),
        )
    ).fetchone()
    return dict(row) if row is not None else None


async def get_content_detail(content_id: int) -> dict:
    async with get_pool().connection() as conn:
        item = await _content_state(conn, content_id)
        rows = await (
            await conn.execute(
                f"""SELECT {_TRANSLATION_STATE_COLUMNS}
                      FROM languages meta_language
                      LEFT JOIN content_translations translation
                        ON translation.meta_language_id=meta_language.id
                       AND translation.content_id=%s
                      LEFT JOIN app_users verifier ON verifier.id=translation.verified_by
                     WHERE meta_language.is_meta AND meta_language.is_active
                     ORDER BY meta_language.code""",
                (content_id,),
            )
        ).fetchall()
        translations = [
            {
                "meta_language": row["meta_language"],
                "state": dict(row) if row["content_id"] is not None else None,
            }
            for row in rows
        ]
        return {"item": item, "translations": translations}


async def _revision(
    conn, content_id: int, admin_id: UUID, note: str | None, before: dict, after: dict
) -> None:
    await conn.execute(
        "INSERT INTO content_revisions (content_id, changed_by, change_note, before_state, after_state) VALUES (%s,%s,%s,%s,%s)",
        (content_id, admin_id, note, Jsonb(before), Jsonb(after)),
    )


async def patch_content(
    content_id: int, admin_id: UUID, changes: dict[str, Any], note: str | None
) -> dict:
    allowed = {
        "target_text",
        "target_text_toned",
        "difficulty_level",
        "audio_url",
        "image_url",
        "image_attribution",
        "audio_state",
        "status",
        "sort_order",
    }
    async with get_pool().connection() as conn, conn.transaction():
        before = await _raw_content_state(conn, content_id, lock=True)
        if "category" in changes:
            slug = changes.pop("category")
            if slug is None:
                changes["category_id"] = None
            else:
                category = await (
                    await conn.execute(
                        "SELECT cat.id FROM categories cat JOIN content_items c ON c.language_id=cat.language_id WHERE c.id=%s AND cat.slug=%s",
                        (content_id, slug),
                    )
                ).fetchone()
                if category is None:
                    raise HTTPException(status_code=422, detail="invalid category slug")
                changes["category_id"] = category["id"]
        if changes:
            if not set(changes) <= allowed | {"category_id"}:
                raise HTTPException(status_code=422, detail="unsupported content field")
            assignments = ", ".join(f"{field}=%({field})s" for field in sorted(changes))
            await conn.execute(
                f"UPDATE content_items SET {assignments} WHERE id=%(content_id)s",
                {"content_id": content_id, **changes},
            )
        after = await _raw_content_state(conn, content_id)
        await _revision(conn, content_id, admin_id, note, before, after)
        return await _content_state(conn, content_id)


async def patch_translation(
    content_id: int, meta_language: str, admin_id: UUID, changes: dict[str, Any], note: str | None
) -> dict:
    async with get_pool().connection() as conn:
        try:
            async with conn.transaction():
                await _raw_content_state(conn, content_id, lock=True)
                language = await (
                    await conn.execute(
                        "SELECT id FROM languages WHERE code=%s AND is_meta", (meta_language,)
                    )
                ).fetchone()
                if language is None:
                    raise HTTPException(status_code=422, detail="invalid meta language")
                language_id = language["id"]
                row = await (
                    await conn.execute(
                        "SELECT to_jsonb(t) AS state FROM content_translations t WHERE content_id=%s AND meta_language_id=%s FOR UPDATE",
                        (content_id, language_id),
                    )
                ).fetchone()
                before = row["state"] if row else {}
                if row is None:
                    if not changes.get("translation"):
                        raise HTTPException(
                            status_code=422,
                            detail="translation is required when creating a translation",
                        )
                    await conn.execute(
                        "INSERT INTO content_translations (content_id, meta_language_id, translation, literal_translation, cultural_note) VALUES (%s,%s,%s,%s,%s)",
                        (
                            content_id,
                            language_id,
                            changes["translation"],
                            changes.get("literal_translation"),
                            changes.get("cultural_note"),
                        ),
                    )
                elif changes:
                    assignments = ", ".join(f"{field}=%({field})s" for field in sorted(changes))
                    await conn.execute(
                        f"UPDATE content_translations SET {assignments} WHERE content_id=%(content_id)s AND meta_language_id=%(language_id)s",
                        {"content_id": content_id, "language_id": language_id, **changes},
                    )
                after_row = await (
                    await conn.execute(
                        "SELECT to_jsonb(t) AS state FROM content_translations t WHERE content_id=%s AND meta_language_id=%s",
                        (content_id, language_id),
                    )
                ).fetchone()
                after = after_row["state"]
                await _revision(conn, content_id, admin_id, note, before, after)
                state = await _translation_state(conn, content_id, meta_language)
                if state is None:
                    raise HTTPException(status_code=404, detail="translation not found")
                return state
        except RaiseException as exc:
            if "cultural_note is required" in str(exc):
                raise HTTPException(
                    status_code=422, detail="cultural_note is required for proverb translations"
                ) from None
            raise


async def set_verified(
    content_id: int, meta_language: str | None, admin_id: UUID, verified: bool, note: str | None
) -> dict:
    async with get_pool().connection() as conn, conn.transaction():
        await _raw_content_state(conn, content_id, lock=True)
        if meta_language is None:
            before = await _raw_content_state(conn, content_id)
            await conn.execute(
                "UPDATE content_items SET verified=%s, verified_by=%s, verified_at=CASE WHEN %s THEN now() ELSE NULL END WHERE id=%s",
                (verified, admin_id if verified else None, verified, content_id),
            )
            after = await _raw_content_state(conn, content_id)
        else:
            language = await (
                await conn.execute(
                    "SELECT id FROM languages WHERE code=%s AND is_meta", (meta_language,)
                )
            ).fetchone()
            if language is None:
                raise HTTPException(status_code=422, detail="invalid meta language")
            key = (content_id, language["id"])
            row = await (
                await conn.execute(
                    "SELECT to_jsonb(t) AS state FROM content_translations t WHERE content_id=%s AND meta_language_id=%s FOR UPDATE",
                    key,
                )
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="translation not found")
            before = row["state"]
            await conn.execute(
                "UPDATE content_translations SET verified=%s, verified_by=%s, verified_at=CASE WHEN %s THEN now() ELSE NULL END WHERE content_id=%s AND meta_language_id=%s",
                (verified, admin_id if verified else None, verified, *key),
            )
            after = (
                await (
                    await conn.execute(
                        "SELECT to_jsonb(t) AS state FROM content_translations t WHERE content_id=%s AND meta_language_id=%s",
                        key,
                    )
                ).fetchone()
            )["state"]
        await _revision(conn, content_id, admin_id, note, before, after)
        if meta_language is None:
            return {
                "target": "content",
                "content": await _content_state(conn, content_id),
                "translation": None,
            }
        translation = await _translation_state(conn, content_id, meta_language)
        if translation is None:
            raise HTTPException(status_code=404, detail="translation not found")
        return {"target": "translation", "content": None, "translation": translation}


async def list_revisions(content_id: int) -> list[dict]:
    async with get_pool().connection() as conn:
        rows = await (
            await conn.execute(
                """SELECT r.id, r.content_id, r.changed_by, u.display_name AS changed_by_name,
                      r.change_note, r.before_state, r.after_state, r.created_at
                 FROM content_revisions r LEFT JOIN app_users u ON u.id=r.changed_by
                WHERE r.content_id=%s ORDER BY r.created_at DESC, r.id DESC""",
                (content_id,),
            )
        ).fetchall()
        return [dict(row) for row in rows]


async def list_contributors() -> list[dict]:
    async with get_pool().connection() as conn:
        rows = await (
            await conn.execute(
                """SELECT u.id, u.display_name, u.email,
                      jsonb_agg(jsonb_build_object('language', l.code, 'can_verify', p.can_verify) ORDER BY l.code) AS permissions
                 FROM contributor_permissions p JOIN app_users u ON u.id=p.user_id
                 JOIN languages l ON l.id=p.language_id GROUP BY u.id ORDER BY u.display_name, u.id"""
            )
        ).fetchall()
        return [dict(row) for row in rows]


async def grant_contributor(user_id: UUID, language: str, can_verify: bool, admin_id: UUID) -> dict:
    async with get_pool().connection() as conn, conn.transaction():
        lang = await (
            await conn.execute("SELECT id FROM languages WHERE code=%s", (language,))
        ).fetchone()
        if lang is None:
            raise HTTPException(status_code=422, detail="invalid language")
        user = await (
            await conn.execute("SELECT 1 FROM app_users WHERE id=%s", (user_id,))
        ).fetchone()
        if user is None:
            raise HTTPException(status_code=404, detail="user not found")
        row = await (
            await conn.execute(
                """INSERT INTO contributor_permissions (user_id, language_id, can_verify, granted_by, granted_at)
               VALUES (%s,%s,%s,%s,now()) ON CONFLICT (user_id,language_id) DO UPDATE
               SET can_verify=EXCLUDED.can_verify, granted_by=EXCLUDED.granted_by, granted_at=now()
               RETURNING user_id, can_verify, granted_at""",
                (user_id, lang["id"], can_verify, admin_id),
            )
        ).fetchone()
        return {**dict(row), "language": language}


async def revoke_contributor(user_id: UUID, language: str) -> None:
    async with get_pool().connection() as conn, conn.transaction():
        row = await (
            await conn.execute(
                """DELETE FROM contributor_permissions p USING languages l
                WHERE p.language_id=l.id AND p.user_id=%s AND l.code=%s RETURNING p.user_id""",
                (user_id, language),
            )
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="contributor permission not found")


async def search_users(query: str) -> list[dict]:
    async with get_pool().connection() as conn:
        rows = await (
            await conn.execute(
                """SELECT id, display_name, email, role, created_at FROM app_users
                WHERE email ILIKE '%%' || %s || '%%' OR display_name ILIKE '%%' || %s || '%%'
                ORDER BY display_name, id LIMIT 50""",
                (query, query),
            )
        ).fetchall()
        return [dict(row) for row in rows]
