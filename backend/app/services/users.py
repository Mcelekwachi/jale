from __future__ import annotations

import re
import secrets
import unicodedata
import uuid
from typing import Any

from app.config import get_settings
from app.db import get_pool

_PREFERENCE_FIELDS = {
    "active_language_id",
    "meta_language_id",
    "age_band",
    "connection",
    "goal",
    "style",
    "daily_minutes",
    "reminder_enabled",
    "reminder_time",
    "timezone",
    "placement_level",
    "onboarding_last_screen",
}


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
    role = "admin" if settings.is_admin_email(email) else "learner"

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
                     %(role)s::user_role, %(slug)s, now())
                ON CONFLICT DO NOTHING
                RETURNING id
                """,
                {
                    "id": user_id,
                    "email": email,
                    "display_name": display_name,
                    "avatar_url": avatar_url,
                    "slug": slug,
                    "role": role,
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
            """
            UPDATE app_users
               SET role = 'admin'
             WHERE id = %(id)s
               AND %(promote)s
               AND role <> 'admin'
            """,
            {"id": user_id, "promote": role == "admin"},
        )
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


async def get_user_profile(user_id: uuid.UUID) -> dict[str, Any]:
    async with get_pool().connection() as conn:
        cursor = await conn.execute(
            """
            SELECT u.id, u.email, u.display_name, u.avatar_url, u.role,
                   u.share_slug, u.is_active, u.created_at, u.last_seen_at,
                   (to_jsonb(p) - 'active_language_id' - 'meta_language_id')
                   || jsonb_build_object(
                          'active_language', active_language.code,
                          'meta_language', meta_language.code
                      ) AS preferences
              FROM app_users u
              JOIN user_preferences p ON p.user_id = u.id
              JOIN languages active_language ON active_language.id = p.active_language_id
              LEFT JOIN languages meta_language ON meta_language.id = p.meta_language_id
             WHERE u.id = %(user_id)s
            """,
            {"user_id": user_id},
        )
        row = await cursor.fetchone()
        if row is None:
            raise RuntimeError("authenticated user profile is missing")
        return dict(row)


async def get_user_track_preferences(user_id: uuid.UUID) -> dict[str, Any]:
    async with get_pool().connection() as conn:
        cursor = await conn.execute(
            """
            SELECT l.code AS language, p.age_band AS age, p.connection,
                   p.goal, p.style
              FROM user_preferences p
              JOIN languages l ON l.id = p.active_language_id
             WHERE p.user_id = %(user_id)s
            """,
            {"user_id": user_id},
        )
        row = await cursor.fetchone()
        if row is None:
            raise RuntimeError("authenticated user preferences are missing")
        return dict(row)


async def update_preferences(user_id: uuid.UUID, changes: dict[str, Any]) -> dict[str, Any]:
    invalid = changes.keys() - _PREFERENCE_FIELDS
    if invalid:
        raise ValueError(f"unsupported preference fields: {sorted(invalid)!r}")
    if changes:
        assignments = ", ".join(f"{field} = %({field})s" for field in sorted(changes))
        async with get_pool().connection() as conn:
            await conn.execute(
                f"UPDATE user_preferences SET {assignments} WHERE user_id = %(user_id)s",  # noqa: S608
                {"user_id": user_id, **changes},
            )
    return await get_user_profile(user_id)


async def complete_onboarding(user_id: uuid.UUID) -> dict[str, Any]:
    async with get_pool().connection() as conn:
        await conn.execute(
            """
            UPDATE user_preferences
               SET onboarding_status = 'completed', completed_at = now()
             WHERE user_id = %(user_id)s
               AND onboarding_status = 'not_started'
            """,
            {"user_id": user_id},
        )
    return await get_user_profile(user_id)


async def skip_onboarding(
    user_id: uuid.UUID, *, screen_supplied: bool, screen: int | None
) -> dict[str, Any]:
    async with get_pool().connection() as conn:
        if screen_supplied:
            await conn.execute(
                """
                UPDATE user_preferences
                   SET onboarding_status = 'skipped', onboarding_last_screen = %(screen)s
                 WHERE user_id = %(user_id)s
                   AND onboarding_status = 'not_started'
                """,
                {"user_id": user_id, "screen": screen},
            )
        else:
            await conn.execute(
                """
                UPDATE user_preferences
                   SET onboarding_status = 'skipped'
                 WHERE user_id = %(user_id)s
                   AND onboarding_status = 'not_started'
                """,
                {"user_id": user_id},
            )
    return await get_user_profile(user_id)
