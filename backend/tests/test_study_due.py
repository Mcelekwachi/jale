from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from db_test_utils import db_connection, isolated_test_users

pytestmark = pytest.mark.asyncio


@contextmanager
def due_user(database_url: str, user_id: uuid.UUID) -> Iterator[None]:
    with isolated_test_users(user_id):
        yield


@contextmanager
def fixed_utc_now(client, instant: datetime) -> Iterator[None]:
    from app.services.study_progress import get_utc_now

    app = client._transport.app
    missing = object()
    previous = app.dependency_overrides.get(get_utc_now, missing)
    app.dependency_overrides[get_utc_now] = lambda: instant
    try:
        yield
    finally:
        if previous is missing:
            app.dependency_overrides.pop(get_utc_now, None)
        else:
            app.dependency_overrides[get_utc_now] = previous


def published_rows(database_url: str, count: int) -> list[tuple[int, str, str]]:
    with db_connection(database_url) as conn:
        rows = conn.execute(
            """
            SELECT c.id, c.target_text, ct.translation
              FROM content_items c
              JOIN languages target ON target.id=c.language_id AND target.code='ibo'
              JOIN languages meta ON meta.code='eng'
              JOIN content_translations ct
                ON ct.content_id=c.id AND ct.meta_language_id=meta.id
             WHERE c.status='published'
             ORDER BY c.id
             LIMIT %s
            """,
            (count,),
        ).fetchall()
    assert len(rows) == count
    return rows


async def provision(client, headers: dict[str, str]) -> None:
    assert (await client.get("/v1/me", headers=headers)).status_code == 200


def seed_progress(
    database_url: str,
    user_id: uuid.UUID,
    content_ids: list[int],
    *,
    first_due: datetime,
) -> None:
    with db_connection(database_url) as conn, conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO user_progress (user_id, content_id, times_seen, due_at)
            VALUES (%s, %s, 1, %s)
            """,
            [
                (user_id, content_id, first_due + timedelta(seconds=index))
                for index, content_id in enumerate(content_ids)
            ],
        )


async def test_due_requires_authentication(client):
    response = await client.get("/v1/study/due")
    assert response.status_code == 401


@pytest.mark.parametrize("meta_language", ["zzz", "ibo"])
async def test_due_rejects_unknown_and_non_meta_languages(
    client, database_url, user_id, auth_headers, meta_language
):
    with due_user(database_url, user_id):
        response = await client.get(
            "/v1/study/due",
            headers=auth_headers(subject=user_id),
            params={"meta_language": meta_language},
        )
        assert response.status_code == 400


async def test_due_boundary_includes_exact_now_and_excludes_one_microsecond_later(
    client, database_url, user_id, auth_headers
):
    included_id, future_id = [row[0] for row in published_rows(database_url, 2)]
    headers = auth_headers(subject=user_id)
    instant = datetime(2026, 2, 3, 4, 5, 6, 789012, tzinfo=UTC)
    with due_user(database_url, user_id):
        await provision(client, headers)
        with db_connection(database_url) as conn, conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO user_progress (user_id, content_id, times_seen, due_at)
                VALUES (%s, %s, 1, %s)
                """,
                [
                    (user_id, included_id, instant),
                    (user_id, future_id, instant + timedelta(microseconds=1)),
                ],
            )

        with fixed_utc_now(client, instant):
            response = await client.get("/v1/study/due", headers=headers)

        assert response.status_code == 200
        assert [item["id"] for item in response.json()["items"]] == [included_id]


async def test_due_limit_defaults_to_twenty_caps_at_fifty_and_validates_bounds(
    client, database_url, user_id, auth_headers
):
    rows = published_rows(database_url, 51)
    headers = auth_headers(subject=user_id)
    with due_user(database_url, user_id):
        await provision(client, headers)
        seed_progress(
            database_url,
            user_id,
            [row[0] for row in rows],
            first_due=datetime.now(UTC) - timedelta(days=1),
        )

        default = await client.get("/v1/study/due", headers=headers)
        maximum = await client.get("/v1/study/due", headers=headers, params={"limit": 50})
        zero = await client.get("/v1/study/due", headers=headers, params={"limit": 0})
        too_large = await client.get("/v1/study/due", headers=headers, params={"limit": 51})

        assert default.status_code == maximum.status_code == 200
        assert len(default.json()["items"]) == 20
        assert len(maximum.json()["items"]) == 50
        assert zero.status_code == too_large.status_code == 422


async def test_due_is_user_scoped_due_ordered_and_published_only(
    client, database_url, auth_headers
):
    owner_id, other_id = uuid.uuid4(), uuid.uuid4()
    rows = published_rows(database_url, 4)
    due_ids = [rows[1][0], rows[0][0]]
    future_id, draft_id = rows[2][0], rows[3][0]
    headers = auth_headers(subject=owner_id)
    now = datetime.now(UTC)
    with due_user(database_url, owner_id), due_user(database_url, other_id):
        await provision(client, headers)
        await provision(client, auth_headers(subject=other_id))
        seed_progress(database_url, owner_id, due_ids, first_due=now - timedelta(hours=2))
        seed_progress(database_url, owner_id, [future_id], first_due=now + timedelta(days=1))
        seed_progress(database_url, owner_id, [draft_id], first_due=now - timedelta(days=1))
        seed_progress(database_url, other_id, [future_id], first_due=now - timedelta(days=1))
        with db_connection(database_url) as conn:
            conn.execute("UPDATE content_items SET status='draft' WHERE id=%s", (draft_id,))
        try:
            response = await client.get(
                "/v1/study/due",
                headers=headers,
                params={"user_id": str(other_id)},
            )
        finally:
            with db_connection(database_url) as conn:
                conn.execute("UPDATE content_items SET status='published' WHERE id=%s", (draft_id,))

        assert response.status_code == 200
        assert [item["id"] for item in response.json()["items"]] == due_ids


async def test_due_uses_token_users_stored_active_target_language(
    client, database_url, user_id, auth_headers
):
    content_id = published_rows(database_url, 1)[0][0]
    headers = auth_headers(subject=user_id)
    with due_user(database_url, user_id):
        await provision(client, headers)
        seed_progress(
            database_url,
            user_id,
            [content_id],
            first_due=datetime.now(UTC) - timedelta(days=1),
        )
        with db_connection(database_url) as conn:
            english_id = conn.execute("SELECT id FROM languages WHERE code='eng'").fetchone()[0]
            conn.execute(
                "UPDATE user_preferences SET active_language_id=%s WHERE user_id=%s",
                (english_id, user_id),
            )

        response = await client.get(
            "/v1/study/due",
            headers=headers,
            params={"language": "ibo", "user_id": str(uuid.uuid4())},
        )
        assert response.status_code == 200
        assert response.json() == {"items": []}


async def test_due_meta_language_fallback_direction_and_exact_item_shape(
    client, database_url, user_id, auth_headers
):
    with db_connection(database_url) as conn:
        translated = conn.execute(
            """
            SELECT c.id, c.target_text, ct.translation
              FROM content_items c
              JOIN content_translations ct ON ct.content_id = c.id
              JOIN languages ml ON ml.id = ct.meta_language_id AND ml.code = 'nld'
             WHERE c.status = 'published' AND c.content_type = 'word'
             ORDER BY c.sort_order, c.id
             LIMIT 1
            """
        ).fetchone()
        fallback = conn.execute(
            """
            SELECT c.id, c.target_text, ct.translation
              FROM content_items c
             JOIN content_translations ct ON ct.content_id = c.id
             JOIN languages ml ON ml.id = ct.meta_language_id AND ml.code = 'eng'
             WHERE c.status = 'published' AND c.content_type = 'proverb'
               AND NOT EXISTS (
                   SELECT 1
                     FROM content_translations nld_ct
                     JOIN languages nld ON nld.id = nld_ct.meta_language_id
                    WHERE nld_ct.content_id = c.id AND nld.code = 'nld'
               )
             ORDER BY c.sort_order, c.id
             LIMIT 1
            """
        ).fetchone()
    assert translated and fallback
    headers = auth_headers(subject=user_id)
    expected_fields = {
        "id",
        "content_type",
        "prompt",
        "answer",
        "meta_language",
        "meta_language_used",
        "audio_url",
        "image_url",
        "image_attribution",
        "audio_state",
        "target_text_toned",
        "literal_translation",
        "cultural_note",
        "example_sentence",
        "example_translation",
        "options",
        "verified",
        "flag_count",
    }
    with due_user(database_url, user_id):
        await provision(client, headers)
        seed_progress(
            database_url,
            user_id,
            [translated[0], fallback[0]],
            first_due=datetime.now(UTC) - timedelta(days=1),
        )
        default_meta = await client.get("/v1/study/due", headers=headers)
        dutch = await client.get("/v1/study/due", headers=headers, params={"meta_language": "nld"})
        reverse = await client.get(
            "/v1/study/due",
            headers=headers,
            params={"meta_language": "nld", "direction": "meta_to_target"},
        )

        assert default_meta.status_code == dutch.status_code == reverse.status_code == 200
        assert set(default_meta.json()) == {"items"}
        assert all(item["meta_language"] == "eng" for item in default_meta.json()["items"])
        dutch_items = {item["id"]: item for item in dutch.json()["items"]}
        reverse_items = {item["id"]: item for item in reverse.json()["items"]}
        assert set(dutch_items[translated[0]]) == expected_fields
        assert dutch_items[translated[0]]["meta_language_used"] == "nld"
        assert dutch_items[translated[0]]["prompt"] == translated[1]
        assert dutch_items[translated[0]]["answer"] == translated[2]
        assert dutch_items[fallback[0]]["meta_language_used"] == "eng"
        assert dutch_items[fallback[0]]["prompt"] == fallback[1]
        assert dutch_items[fallback[0]]["answer"] == fallback[2]
        for item_id, item in dutch_items.items():
            assert reverse_items[item_id]["prompt"] == item["answer"]
            assert reverse_items[item_id]["answer"] == item["prompt"]
            assert item["options"] is None
