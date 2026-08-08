from __future__ import annotations

import uuid

import pytest
from app.auth import current_user
from app.main import create_app
from db_test_utils import db_connection, isolated_test_users
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

ADMIN_REQUESTS = [
    ("GET", "/v1/admin/flags", None),
    ("PATCH", "/v1/admin/flags/1", {"status": "resolved"}),
    ("POST", "/v1/admin/content/1/flags/resolve", {"resolution_note": "fixed"}),
    ("GET", "/v1/admin/content", None),
    ("PATCH", "/v1/admin/content/1", {"target_text": "Ndewo"}),
    ("PATCH", "/v1/admin/content/1/translations/eng", {"translation": "Hello"}),
    ("POST", "/v1/admin/content/1/verify", {"meta_language": None}),
    ("POST", "/v1/admin/content/1/unverify", {"meta_language": None}),
    ("GET", "/v1/admin/content/1/revisions", None),
    ("GET", "/v1/admin/contributors", None),
    (
        "POST",
        "/v1/admin/contributors",
        {"user_id": str(uuid.uuid4()), "language": "ibo", "can_verify": True},
    ),
    ("DELETE", f"/v1/admin/contributors/{uuid.uuid4()}/ibo", None),
    ("GET", "/v1/admin/users?q=ada", None),
]


async def request(client: AsyncClient, method: str, path: str, body: dict | None):
    return await client.request(method, path, json=body)


@pytest.mark.asyncio
async def test_every_admin_endpoint_rejects_learners_with_403():
    app: FastAPI = create_app()
    app.dependency_overrides[current_user] = lambda: {"id": uuid.uuid4(), "role": "learner"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for method, path, body in ADMIN_REQUESTS:
            response = await request(client, method, path, body)
            assert response.status_code == 403, (method, path, response.text)


@pytest.mark.asyncio
async def test_every_admin_endpoint_rejects_unauthenticated_requests_with_401():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for method, path, body in ADMIN_REQUESTS:
            response = await request(client, method, path, body)
            assert response.status_code == 401, (method, path, response.text)


def test_admin_emails_are_trimmed_and_case_insensitive(monkeypatch):
    from app.config import Settings

    monkeypatch.setenv("ADMIN_EMAILS", " Founder@Example.com, admin@example.com ,, ")
    settings = Settings()
    assert settings.is_admin_email("founder@example.com")
    assert settings.is_admin_email(" ADMIN@example.COM ")
    assert not settings.is_admin_email("learner@example.com")


async def provision_admin(client, database_url, auth_headers):
    admin_id = uuid.uuid4()
    headers = auth_headers(subject=admin_id, email="admin-api@example.test")
    assert (await client.get("/v1/me", headers=headers)).status_code == 200
    with db_connection(database_url) as conn:
        conn.execute("UPDATE app_users SET role='admin' WHERE id=%s", (admin_id,))
    return admin_id, headers


def disposable_content(database_url: str, *, with_translation: bool = False) -> int:
    marker = uuid.uuid4().hex
    with db_connection(database_url) as conn:
        language_id = conn.execute("SELECT id FROM languages WHERE code='ibo'").fetchone()[0]
        content_id = conn.execute(
            """INSERT INTO content_items
                   (source_key, language_id, content_type, target_text)
               VALUES (%s,%s,'word',%s) RETURNING id""",
            (f"test:admin:{marker}", language_id, f"test-{marker}"),
        ).fetchone()[0]
        if with_translation:
            meta_id = conn.execute("SELECT id FROM languages WHERE code='eng'").fetchone()[0]
            conn.execute(
                "INSERT INTO content_translations (content_id,meta_language_id,translation) VALUES (%s,%s,'Test')",
                (content_id, meta_id),
            )
    return content_id


async def test_admin_email_provisions_promotes_and_never_demotes(
    client, database_url, auth_headers, monkeypatch
):
    from app.config import get_settings

    configured_id, existing_id, ordinary_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    configured = auth_headers(subject=configured_id, email=" Founder@Example.test ")
    existing = auth_headers(subject=existing_id, email="existing@example.test")
    ordinary = auth_headers(subject=ordinary_id, email="ordinary@example.test")
    with isolated_test_users(configured_id, existing_id, ordinary_id):
        monkeypatch.setenv("ADMIN_EMAILS", "founder@example.test")
        get_settings.cache_clear()
        assert (await client.get("/v1/me", headers=configured)).json()["role"] == "admin"
        assert (await client.get("/v1/me", headers=ordinary)).json()["role"] == "learner"
        assert (await client.get("/v1/me", headers=existing)).json()["role"] == "learner"

        monkeypatch.setenv("ADMIN_EMAILS", "existing@example.test")
        get_settings.cache_clear()
        assert (await client.get("/v1/me", headers=existing)).json()["role"] == "admin"
        assert (await client.get("/v1/me", headers=configured)).json()["role"] == "admin"
    get_settings.cache_clear()


async def test_flag_queue_resolution_and_bulk_resolution(client, database_url, auth_headers):
    admin_id = reporter_one = reporter_two = None
    flag_ids: list[int] = []
    try:
        admin_id, admin_headers = await provision_admin(client, database_url, auth_headers)
        reporter_one, reporter_two = uuid.uuid4(), uuid.uuid4()
        for reporter in (reporter_one, reporter_two):
            assert (
                await client.get("/v1/me", headers=auth_headers(subject=reporter))
            ).status_code == 200
        with db_connection(database_url) as conn:
            content_id = conn.execute(
                "SELECT id FROM content_items ORDER BY id LIMIT 1"
            ).fetchone()[0]
            rows = conn.execute(
                """INSERT INTO content_flags (content_id,user_id,reason,note)
                   VALUES (%s,%s,'bad_audio','one'),(%s,%s,'wrong_translation','two')
                   RETURNING id""",
                (content_id, reporter_one, content_id, reporter_two),
            ).fetchall()
            flag_ids = [row[0] for row in rows]
        queue = await client.get("/v1/admin/flags", headers=admin_headers)
        assert queue.status_code == 200
        matches = [row for row in queue.json() if row["content_id"] == content_id]
        assert len(matches) == 1
        assert matches[0]["flag_count"] == 2
        assert set(matches[0]["reasons"]) == {"bad_audio", "wrong_translation"}
        assert matches[0]["reporter_count"] == 2
        assert {flag["note"] for flag in matches[0]["flags"]} == {"one", "two"}
        assert all("meta_language" in flag for flag in matches[0]["flags"])
        assert matches[0]["translation"]

        first = await client.patch(
            f"/v1/admin/flags/{rows[0][0]}",
            headers=admin_headers,
            json={"status": "resolved", "resolution_note": "checked"},
        )
        assert first.status_code == 200
        assert (
            await client.patch(
                f"/v1/admin/flags/{rows[0][0]}",
                headers=admin_headers,
                json={"status": "rejected"},
            )
        ).status_code == 409
        bulk = await client.post(
            f"/v1/admin/content/{content_id}/flags/resolve",
            headers=admin_headers,
            json={"resolution_note": "content fixed"},
        )
        assert bulk.json()["resolved_count"] == 1
        with db_connection(database_url) as conn:
            assert (
                conn.execute(
                    "SELECT flag_count FROM content_items WHERE id=%s", (content_id,)
                ).fetchone()[0]
                == 0
            )
    finally:
        if flag_ids:
            with db_connection(database_url) as conn:
                conn.execute("DELETE FROM content_flags WHERE id=ANY(%s)", (flag_ids,))
        with isolated_test_users(
            *(value for value in (admin_id, reporter_one, reporter_two) if value)
        ):
            pass


async def test_content_edits_are_audited_and_proverb_validation_is_readable(
    client, database_url, auth_headers
):
    admin_id, admin_headers = await provision_admin(client, database_url, auth_headers)
    with isolated_test_users(admin_id):
        content_id = disposable_content(database_url)
        with db_connection(database_url) as conn:
            proverb_id = conn.execute(
                "SELECT id FROM content_items WHERE content_type='proverb' ORDER BY id LIMIT 1"
            ).fetchone()[0]
            before_text = conn.execute(
                "SELECT target_text FROM content_items WHERE id=%s", (content_id,)
            ).fetchone()[0]
        try:
            changed = before_text + " test"
            response = await client.patch(
                f"/v1/admin/content/{content_id}",
                headers=admin_headers,
                json={"target_text": changed, "change_note": "test edit"},
            )
            assert response.status_code == 200
            assert (
                await client.patch(
                    f"/v1/admin/content/{content_id}",
                    headers=admin_headers,
                    json={"source_key": "forbidden"},
                )
            ).status_code == 422
            revisions = (
                await client.get(f"/v1/admin/content/{content_id}/revisions", headers=admin_headers)
            ).json()
            assert revisions[0]["before_state"]["target_text"] == before_text
            assert revisions[0]["after_state"]["target_text"] == changed
            invalid = await client.patch(
                f"/v1/admin/content/{proverb_id}/translations/eng",
                headers=admin_headers,
                json={"cultural_note": None},
            )
            assert invalid.status_code == 422
            assert "cultural_note is required" in invalid.json()["detail"]
        finally:
            with db_connection(database_url) as conn:
                conn.execute("DELETE FROM content_items WHERE id=%s", (content_id,))


async def test_translation_verification_contributors_and_user_search(
    client, database_url, auth_headers
):
    admin_id, admin_headers = await provision_admin(client, database_url, auth_headers)
    contributor_id = uuid.uuid4()
    with isolated_test_users(admin_id, contributor_id):
        assert (
            await client.get(
                "/v1/me",
                headers=auth_headers(
                    subject=contributor_id,
                    email="contributor@example.test",
                    user_metadata={"full_name": "Ada Contributor"},
                ),
            )
        ).status_code == 200
        content_id = disposable_content(database_url, with_translation=True)
        try:
            verified = await client.post(
                f"/v1/admin/content/{content_id}/verify",
                headers=admin_headers,
                json={"meta_language": "eng"},
            )
            assert verified.status_code == 200
            assert verified.json()["verified_by"] == str(admin_id)
            granted = await client.post(
                "/v1/admin/contributors",
                headers=admin_headers,
                json={"user_id": str(contributor_id), "language": "ibo", "can_verify": True},
            )
            assert granted.status_code == 201
            assert (
                await client.delete(
                    f"/v1/admin/contributors/{contributor_id}/ibo", headers=admin_headers
                )
            ).status_code == 204
            users = await client.get("/v1/admin/users?q=Ada", headers=admin_headers)
            assert users.status_code == 200
            found = next(row for row in users.json() if row["id"] == str(contributor_id))
            assert set(found) == {"id", "display_name", "email", "role", "created_at"}
        finally:
            with db_connection(database_url) as conn:
                conn.execute("DELETE FROM content_items WHERE id=%s", (content_id,))
