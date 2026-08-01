from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

pytestmark = pytest.mark.asyncio


@contextmanager
def due_user(database_url: str, user_id: uuid.UUID) -> Iterator[None]:
    try:
        yield
    finally:
        with psycopg.connect(database_url, autocommit=True) as conn:
            conn.execute("DELETE FROM app_users WHERE id = %s", (user_id,))


@contextmanager
def dutch_translation(database_url: str, content_id: int, text: str) -> Iterator[None]:
    with psycopg.connect(database_url, autocommit=True) as conn:
        dutch_id = conn.execute("SELECT id FROM languages WHERE code='nld'").fetchone()[0]
        conn.execute(
            """
            INSERT INTO content_translations (content_id, meta_language_id, translation)
            VALUES (%s, %s, %s)
            ON CONFLICT (content_id, meta_language_id)
            DO UPDATE SET translation=EXCLUDED.translation
            """,
            (content_id, dutch_id, text),
        )
    try:
        yield
    finally:
        with psycopg.connect(database_url, autocommit=True) as conn:
            conn.execute(
                "DELETE FROM content_translations WHERE content_id=%s AND meta_language_id=%s",
                (content_id, dutch_id),
            )


def published_rows(database_url: str, count: int) -> list[tuple[int, str, str]]:
    with psycopg.connect(database_url) as conn:
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
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.executemany(
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
        with psycopg.connect(database_url, autocommit=True) as conn:
            conn.execute("UPDATE content_items SET status='draft' WHERE id=%s", (draft_id,))
        try:
            response = await client.get(
                "/v1/study/due",
                headers=headers,
                params={"user_id": str(other_id)},
            )
        finally:
            with psycopg.connect(database_url, autocommit=True) as conn:
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
        with psycopg.connect(database_url, autocommit=True) as conn:
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
    translated, fallback = published_rows(database_url, 2)
    headers = auth_headers(subject=user_id)
    dutch_text = f"Nederlandse vertaling {translated[0]}"
    expected_fields = {
        "id",
        "content_type",
        "prompt",
        "answer",
        "meta_language",
        "meta_language_used",
        "audio_url",
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
    with (
        due_user(database_url, user_id),
        dutch_translation(database_url, translated[0], dutch_text),
    ):
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
        assert dutch_items[translated[0]]["answer"] == dutch_text
        assert dutch_items[fallback[0]]["meta_language_used"] == "eng"
        assert dutch_items[fallback[0]]["prompt"] == fallback[1]
        assert dutch_items[fallback[0]]["answer"] == fallback[2]
        for item_id, item in dutch_items.items():
            assert reverse_items[item_id]["prompt"] == item["answer"]
            assert reverse_items[item_id]["answer"] == item["prompt"]
            assert item["options"] is None
