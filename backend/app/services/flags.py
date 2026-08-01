from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException

from app.db import get_pool

_MAX_BIGINT = 9_223_372_036_854_775_807

_SELECT_FLAG = """
SELECT f.id, f.content_id, f.reason, f.note, ml.code AS meta_language,
       f.status, f.created_at
  FROM content_flags f
  LEFT JOIN languages ml ON ml.id = f.meta_language_id
 WHERE f.content_id = %(content_id)s
   AND f.user_id = %(user_id)s
   AND f.meta_language_id IS NOT DISTINCT FROM %(meta_language_id)s
   AND f.status IN ('open', 'in_review')
"""


def _validate_content_id(content_id: int) -> None:
    if content_id < 1 or content_id > _MAX_BIGINT:
        raise HTTPException(status_code=404, detail="content not found")


async def _lock_content(conn, content_id: int) -> None:
    content = await (
        await conn.execute("SELECT 1 FROM content_items WHERE id=%s FOR UPDATE", (content_id,))
    ).fetchone()
    if content is None:
        raise HTTPException(status_code=404, detail="content not found")


async def create_flag(
    content_id: int,
    user_id: UUID,
    reason: str,
    note: str | None,
    meta_language_id: int | None,
) -> dict:
    _validate_content_id(content_id)
    async with get_pool().connection() as conn, conn.transaction():
        await _lock_content(conn, content_id)

        await conn.execute(
            """
            INSERT INTO content_flags
                (content_id, user_id, meta_language_id, reason, note)
            VALUES
                (%(content_id)s, %(user_id)s, %(meta_language_id)s,
                 %(reason)s::flag_reason, %(note)s)
            ON CONFLICT
                (content_id, user_id, COALESCE(meta_language_id, 0))
                WHERE status IN ('open', 'in_review')
            DO NOTHING
            """,
            {
                "content_id": content_id,
                "user_id": user_id,
                "meta_language_id": meta_language_id,
                "reason": reason,
                "note": note,
            },
        )
        flag = await (
            await conn.execute(
                _SELECT_FLAG,
                {
                    "content_id": content_id,
                    "user_id": user_id,
                    "meta_language_id": meta_language_id,
                },
            )
        ).fetchone()
        if flag is None:
            raise RuntimeError("active content flag disappeared during creation")
        return flag


async def delete_flag(
    content_id: int,
    user_id: UUID,
    meta_language_id: int | None,
) -> None:
    _validate_content_id(content_id)
    async with get_pool().connection() as conn, conn.transaction():
        await _lock_content(conn, content_id)
        deleted = await (
            await conn.execute(
                """
                DELETE FROM content_flags
                 WHERE id = (
                       SELECT id
                         FROM content_flags
                        WHERE content_id = %(content_id)s
                          AND user_id = %(user_id)s
                          AND meta_language_id IS NOT DISTINCT FROM %(meta_language_id)s
                          AND status IN ('open', 'in_review')
                        ORDER BY id
                        LIMIT 1
                 )
                RETURNING id
                """,
                {
                    "content_id": content_id,
                    "user_id": user_id,
                    "meta_language_id": meta_language_id,
                },
            )
        ).fetchone()
        if deleted is None:
            raise HTTPException(status_code=404, detail="active content flag not found")
