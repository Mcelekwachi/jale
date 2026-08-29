from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest
from db_test_utils import db_connection, isolated_test_users

pytestmark = pytest.mark.asyncio

PUBLIC_PROFILE_FIELDS = {
    "display_name",
    "current_streak",
    "longest_streak",
    "total_mastered",
    "language",
    "language_name",
    "language_endonym",
    "joined_month",
}


@contextmanager
def profile_user(database_url: str, user_id: uuid.UUID) -> Iterator[None]:
    with isolated_test_users(user_id):
        yield


async def provision(client, headers: dict[str, str]) -> dict:
    response = await client.get("/v1/me", headers=headers)
    assert response.status_code == 200
    return response.json()


async def test_public_profile_returns_only_privacy_safe_summary(
    client, database_url, user_id, auth_headers
):
    headers = auth_headers(
        subject=user_id,
        email="private@example.test",
        user_metadata={"full_name": "Public Learner"},
    )
    joined_at = datetime(2024, 3, 19, 14, 25, tzinfo=UTC)
    with profile_user(database_url, user_id):
        profile = await provision(client, headers)
        share_slug = profile["share_slug"]
        with db_connection(database_url) as conn:
            igbo_id = conn.execute("SELECT id FROM languages WHERE code='ibo'").fetchone()[0]
            conn.execute(
                """
                UPDATE app_users
                   SET display_name='Public Learner', created_at=%s
                 WHERE id=%s
                """,
                (joined_at, user_id),
            )
            conn.execute(
                "UPDATE user_preferences SET active_language_id=%s WHERE user_id=%s",
                (igbo_id, user_id),
            )
            conn.execute(
                """
                UPDATE user_stats
                   SET current_streak=7, longest_streak=19, total_mastered=42
                 WHERE user_id=%s
                """,
                (user_id,),
            )

        response = await client.get(f"/v1/profile/{share_slug}")

        assert response.status_code == 200
        assert response.json() == {
            "display_name": "Public Learner",
            "current_streak": 7,
            "longest_streak": 19,
            "total_mastered": 42,
            "language": "ibo",
            "language_name": "Igbo",
            "language_endonym": "Asụsụ Igbo",
            "joined_month": "2024-03",
        }
        assert set(response.json()) == PUBLIC_PROFILE_FIELDS
        serialized = response.text.lower()
        for private_name in (
            "email",
            "user_id",
            "preferences",
            "flags",
            "progress",
            "created_at",
            "updated_at",
            "last_seen_at",
        ):
            assert private_name not in serialized


async def test_unknown_and_inactive_profiles_are_indistinguishable(
    client, database_url, user_id, auth_headers
):
    headers = auth_headers(subject=user_id, user_metadata={"full_name": "Hidden Learner"})
    with profile_user(database_url, user_id):
        share_slug = (await provision(client, headers))["share_slug"]
        unknown = await client.get(f"/v1/profile/missing-{uuid.uuid4().hex}")
        with db_connection(database_url) as conn:
            conn.execute("UPDATE app_users SET is_active=false WHERE id=%s", (user_id,))
        inactive = await client.get(f"/v1/profile/{share_slug}")

        assert unknown.status_code == inactive.status_code == 404
        assert inactive.json() == unknown.json()


async def test_profile_slug_is_matched_as_data_not_sql(client):
    unknown = await client.get("/v1/profile/%27%20OR%201%3D1--")
    assert unknown.status_code == 404
