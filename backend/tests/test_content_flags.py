from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
import pytest
from psycopg import sql

pytestmark = pytest.mark.asyncio

FLAG_FIELDS = {
    "id",
    "content_id",
    "reason",
    "note",
    "meta_language",
    "status",
    "created_at",
}


@contextmanager
def flag_users(database_url: str, *user_ids: uuid.UUID) -> Iterator[None]:
    try:
        yield
    finally:
        with psycopg.connect(database_url, autocommit=True) as conn:
            conn.execute("DELETE FROM content_flags WHERE user_id = ANY(%s)", (list(user_ids),))
            conn.execute("DELETE FROM app_users WHERE id = ANY(%s)", (list(user_ids),))


def published_content_id(database_url: str) -> int:
    with psycopg.connect(database_url) as conn:
        return conn.execute(
            "SELECT id FROM content_items WHERE status='published' ORDER BY id LIMIT 1"
        ).fetchone()[0]


def stored_flags(database_url: str, content_id: int, *user_ids: uuid.UUID) -> list[tuple]:
    with psycopg.connect(database_url) as conn:
        return conn.execute(
            """
            SELECT f.id, f.user_id, l.code, f.reason::text, f.note, f.status::text
              FROM content_flags f
              LEFT JOIN languages l ON l.id=f.meta_language_id
             WHERE f.content_id=%s AND f.user_id=ANY(%s)
             ORDER BY f.id
            """,
            (content_id, list(user_ids)),
        ).fetchall()


def flag_count(database_url: str, content_id: int) -> int:
    with psycopg.connect(database_url) as conn:
        return conn.execute(
            "SELECT flag_count FROM content_items WHERE id=%s", (content_id,)
        ).fetchone()[0]


@contextmanager
def force_flag_insert_overlap(
    database_url: str, user_id: uuid.UUID, content_id: int
) -> Iterator[None]:
    suffix = uuid.uuid4().hex
    function_name = f"test_flag_overlap_{suffix}_fn"
    trigger_name = f"test_flag_overlap_{suffix}"
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute(
            sql.SQL(
                """
                CREATE FUNCTION {}() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                  IF NEW.user_id = {}::uuid AND NEW.content_id = {}::bigint THEN
                    PERFORM pg_sleep(0.25);
                  END IF;
                  RETURN NEW;
                END
                $$
                """
            ).format(
                sql.Identifier(function_name),
                sql.Literal(str(user_id)),
                sql.Literal(content_id),
            )
        )
    try:
        with psycopg.connect(database_url, autocommit=True) as conn:
            conn.execute(
                sql.SQL(
                    "CREATE TRIGGER {} BEFORE INSERT ON content_flags "
                    "FOR EACH ROW EXECUTE FUNCTION {}()"
                ).format(sql.Identifier(trigger_name), sql.Identifier(function_name))
            )
        yield
    finally:
        with psycopg.connect(database_url, autocommit=True) as conn:
            conn.execute(
                sql.SQL("DROP TRIGGER IF EXISTS {} ON content_flags").format(
                    sql.Identifier(trigger_name)
                )
            )
            conn.execute(
                sql.SQL("DROP FUNCTION IF EXISTS {}()").format(sql.Identifier(function_name))
            )


async def test_flag_endpoints_require_authentication(client, database_url):
    content_id = published_content_id(database_url)
    assert (
        await client.post(f"/v1/content/{content_id}/flag", json={"reason": "wrong_translation"})
    ).status_code == 401
    assert (await client.delete(f"/v1/content/{content_id}/flag")).status_code == 401


@pytest.mark.parametrize(
    "reason",
    [
        "bad_audio",
        "wrong_translation",
        "cultural_inaccuracy",
        "spelling_or_tone",
        "offensive",
        "other",
    ],
)
async def test_post_flag_accepts_each_reason_and_returns_safe_shape(
    client, database_url, user_id, auth_headers, reason
):
    content_id = published_content_id(database_url)
    with flag_users(database_url, user_id):
        response = await client.post(
            f"/v1/content/{content_id}/flag",
            headers=auth_headers(subject=user_id),
            json={"reason": reason, "note": "Please review"},
        )

        assert response.status_code == 200
        body = response.json()
        assert set(body) == FLAG_FIELDS
        assert body["content_id"] == content_id
        assert body["reason"] == reason
        assert body["note"] == "Please review"
        assert body["meta_language"] is None
        assert body["status"] == "open"
        assert body["created_at"]
        assert "user_id" not in body


@pytest.mark.parametrize(
    "payload",
    [
        {"reason": "not_a_reason"},
        {"reason": "other", "unknown": True},
        {"reason": "other", "meta_language": "zzz"},
        {"reason": "other", "meta_language": "ibo"},
    ],
)
async def test_post_flag_rejects_invalid_payload_and_meta_language(
    client, database_url, user_id, auth_headers, payload
):
    content_id = published_content_id(database_url)
    with flag_users(database_url, user_id):
        response = await client.post(
            f"/v1/content/{content_id}/flag",
            headers=auth_headers(subject=user_id),
            json=payload,
        )
        assert response.status_code == 422
        assert stored_flags(database_url, content_id, user_id) == []


async def test_reposting_exact_scope_is_idempotent(client, database_url, user_id, auth_headers):
    content_id = published_content_id(database_url)
    headers = auth_headers(subject=user_id)
    payload = {"reason": "spelling_or_tone", "note": "Tone mark"}
    with flag_users(database_url, user_id):
        first = await client.post(f"/v1/content/{content_id}/flag", headers=headers, json=payload)
        second = await client.post(
            f"/v1/content/{content_id}/flag",
            headers=headers,
            json={"reason": "other", "note": "Must not replace existing"},
        )

        assert first.status_code == second.status_code == 200
        assert second.json() == first.json()
        rows = stored_flags(database_url, content_id, user_id)
        assert len(rows) == 1
        assert rows[0][3:] == ("spelling_or_tone", "Tone mark", "open")
        assert flag_count(database_url, content_id) == 1


async def test_item_and_translation_scopes_coexist_and_delete_exact_scope_only(
    client, database_url, user_id, auth_headers
):
    content_id = published_content_id(database_url)
    headers = auth_headers(subject=user_id)
    path = f"/v1/content/{content_id}/flag"
    with flag_users(database_url, user_id):
        item = await client.post(path, headers=headers, json={"reason": "bad_audio"})
        dutch = await client.post(
            path,
            headers=headers,
            json={"reason": "wrong_translation", "meta_language": "nld"},
        )
        assert item.status_code == dutch.status_code == 200
        assert item.json()["meta_language"] is None
        assert dutch.json()["meta_language"] == "nld"
        assert len(stored_flags(database_url, content_id, user_id)) == 2
        assert flag_count(database_url, content_id) == 2

        delete_item = await client.delete(path, headers=headers)
        assert delete_item.status_code == 200
        assert [row[2] for row in stored_flags(database_url, content_id, user_id)] == ["nld"]
        assert flag_count(database_url, content_id) == 1
        missing_item = await client.delete(path, headers=headers)
        assert missing_item.status_code == 404

        delete_dutch = await client.delete(path, headers=headers, params={"meta_language": "nld"})
        assert delete_dutch.status_code == 200
        assert stored_flags(database_url, content_id, user_id) == []
        assert flag_count(database_url, content_id) == 0
        missing_dutch = await client.delete(path, headers=headers, params={"meta_language": "nld"})
        assert missing_dutch.status_code == 404


@pytest.mark.parametrize("meta_language", ["zzz", "ibo"])
async def test_delete_rejects_unknown_and_non_meta_language(
    client, database_url, user_id, auth_headers, meta_language
):
    content_id = published_content_id(database_url)
    with flag_users(database_url, user_id):
        response = await client.delete(
            f"/v1/content/{content_id}/flag",
            headers=auth_headers(subject=user_id),
            params={"meta_language": meta_language},
        )
        assert response.status_code == 422


async def test_different_users_have_independent_flags_and_delete_is_owner_scoped(
    client, database_url, auth_headers
):
    first_id, second_id = uuid.uuid4(), uuid.uuid4()
    content_id = published_content_id(database_url)
    path = f"/v1/content/{content_id}/flag"
    first_headers = auth_headers(subject=first_id)
    second_headers = auth_headers(subject=second_id)
    with flag_users(database_url, first_id, second_id):
        first = await client.post(path, headers=first_headers, json={"reason": "other"})
        second = await client.post(path, headers=second_headers, json={"reason": "other"})
        assert first.status_code == second.status_code == 200
        assert first.json()["id"] != second.json()["id"]
        assert len(stored_flags(database_url, content_id, first_id, second_id)) == 2
        assert flag_count(database_url, content_id) == 2

        deleted = await client.delete(
            path,
            headers=first_headers,
            params={"user_id": str(second_id)},
        )
        assert deleted.status_code == 200
        remaining = stored_flags(database_url, content_id, first_id, second_id)
        assert [(row[1], row[0]) for row in remaining] == [(second_id, second.json()["id"])]
        assert flag_count(database_url, content_id) == 1


async def test_post_ignores_client_user_id_and_unknown_content_is_404(
    client, database_url, auth_headers
):
    owner_id, other_id = uuid.uuid4(), uuid.uuid4()
    content_id = published_content_id(database_url)
    with flag_users(database_url, owner_id, other_id):
        response = await client.post(
            f"/v1/content/{content_id}/flag",
            headers=auth_headers(subject=owner_id),
            params={"user_id": str(other_id)},
            json={"reason": "other"},
        )
        assert response.status_code == 200
        assert [row[1] for row in stored_flags(database_url, content_id, owner_id, other_id)] == [
            owner_id
        ]
        missing = await client.post(
            "/v1/content/9223372036854775000/flag",
            headers=auth_headers(subject=owner_id),
            json={"reason": "other"},
        )
        assert missing.status_code == 404


async def test_item_and_translation_scopes_can_be_created_concurrently(
    client, database_url, user_id, auth_headers
):
    content_id = published_content_id(database_url)
    headers = auth_headers(subject=user_id)
    path = f"/v1/content/{content_id}/flag"

    with flag_users(database_url, user_id):
        await client.get("/v1/me", headers=headers)
        with force_flag_insert_overlap(database_url, user_id, content_id):
            item, dutch = await asyncio.wait_for(
                asyncio.gather(
                    client.post(path, headers=headers, json={"reason": "bad_audio"}),
                    client.post(
                        path,
                        headers=headers,
                        json={"reason": "wrong_translation", "meta_language": "nld"},
                    ),
                ),
                timeout=10,
            )

            assert item.status_code == dutch.status_code == 200
            assert item.json()["id"] != dutch.json()["id"]
            rows = stored_flags(database_url, content_id, user_id)
            assert len(rows) == 2
            assert {row[2] for row in rows} == {None, "nld"}
            assert flag_count(database_url, content_id) == 2
