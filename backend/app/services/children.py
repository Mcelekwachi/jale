"""Child profiles, the age gate, account export and account deletion.

A child profile is an app_users row owned by a parent (parent_user_id). Because
every progress table is keyed by app_users.id, a child needs no special-casing
anywhere else: selecting the profile just swaps which user id a request is for.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import secrets
import urllib.error
import urllib.request
import uuid
from typing import Any

import psycopg.errors

from app.config import get_settings
from app.db import get_pool

logger = logging.getLogger(__name__)

CONSENT_POLICY_VERSION = "2026-10-v1"
MAX_CHILDREN = 10

# Tables whose rows belong to one user and are keyed by a user_id column.
_EXPORT_TABLES = (
    "user_preferences",
    "user_stats",
    "user_progress",
    "user_daily_activity",
    "study_answer_receipts",
    "content_flags",
    "contributors",
    "contributor_permissions",
)


async def get_child_for_parent(parent_id: Any, child_id: uuid.UUID) -> dict[str, Any] | None:
    async with get_pool().connection() as conn:
        cursor = await conn.execute(
            """
            SELECT child.*
              FROM app_users child
              JOIN parental_consents consent ON consent.child_user_id = child.id
             WHERE child.id = %(child_id)s
               AND child.parent_user_id = %(parent_id)s
               AND child.is_active
            """,
            {"child_id": child_id, "parent_id": parent_id},
        )
        row = await cursor.fetchone()
    return dict(row) if row else None


async def confirm_age(user_id: Any) -> None:
    async with get_pool().connection() as conn:
        await conn.execute(
            "UPDATE app_users SET age_confirmed_at = COALESCE(age_confirmed_at, now())"
            " WHERE id = %(id)s AND parent_user_id IS NULL",
            {"id": user_id},
        )


async def list_children(parent_id: Any) -> list[dict[str, Any]]:
    async with get_pool().connection() as conn:
        cursor = await conn.execute(
            """
            SELECT id, display_name AS nickname, birth_year, created_at
              FROM app_users
             WHERE parent_user_id = %(parent_id)s
             ORDER BY created_at, id
            """,
            {"parent_id": parent_id},
        )
        return [dict(row) for row in await cursor.fetchall()]


async def create_child(parent_id: Any, nickname: str, birth_year: int) -> dict[str, Any] | None:
    """Create a child profile. Returns None when the parent is at the limit."""
    child_id = uuid.uuid4()
    settings = get_settings()
    async with get_pool().connection() as conn, conn.transaction():
        # Serialise per parent so two requests cannot both slip under the limit.
        await conn.execute(
            "SELECT pg_advisory_xact_lock(hashtext(%(key)s))", {"key": str(parent_id)}
        )
        count_cursor = await conn.execute(
            "SELECT count(*) AS n FROM app_users WHERE parent_user_id = %(id)s", {"id": parent_id}
        )
        if (await count_cursor.fetchone())["n"] >= MAX_CHILDREN:
            return None
        language_cursor = await conn.execute(
            "SELECT id FROM languages WHERE code = %(code)s AND is_active AND is_learnable",
            {"code": settings.default_language},
        )
        language = await language_cursor.fetchone()
        if language is None:
            raise RuntimeError("DEFAULT_LANGUAGE is not an active learnable language")
        inserted = await conn.execute(
            """
            INSERT INTO app_users (id, display_name, parent_user_id, birth_year, age_confirmed_at)
            VALUES (%(id)s, %(nickname)s, %(parent_id)s, %(birth_year)s, now())
            RETURNING created_at
            """,
            {
                "id": child_id,
                "nickname": nickname,
                "parent_id": parent_id,
                "birth_year": birth_year,
            },
        )
        created_at = (await inserted.fetchone())["created_at"]
        await conn.execute("INSERT INTO user_stats (user_id) VALUES (%(id)s)", {"id": child_id})
        await conn.execute(
            "INSERT INTO user_preferences (user_id, active_language_id, age_band)"
            " VALUES (%(id)s, %(language_id)s, 'child_u13')",
            {"id": child_id, "language_id": language["id"]},
        )
        await conn.execute(
            "INSERT INTO parental_consents (parent_user_id, child_user_id, policy_version)"
            " VALUES (%(parent_id)s, %(child_id)s, %(version)s)",
            {"parent_id": parent_id, "child_id": child_id, "version": CONSENT_POLICY_VERSION},
        )
    return {
        "id": child_id,
        "nickname": nickname,
        "birth_year": birth_year,
        "created_at": created_at,
    }


async def delete_child(parent_id: Any, child_id: uuid.UUID) -> bool:
    """Withdraw consent: erase the child profile and everything keyed to it."""
    async with get_pool().connection() as conn:
        cursor = await conn.execute(
            "DELETE FROM app_users WHERE id = %(child_id)s AND parent_user_id = %(parent_id)s"
            " RETURNING id",
            {"child_id": child_id, "parent_id": parent_id},
        )
        return await cursor.fetchone() is not None


async def _export_user(conn, user_id: Any) -> dict[str, Any]:
    cursor = await conn.execute(
        """
        SELECT to_jsonb(u) - 'parent_pin_hash' AS data
          FROM app_users u WHERE u.id = %(id)s
        """,
        {"id": user_id},
    )
    row = await cursor.fetchone()
    data: dict[str, Any] = {"account": row["data"] if row else None}
    for table in _EXPORT_TABLES:
        cursor = await conn.execute(
            f"SELECT to_jsonb(t) AS data FROM {table} t WHERE t.user_id = %(id)s",  # noqa: S608
            {"id": user_id},
        )
        data[table] = [r["data"] for r in await cursor.fetchall()]
    return data


async def export_user(user_id: Any, *, include_children: bool) -> dict[str, Any]:
    async with get_pool().connection() as conn:
        data = await _export_user(conn, user_id)
        if include_children:
            cursor = await conn.execute(
                "SELECT id FROM app_users WHERE parent_user_id = %(id)s ORDER BY created_at, id",
                {"id": user_id},
            )
            data["children"] = [await _export_user(conn, r["id"]) for r in await cursor.fetchall()]
            cursor = await conn.execute(
                "SELECT to_jsonb(c) AS data FROM parental_consents c WHERE c.parent_user_id = %(id)s",
                {"id": user_id},
            )
            data["parental_consents"] = [r["data"] for r in await cursor.fetchall()]
        return data


async def export_child(parent_id: Any, child_id: uuid.UUID) -> dict[str, Any] | None:
    if await get_child_for_parent(parent_id, child_id) is None:
        return None
    return await export_user(child_id, include_children=False)


def _delete_login(user_id: Any) -> None:
    settings = get_settings()
    key = settings.supabase_service_role_key
    if not key:
        return
    request = urllib.request.Request(  # noqa: S310 — https project URL validated in config
        f"{settings.supabase_project_url}/auth/v1/admin/users/{user_id}",
        method="DELETE",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10):  # noqa: S310
            pass
    except (urllib.error.URLError, TimeoutError):
        # The data is already gone; a surviving login just re-registers empty.
        logger.warning("could not delete the auth login for a deleted account")


async def delete_account(user_id: Any) -> bool:
    """Erase the account, its children and all their data.

    Returns False when payment records still reference the person: those must be
    kept, so deletion is refused rather than silently orphaning them.
    """
    try:
        async with get_pool().connection() as conn:
            await conn.execute("DELETE FROM app_users WHERE id = %(id)s", {"id": user_id})
    except psycopg.errors.ForeignKeyViolation:
        return False
    await asyncio.to_thread(_delete_login, user_id)
    return True


def _hash_pin(pin: str, salt: bytes) -> str:
    digest = hashlib.scrypt(pin.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"{salt.hex()}:{digest.hex()}"


async def set_pin(user_id: Any, pin: str) -> None:
    stored = _hash_pin(pin, secrets.token_bytes(16))
    async with get_pool().connection() as conn:
        await conn.execute(
            "UPDATE app_users SET parent_pin_hash = %(hash)s WHERE id = %(id)s AND parent_user_id IS NULL",
            {"hash": stored, "id": user_id},
        )


async def has_pin(user_id: Any) -> bool:
    async with get_pool().connection() as conn:
        cursor = await conn.execute(
            "SELECT parent_pin_hash IS NOT NULL AS has_pin FROM app_users WHERE id = %(id)s",
            {"id": user_id},
        )
        row = await cursor.fetchone()
    return bool(row and row["has_pin"])


async def verify_pin(user_id: Any, pin: str) -> bool:
    async with get_pool().connection() as conn:
        cursor = await conn.execute(
            "SELECT parent_pin_hash FROM app_users WHERE id = %(id)s", {"id": user_id}
        )
        row = await cursor.fetchone()
    if not row or not row["parent_pin_hash"]:
        return False
    salt_hex, _, digest_hex = row["parent_pin_hash"].partition(":")
    candidate = hashlib.scrypt(pin.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1)
    return hmac.compare_digest(candidate.hex(), digest_hex)
