from __future__ import annotations

import re
import secrets
import unicodedata
import uuid
from typing import Any

from app.config import get_settings
from app.db import get_pool


def _slug_base(display_name: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", display_name or "learner")
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii").lower()
    return (re.sub(r"[^a-z0-9]+", "-", ascii_name).strip("-") or "learner")[:60]


async def provision_user(claims: dict[str, Any]) -> dict[str, Any]:
    """Create the local rows for an authenticated Supabase identity once."""
    user_id = uuid.UUID(str(claims["sub"]))
    email_claim = claims.get("email")
    email = email_claim[:320] if isinstance(email_claim, str) else None
    metadata = claims.get("user_metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    display_name = metadata.get("full_name")
    if not isinstance(display_name, str) or not display_name.strip():
        display_name = metadata.get("name")
    if not isinstance(display_name, str) or not display_name.strip():
        display_name = claims.get("name")
    if not isinstance(display_name, str) or not display_name.strip():
        display_name = None
    if not display_name and isinstance(email, str):
        display_name = email.partition("@")[0]
    display_name = (display_name or "Learner")[:100]
    avatar_url = metadata.get("avatar_url")
    if not isinstance(avatar_url, str):
        avatar_url = claims.get("avatar_url")
    if not isinstance(avatar_url, str):
        avatar_url = metadata.get("picture")
    if not isinstance(avatar_url, str):
        avatar_url = None
    elif len(avatar_url) > 2048:
        avatar_url = avatar_url[:2048]
    settings = get_settings()

    async with get_pool().connection() as conn, conn.transaction():
        language_cursor = await conn.execute(
            """
            SELECT id
              FROM languages
             WHERE code = %(code)s AND is_active AND is_learnable
            """,
            {"code": settings.default_language},
        )
        language = await language_cursor.fetchone()
        if language is None:
            raise RuntimeError("DEFAULT_LANGUAGE is not an active learnable language")

        while True:
            slug = f"{_slug_base(display_name)}-{secrets.token_hex(3)}"
            inserted_cursor = await conn.execute(
                """
                INSERT INTO app_users
                    (id, email, display_name, avatar_url, role, share_slug, last_seen_at)
                VALUES
                    (%(id)s, %(email)s, %(display_name)s, %(avatar_url)s,
                     'learner', %(slug)s, now())
                ON CONFLICT DO NOTHING
                RETURNING id
                """,
                {
                    "id": user_id,
                    "email": email,
                    "display_name": display_name,
                    "avatar_url": avatar_url,
                    "slug": slug,
                },
            )
            if await inserted_cursor.fetchone() is not None:
                break
            existing_cursor = await conn.execute(
                "SELECT id FROM app_users WHERE id = %(id)s", {"id": user_id}
            )
            if await existing_cursor.fetchone() is not None:
                break

        await conn.execute(
            "INSERT INTO user_stats (user_id) VALUES (%(id)s) ON CONFLICT DO NOTHING",
            {"id": user_id},
        )
        await conn.execute(
            """
            INSERT INTO user_preferences (user_id, active_language_id)
            VALUES (%(id)s, %(language_id)s)
            ON CONFLICT DO NOTHING
            """,
            {"id": user_id, "language_id": language["id"]},
        )
        await conn.execute(
            """
            UPDATE app_users
               SET last_seen_at = now()
             WHERE id = %(id)s
               AND (last_seen_at IS NULL OR last_seen_at < now() - interval '1 hour')
            """,
            {"id": user_id},
        )
        user_cursor = await conn.execute(
            "SELECT * FROM app_users WHERE id = %(id)s", {"id": user_id}
        )
        user = await user_cursor.fetchone()
        if user is None:
            raise RuntimeError("authenticated user provisioning failed")
        return dict(user)
