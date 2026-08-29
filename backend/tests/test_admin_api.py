from __future__ import annotations

import uuid

import pytest
from app.auth import current_user
from app.main import create_app
from app.schemas import FlagReason
from db_test_utils import db_connection, isolated_test_users
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

ADMIN_REQUESTS = [
    ("GET", "/v1/admin/flags", None),
    ("PATCH", "/v1/admin/flags/1", {"status": "resolved"}),
    ("POST", "/v1/admin/content/1/flags/resolve", {"resolution_note": "fixed"}),
    ("GET", "/v1/admin/content", None),
    ("GET", "/v1/admin/content/1", None),
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
        assert isinstance(matches[0]["reasons"], list)
        assert all(isinstance(reason, str) for reason in matches[0]["reasons"])
        assert all(
            reason in {member.value for member in FlagReason} for reason in matches[0]["reasons"]
        )
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
        assert "meta_language" in first.json()
        assert "meta_language_id" not in first.json()
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


async def test_flag_queue_single_reason_is_a_one_element_string_list(
    client, database_url, auth_headers
):
    admin_id = reporter_id = None
    content_id = disposable_content(database_url)
    try:
        admin_id, admin_headers = await provision_admin(client, database_url, auth_headers)
        reporter_id = uuid.uuid4()
        assert (
            await client.get("/v1/me", headers=auth_headers(subject=reporter_id))
        ).status_code == 200
        with db_connection(database_url) as conn:
            conn.execute(
                "INSERT INTO content_flags (content_id,user_id,reason) VALUES (%s,%s,'other')",
                (content_id, reporter_id),
            )

        queue = await client.get("/v1/admin/flags", headers=admin_headers)

        assert queue.status_code == 200
        match = next(row for row in queue.json() if row["content_id"] == content_id)
        assert match["reasons"] == ["other"]
        assert isinstance(match["reasons"], list)
        assert all(isinstance(reason, str) for reason in match["reasons"])
        assert all(reason in {member.value for member in FlagReason} for reason in match["reasons"])
    finally:
        with db_connection(database_url) as conn:
            conn.execute("DELETE FROM content_items WHERE id=%s", (content_id,))
        with isolated_test_users(*(value for value in (admin_id, reporter_id) if value)):
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
            assert response.json()["language"] == "ibo"
            assert (
                not {
                    "language_id",
                    "dialect_id",
                    "category_id",
                }
                & response.json().keys()
            )
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

            audio_response = await client.patch(
                f"/v1/admin/content/{content_id}",
                headers=admin_headers,
                json={
                    "audio_url": "https://example.test/verified.mp3",
                    "audio_state": "verified",
                    "change_note": "verify audio",
                },
            )
            assert audio_response.status_code == 200
            assert audio_response.json()["audio_state"] == "verified"
            subsequent_read = await client.get(
                f"/v1/admin/content/{content_id}", headers=admin_headers
            )
            assert subsequent_read.status_code == 200
            assert subsequent_read.json()["item"]["audio_state"] == "verified"

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
            assert verified.json()["target"] == "translation"
            assert verified.json()["content"] is None
            assert verified.json()["translation"]["verified_by"] == str(admin_id)
            assert verified.json()["translation"]["meta_language"] == "eng"
            item_verified = await client.post(
                f"/v1/admin/content/{content_id}/verify",
                headers=admin_headers,
                json={"meta_language": None},
            )
            assert item_verified.status_code == 200
            assert item_verified.json()["target"] == "content"
            assert item_verified.json()["translation"] is None
            assert item_verified.json()["content"]["language"] == "ibo"
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


async def test_admin_content_filters_match_public_filter_semantics(
    client, database_url, auth_headers
):
    admin_id, admin_headers = await provision_admin(client, database_url, auth_headers)
    marker = uuid.uuid4().hex
    content_ids: list[int] = []
    with isolated_test_users(admin_id):
        try:
            with db_connection(database_url) as conn:
                language_id = conn.execute("SELECT id FROM languages WHERE code='ibo'").fetchone()[
                    0
                ]
                meta_id = conn.execute("SELECT id FROM languages WHERE code='eng'").fetchone()[0]
                category_id, category_slug = conn.execute(
                    "SELECT id, slug FROM categories WHERE language_id=%s ORDER BY id LIMIT 1",
                    (language_id,),
                ).fetchone()
                proverb_id = conn.execute(
                    """INSERT INTO content_items
                           (source_key, language_id, category_id, content_type,
                            difficulty_level, target_text, verified, sort_order)
                       VALUES (%s,%s,%s,'proverb','advanced',%s,false,-1000)
                       RETURNING id""",
                    (
                        f"test:admin-filter:{marker}:proverb",
                        language_id,
                        category_id,
                        f"target-{marker}",
                    ),
                ).fetchone()[0]
                translated_id = conn.execute(
                    """INSERT INTO content_items
                           (source_key, language_id, content_type, target_text)
                       VALUES (%s,%s,'word',%s)
                       RETURNING id""",
                    (
                        f"test:admin-filter:{marker}:word",
                        language_id,
                        f"unrelated-{marker}",
                    ),
                ).fetchone()[0]
                content_ids.extend((proverb_id, translated_id))
                conn.execute(
                    """INSERT INTO content_translations
                           (content_id, meta_language_id, translation, cultural_note)
                       VALUES (%s,%s,%s,'Test note'), (%s,%s,%s,NULL)""",
                    (
                        proverb_id,
                        meta_id,
                        "Proverb translation",
                        translated_id,
                        meta_id,
                        f"translated-{marker}",
                    ),
                )
                conn.execute(
                    """INSERT INTO content_flags (content_id, user_id, reason)
                       VALUES (%s,%s,'other')""",
                    (proverb_id, admin_id),
                )

            proverb_response = await client.get(
                "/v1/admin/content?content_type=proverb", headers=admin_headers
            )
            assert proverb_response.status_code == 200
            assert proverb_id in {item["id"] for item in proverb_response.json()["items"]}
            assert all(
                item["content_type"] == "proverb" for item in proverb_response.json()["items"]
            )

            difficulty_response = await client.get(
                "/v1/admin/content?difficulty=advanced", headers=admin_headers
            )
            assert difficulty_response.status_code == 200
            assert proverb_id in {item["id"] for item in difficulty_response.json()["items"]}
            assert all(
                item["difficulty_level"] == "advanced"
                for item in difficulty_response.json()["items"]
            )

            category_response = await client.get(
                f"/v1/admin/content?category={category_slug}", headers=admin_headers
            )
            assert category_response.status_code == 200
            assert proverb_id in {item["id"] for item in category_response.json()["items"]}
            assert all(
                item["category"] == category_slug for item in category_response.json()["items"]
            )

            target_response = await client.get(
                f"/v1/admin/content?q=target-{marker}", headers=admin_headers
            )
            assert {item["id"] for item in target_response.json()["items"]} == {proverb_id}

            translation_response = await client.get(
                f"/v1/admin/content?q=translated-{marker}", headers=admin_headers
            )
            assert {item["id"] for item in translation_response.json()["items"]} == {translated_id}

            composed_response = await client.get(
                "/v1/admin/content?verified=false&content_type=proverb&has_flags=true",
                headers=admin_headers,
            )
            assert composed_response.status_code == 200
            assert proverb_id in {item["id"] for item in composed_response.json()["items"]}
            assert all(
                not item["verified"]
                and item["content_type"] == "proverb"
                and item["flag_count"] > 0
                for item in composed_response.json()["items"]
            )

            invalid = await client.get(
                "/v1/admin/content?content_type=not_real", headers=admin_headers
            )
            assert invalid.status_code == 422
        finally:
            if content_ids:
                with db_connection(database_url) as conn:
                    conn.execute("DELETE FROM content_items WHERE id=ANY(%s)", (content_ids,))


async def test_admin_content_detail_distinguishes_missing_and_empty_translations(
    client, database_url, auth_headers
):
    admin_id, admin_headers = await provision_admin(client, database_url, auth_headers)
    content_id = disposable_content(database_url)
    with isolated_test_users(admin_id):
        try:
            with db_connection(database_url) as conn:
                language_id = conn.execute("SELECT id FROM languages WHERE code='ibo'").fetchone()[
                    0
                ]
                category_id, category_slug = conn.execute(
                    "SELECT id, slug FROM categories WHERE language_id=%s ORDER BY id LIMIT 1",
                    (language_id,),
                ).fetchone()
                dialect_id, dialect_code = conn.execute(
                    "SELECT id, code FROM dialects WHERE language_id=%s ORDER BY id LIMIT 1",
                    (language_id,),
                ).fetchone()
                conn.execute(
                    "UPDATE content_items SET category_id=%s, dialect_id=%s WHERE id=%s",
                    (category_id, dialect_id, content_id),
                )
                english_id = conn.execute("SELECT id FROM languages WHERE code='eng'").fetchone()[0]
                conn.execute(
                    "INSERT INTO content_translations "
                    "(content_id, meta_language_id, translation) VALUES (%s,%s,'')",
                    (content_id, english_id),
                )

            response = await client.get(f"/v1/admin/content/{content_id}", headers=admin_headers)

            assert response.status_code == 200
            detail = response.json()
            assert detail["item"]["language"] == "ibo"
            assert detail["item"]["category"] == category_slug
            assert detail["item"]["dialect"] == dialect_code
            assert (
                not {
                    "language_id",
                    "dialect_id",
                    "category_id",
                }
                & detail["item"].keys()
            )
            translations = {slot["meta_language"]: slot["state"] for slot in detail["translations"]}
            assert translations["eng"]["translation"] == ""
            assert translations["eng"]["meta_language"] == "eng"
            assert translations["nld"] is None
        finally:
            with db_connection(database_url) as conn:
                conn.execute("DELETE FROM content_items WHERE id=%s", (content_id,))


async def test_admin_content_detail_returns_404_for_unknown_item(
    client, database_url, auth_headers
):
    admin_id, admin_headers = await provision_admin(client, database_url, auth_headers)
    with isolated_test_users(admin_id):
        response = await client.get("/v1/admin/content/2147483647", headers=admin_headers)
        assert response.status_code == 404


async def test_missing_dutch_translation_filter_can_be_scoped_to_proverbs(
    client, database_url, auth_headers
):
    admin_id, admin_headers = await provision_admin(client, database_url, auth_headers)
    with isolated_test_users(admin_id):
        response = await client.get(
            "/v1/admin/content?content_type=proverb&missing_translation=nld&limit=100",
            headers=admin_headers,
        )

        assert response.status_code == 200
        page = response.json()
        assert page["total"] == 50
        assert len(page["items"]) == 50
        assert {item["content_type"] for item in page["items"]} == {"proverb"}
