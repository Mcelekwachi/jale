from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import re
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.asyncio


@contextmanager
def remove_test_users(database_url: str, *user_ids: uuid.UUID) -> Iterator[None]:
    """Commit cleanup so the API pool and later tests see isolated state."""
    try:
        yield
    finally:
        with psycopg.connect(database_url, autocommit=True) as conn:
            conn.execute("DELETE FROM app_users WHERE id = ANY(%s)", (list(user_ids),))


def auth_row_counts(database_url: str, user_id: uuid.UUID) -> tuple[int, int, int]:
    with psycopg.connect(database_url) as conn:
        return conn.execute(
            """
            SELECT
                (SELECT count(*) FROM app_users WHERE id = %(user_id)s),
                (SELECT count(*) FROM user_preferences WHERE user_id = %(user_id)s),
                (SELECT count(*) FROM user_stats WHERE user_id = %(user_id)s)
            """,
            {"user_id": user_id},
        ).fetchone()


async def test_settings_allow_public_startup_without_supabase_auth_config(monkeypatch):
    from app.config import Settings

    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    monkeypatch.delenv("SUPABASE_PROJECT_URL", raising=False)

    settings = Settings()

    assert settings.supabase_jwt_secret == ""
    assert settings.supabase_project_url == ""


@pytest.mark.parametrize(
    "headers_factory",
    [
        lambda mint: {},
        lambda mint: {"Authorization": "Bearer not-a-jwt"},
        lambda mint: {
            "Authorization": f"Bearer {mint(expires_at=datetime.now(UTC) - timedelta(seconds=1))}"
        },
        lambda mint: {"Authorization": f"Bearer {mint(audience='wrong-audience')}"},
    ],
    ids=["absent", "malformed", "expired", "wrong-audience"],
)
async def test_invalid_credentials_return_the_same_generic_401(client, mint_token, headers_factory):
    response = await client.get("/v1/me", headers=headers_factory(mint_token))

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid authentication credentials"}
    assert response.headers["www-authenticate"] == "Bearer"


async def test_optional_auth_returns_none_only_when_header_is_absent(client):
    from app.auth import optional_current_user

    test_app = FastAPI()

    @test_app.get("/optional")
    async def optional(user=Depends(optional_current_user)):
        return {"user": user}

    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://optional.test"
    ) as test_client:
        absent = await test_client.get("/optional")
        invalid_responses = [
            await test_client.get("/optional", headers={"Authorization": authorization})
            for authorization in ("Bearer not-a-jwt", "Basic abc", "Bearer")
        ]

    assert absent.status_code == 200
    assert absent.json() == {"user": None}
    for invalid in invalid_responses:
        assert invalid.status_code == 401
        assert invalid.json() == {"detail": "Invalid authentication credentials"}
        assert invalid.headers["www-authenticate"] == "Bearer"


async def test_empty_configured_secret_fails_closed_with_generic_401(monkeypatch):
    from app.auth import current_user
    from app.config import get_settings

    test_app = FastAPI()

    @test_app.get("/authenticated")
    async def authenticated(user=Depends(current_user)):
        return {"id": str(user["id"])}

    claims = {
        "sub": str(uuid.uuid4()),
        "aud": "authenticated",
        "exp": int((datetime.now(UTC) + timedelta(minutes=5)).timestamp()),
        "email": "empty-secret@example.test",
    }

    def base64url_json(value: dict[str, object]) -> str:
        encoded = json.dumps(value, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(encoded).rstrip(b"=").decode()

    signing_input = ".".join(
        (base64url_json({"alg": "HS256", "typ": "JWT"}), base64url_json(claims))
    )
    signature = hmac.new(b"", signing_input.encode(), hashlib.sha256).digest()
    token = f"{signing_input}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"

    try:
        with monkeypatch.context() as auth_env:
            auth_env.setenv("SUPABASE_JWT_SECRET", "")
            get_settings.cache_clear()
            async with AsyncClient(
                transport=ASGITransport(app=test_app), base_url="http://empty-secret.test"
            ) as test_client:
                response = await test_client.get(
                    "/authenticated", headers={"Authorization": f"Bearer {token}"}
                )
    finally:
        # The context restores the deterministic test secret before this clear.
        get_settings.cache_clear()

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid authentication credentials"}
    assert response.headers["www-authenticate"] == "Bearer"


async def test_first_authenticated_request_provisions_each_user_row_once(
    client, database_url, user_id, auth_headers
):
    headers = auth_headers(
        subject=user_id,
        email="new.learner@example.test",
        user_metadata={"full_name": "New Learner", "avatar_url": "https://example.test/a.png"},
    )
    with remove_test_users(database_url, user_id):
        first = await client.get("/v1/me", headers=headers)

        assert first.status_code == 200
        assert first.json()["id"] == str(user_id)
        assert first.json()["display_name"] == "New Learner"
        assert auth_row_counts(database_url, user_id) == (1, 1, 1)

        with psycopg.connect(database_url) as conn:
            preferences = conn.execute(
                """
                SELECT l.code, p.meta_language_id
                  FROM user_preferences p
                  JOIN languages l ON l.id = p.active_language_id
                 WHERE p.user_id = %s
                """,
                (user_id,),
            ).fetchone()
        assert preferences == ("ibo", None)

        second = await client.get("/v1/me", headers=headers)

        assert second.status_code == 200
        assert second.json()["id"] == str(user_id)
        assert auth_row_counts(database_url, user_id) == (1, 1, 1)


async def test_concurrent_first_requests_converge_on_one_provisioned_user(
    client, database_url, user_id, auth_headers
):
    headers = auth_headers(subject=user_id, user_metadata={"full_name": "Concurrent Learner"})
    with remove_test_users(database_url, user_id):
        first, second = await asyncio.gather(
            client.get("/v1/me", headers=headers),
            client.get("/v1/me", headers=headers),
        )

        assert first.status_code == second.status_code == 200
        assert first.json()["id"] == second.json()["id"] == str(user_id)
        assert auth_row_counts(database_url, user_id) == (1, 1, 1)


async def test_equal_display_names_receive_distinct_url_safe_share_slugs(
    client, database_url, auth_headers
):
    first_id, second_id = uuid.uuid4(), uuid.uuid4()
    metadata = {"full_name": "Chinẹdụ Ñwá!"}
    with remove_test_users(database_url, first_id, second_id):
        first = await client.get(
            "/v1/me", headers=auth_headers(subject=first_id, user_metadata=metadata)
        )
        second = await client.get(
            "/v1/me", headers=auth_headers(subject=second_id, user_metadata=metadata)
        )

        assert first.status_code == second.status_code == 200
        slugs = {first.json()["share_slug"], second.json()["share_slug"]}
        assert len(slugs) == 2
        assert all(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug) for slug in slugs)


async def test_top_level_identity_claims_are_used_when_metadata_is_absent(
    client, database_url, user_id, auth_headers
):
    avatar_url = "https://example.test/top-level-avatar.png"
    headers = auth_headers(
        subject=user_id,
        name="Top Level Name",
        avatar_url=avatar_url,
    )
    with remove_test_users(database_url, user_id):
        response = await client.get("/v1/me", headers=headers)

        assert response.status_code == 200
        assert response.json()["display_name"] == "Top Level Name"
        assert response.json()["avatar_url"] == avatar_url
        with psycopg.connect(database_url) as conn:
            stored = conn.execute(
                "SELECT display_name, avatar_url FROM app_users WHERE id = %s", (user_id,)
            ).fetchone()
        assert stored == ("Top Level Name", avatar_url)


async def test_last_seen_advances_only_when_missing_or_older_than_one_hour(
    client, database_url, user_id, auth_headers
):
    headers = auth_headers(subject=user_id)
    old_time = datetime.now(UTC) - timedelta(hours=2)
    with remove_test_users(database_url, user_id):
        assert (await client.get("/v1/me", headers=headers)).status_code == 200
        with psycopg.connect(database_url) as conn:
            initial = conn.execute(
                "SELECT last_seen_at FROM app_users WHERE id = %s", (user_id,)
            ).fetchone()[0]
        assert initial is not None

        with psycopg.connect(database_url, autocommit=True) as conn:
            conn.execute(
                "UPDATE app_users SET last_seen_at = %s WHERE id = %s", (old_time, user_id)
            )

        assert (await client.get("/v1/me", headers=headers)).status_code == 200
        with psycopg.connect(database_url) as conn:
            advanced = conn.execute(
                "SELECT last_seen_at FROM app_users WHERE id = %s", (user_id,)
            ).fetchone()[0]
        assert advanced > old_time

        assert (await client.get("/v1/me", headers=headers)).status_code == 200
        with psycopg.connect(database_url) as conn:
            unchanged = conn.execute(
                "SELECT last_seen_at FROM app_users WHERE id = %s", (user_id,)
            ).fetchone()[0]
        assert unchanged == advanced


async def test_require_admin_rejects_learner_and_accepts_database_admin(
    client, database_url, user_id, auth_headers
):
    from app.auth import require_admin

    test_app = FastAPI()

    @test_app.get("/admin-test")
    async def admin_test(user=Depends(require_admin)):
        return {"id": str(user["id"]), "role": user["role"]}

    headers = auth_headers(subject=user_id)
    with remove_test_users(database_url, user_id):
        assert (await client.get("/v1/me", headers=headers)).status_code == 200
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://admin.test"
        ) as test_client:
            learner = await test_client.get("/admin-test", headers=headers)
            assert learner.status_code == 403

            with psycopg.connect(database_url, autocommit=True) as conn:
                conn.execute("UPDATE app_users SET role = 'admin' WHERE id = %s", (user_id,))

            admin = await test_client.get("/admin-test", headers=headers)

        assert admin.status_code == 200
        assert admin.json() == {"id": str(user_id), "role": "admin"}
