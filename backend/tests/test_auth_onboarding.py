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

import pytest
from db_test_utils import db_connection, isolated_test_users
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.asyncio


@contextmanager
def remove_test_users(database_url: str, *user_ids: uuid.UUID) -> Iterator[None]:
    """Commit cleanup so the API pool and later tests see isolated state."""
    with isolated_test_users(*user_ids):
        yield


def auth_row_counts(database_url: str, user_id: uuid.UUID) -> tuple[int, int, int]:
    with db_connection(database_url) as conn:
        return conn.execute(
            """
            SELECT
                (SELECT count(*) FROM app_users WHERE id = %(user_id)s),
                (SELECT count(*) FROM user_preferences WHERE user_id = %(user_id)s),
                (SELECT count(*) FROM user_stats WHERE user_id = %(user_id)s)
            """,
            {"user_id": user_id},
        ).fetchone()


def unit_content_ids(database_url: str, track_slug: str, position: int) -> list[int]:
    with db_connection(database_url) as conn:
        rows = conn.execute(
            """
            SELECT item.id
              FROM track_units unit
              JOIN tracks track ON track.id = unit.track_id
              JOIN LATERAL (
                  SELECT content.id
                    FROM content_items content
                   WHERE content.language_id = track.language_id
                     AND content.status = 'published'
                     AND (unit.filter_category_id IS NULL
                          OR content.category_id = unit.filter_category_id)
                     AND (unit.filter_content_type IS NULL
                          OR content.content_type = unit.filter_content_type)
                     AND (unit.filter_difficulty IS NULL
                          OR content.difficulty_level = unit.filter_difficulty)
                   ORDER BY content.sort_order, content.id
                   LIMIT unit.item_count
              ) item ON true
             WHERE track.slug = %s AND unit.position = %s
             ORDER BY item.id
            """,
            (track_slug, position),
        ).fetchall()
    return [row[0] for row in rows]


async def test_settings_require_supabase_project_url(monkeypatch):
    from app.config import Settings

    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    monkeypatch.delenv("SUPABASE_PROJECT_URL", raising=False)

    with pytest.raises(ValueError, match="SUPABASE_PROJECT_URL"):
        Settings()


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

        with db_connection(database_url) as conn:
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
        with db_connection(database_url) as conn:
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
        with db_connection(database_url) as conn:
            initial = conn.execute(
                "SELECT last_seen_at FROM app_users WHERE id = %s", (user_id,)
            ).fetchone()[0]
        assert initial is not None

        with db_connection(database_url) as conn:
            conn.execute(
                "UPDATE app_users SET last_seen_at = %s WHERE id = %s", (old_time, user_id)
            )

        assert (await client.get("/v1/me", headers=headers)).status_code == 200
        with db_connection(database_url) as conn:
            advanced = conn.execute(
                "SELECT last_seen_at FROM app_users WHERE id = %s", (user_id,)
            ).fetchone()[0]
        assert advanced > old_time

        assert (await client.get("/v1/me", headers=headers)).status_code == 200
        with db_connection(database_url) as conn:
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

            with db_connection(database_url) as conn:
                conn.execute("UPDATE app_users SET role = 'admin' WHERE id = %s", (user_id,))

            admin = await test_client.get("/admin-test", headers=headers)

        assert admin.status_code == 200
        assert admin.json() == {"id": str(user_id), "role": "admin"}


async def test_get_me_returns_profile_with_nested_preferences(
    client, database_url, user_id, auth_headers
):
    headers = auth_headers(
        subject=user_id,
        email="profile@example.test",
        user_metadata={"full_name": "Profile Learner"},
    )
    with remove_test_users(database_url, user_id):
        response = await client.get("/v1/me", headers=headers)

        assert response.status_code == 200
        profile = response.json()
        assert {
            "id": profile["id"],
            "email": profile["email"],
            "display_name": profile["display_name"],
            "role": profile["role"],
        } == {
            "id": str(user_id),
            "email": "profile@example.test",
            "display_name": "Profile Learner",
            "role": "learner",
        }
        assert profile["share_slug"]
        assert "avatar_url" in profile
        assert set(profile["preferences"]) >= {
            "active_language",
            "meta_language",
            "age_band",
            "connection",
            "goal",
            "style",
            "daily_minutes",
            "reminder_enabled",
            "reminder_time",
            "timezone",
            "placement_level",
            "placement_skipped",
            "onboarding_status",
            "onboarding_last_screen",
            "completed_at",
        }
        assert profile["preferences"]["active_language"] == "ibo"
        assert profile["preferences"]["meta_language"] is None
        assert not any(key.endswith("_language_id") for key in profile["preferences"])
        assert profile["preferences"]["onboarding_status"] == "not_started"


async def test_patch_preferences_is_partial_and_does_not_change_onboarding_status(
    client, database_url, user_id, auth_headers
):
    headers = auth_headers(subject=user_id)
    with remove_test_users(database_url, user_id):
        before = (await client.get("/v1/me", headers=headers)).json()["preferences"]

        response = await client.patch(
            "/v1/me/preferences", headers=headers, json={"daily_minutes": 15}
        )

        assert response.status_code == 200
        after = response.json()["preferences"]
        assert after["daily_minutes"] == 15
        assert after["onboarding_status"] == before["onboarding_status"] == "not_started"
        changing_fields = {"daily_minutes", "updated_at"}
        assert {key: value for key, value in after.items() if key not in changing_fields} == {
            key: value for key, value in before.items() if key not in changing_fields
        }


@pytest.mark.parametrize(
    "payload",
    [
        {"unknown_field": "not allowed"},
        {"age_band": "centuries_old"},
        {"connection": "martian"},
        {"goal": "invalid_goal"},
        {"style": "invalid_style"},
        {"placement_level": "impossible"},
    ],
)
async def test_patch_preferences_rejects_unknown_fields_and_invalid_enums(
    client, database_url, user_id, auth_headers, payload
):
    with remove_test_users(database_url, user_id):
        response = await client.patch(
            "/v1/me/preferences", headers=auth_headers(subject=user_id), json=payload
        )
        assert response.status_code == 422


async def test_patch_preferences_validates_iana_timezone_names(
    client, database_url, user_id, auth_headers
):
    headers = auth_headers(subject=user_id)
    with remove_test_users(database_url, user_id):
        valid = await client.patch(
            "/v1/me/preferences", headers=headers, json={"timezone": "Pacific/Auckland"}
        )
        invalid = await client.patch(
            "/v1/me/preferences", headers=headers, json={"timezone": "Not/A_Real_Timezone"}
        )

        assert valid.status_code == 200
        assert valid.json()["preferences"]["timezone"] == "Pacific/Auckland"
        assert invalid.status_code == 422
        profile = await client.get("/v1/me", headers=headers)
        assert profile.json()["preferences"]["timezone"] == "Pacific/Auckland"


async def test_me_endpoints_are_scoped_only_to_each_token_subject(
    client, database_url, auth_headers
):
    first_id, second_id = uuid.uuid4(), uuid.uuid4()
    first_headers = auth_headers(subject=first_id, user_metadata={"full_name": "First Owner"})
    second_headers = auth_headers(subject=second_id, user_metadata={"full_name": "Second Owner"})
    with remove_test_users(database_url, first_id, second_id):
        first = await client.get(
            "/v1/me", headers=first_headers, params={"user_id": str(second_id)}
        )
        second = await client.get(
            "/v1/me", headers=second_headers, params={"user_id": str(first_id)}
        )
        assert first.status_code == second.status_code == 200
        assert first.json()["id"] == str(first_id)
        assert first.json()["display_name"] == "First Owner"
        assert second.json()["id"] == str(second_id)
        assert second.json()["display_name"] == "Second Owner"

        assert (
            await client.patch(
                "/v1/me/preferences",
                headers=first_headers,
                params={"user_id": str(second_id)},
                json={"daily_minutes": 30},
            )
        ).status_code == 200
        first_after = (await client.get("/v1/me", headers=first_headers)).json()
        second_after = (await client.get("/v1/me", headers=second_headers)).json()
        assert first_after["preferences"]["daily_minutes"] == 30
        assert second_after["preferences"]["daily_minutes"] != 30


@pytest.mark.parametrize(
    "field",
    ["active_language", "age_band", "connection", "goal", "style"],
)
async def test_patch_preferences_rejects_null_for_required_selection_fields(
    client, database_url, user_id, auth_headers, field
):
    with remove_test_users(database_url, user_id):
        response = await client.patch(
            "/v1/me/preferences",
            headers=auth_headers(subject=user_id),
            json={field: None},
        )
        assert response.status_code == 422


async def test_patch_preferences_clears_nullable_fields(
    client, database_url, user_id, auth_headers
):
    headers = auth_headers(subject=user_id)
    with remove_test_users(database_url, user_id):
        assert (await client.get("/v1/me", headers=headers)).status_code == 200
        populated = await client.patch(
            "/v1/me/preferences",
            headers=headers,
            json={
                "meta_language": "eng",
                "reminder_time": "09:30:00",
                "placement_level": "beginner",
                "onboarding_last_screen": 4,
            },
        )
        assert populated.status_code == 200

        cleared = await client.patch(
            "/v1/me/preferences",
            headers=headers,
            json={
                "meta_language": None,
                "reminder_time": None,
                "placement_level": None,
                "onboarding_last_screen": None,
            },
        )

        assert cleared.status_code == 200
        preferences = cleared.json()["preferences"]
        assert preferences["meta_language"] is None
        assert preferences["reminder_time"] is None
        assert preferences["placement_level"] is None
        assert preferences["onboarding_last_screen"] is None


async def test_patch_preferences_resolves_meta_language_code_to_stored_id(
    client, database_url, user_id, auth_headers
):
    headers = auth_headers(subject=user_id)
    with remove_test_users(database_url, user_id):
        response = await client.patch(
            "/v1/me/preferences", headers=headers, json={"meta_language": "nld"}
        )
        assert response.status_code == 200
        assert response.json()["preferences"]["meta_language"] == "nld"
        with db_connection(database_url) as conn:
            stored = conn.execute(
                """
                SELECT stored.id, language.id
                  FROM user_preferences preferences
                  JOIN languages stored ON stored.id = preferences.meta_language_id
                  JOIN languages language ON language.code = 'nld'
                 WHERE preferences.user_id = %s
                """,
                (user_id,),
            ).fetchone()
        assert stored[0] == stored[1]


async def test_patch_preferences_clears_meta_language_code(
    client, database_url, user_id, auth_headers
):
    headers = auth_headers(subject=user_id)
    with remove_test_users(database_url, user_id):
        assert (
            await client.patch("/v1/me/preferences", headers=headers, json={"meta_language": "nld"})
        ).status_code == 200
        response = await client.patch(
            "/v1/me/preferences", headers=headers, json={"meta_language": None}
        )
        assert response.status_code == 200
        assert response.json()["preferences"]["meta_language"] is None
        with db_connection(database_url) as conn:
            stored = conn.execute(
                "SELECT meta_language_id FROM user_preferences WHERE user_id = %s",
                (user_id,),
            ).fetchone()[0]
        assert stored is None


@pytest.mark.parametrize("code", ["ibo", "zzz"])
async def test_patch_preferences_rejects_invalid_meta_language_codes(
    client, database_url, user_id, auth_headers, code
):
    with remove_test_users(database_url, user_id):
        response = await client.patch(
            "/v1/me/preferences",
            headers=auth_headers(subject=user_id),
            json={"meta_language": code},
        )
        assert response.status_code == 422


async def test_patch_preferences_rejects_non_learnable_active_language(
    client, database_url, user_id, auth_headers
):
    with remove_test_users(database_url, user_id):
        response = await client.patch(
            "/v1/me/preferences",
            headers=auth_headers(subject=user_id),
            json={"active_language": "eng"},
        )
        assert response.status_code == 422


@pytest.mark.parametrize(
    ("payload", "language_name"),
    [
        ({"active_language": "yor"}, "Yoruba"),
        ({"meta_language": "fra"}, "French"),
    ],
)
async def test_patch_preferences_rejects_languages_that_are_not_yet_available(
    client, database_url, user_id, auth_headers, payload, language_name
):
    with remove_test_users(database_url, user_id):
        response = await client.patch(
            "/v1/me/preferences", headers=auth_headers(subject=user_id), json=payload
        )

    assert response.status_code == 422
    assert language_name in response.json()["detail"]
    assert "not yet available" in response.json()["detail"]


async def test_patch_preferences_accepts_available_target_and_meta_languages(
    client, database_url, user_id, auth_headers
):
    with remove_test_users(database_url, user_id):
        response = await client.patch(
            "/v1/me/preferences",
            headers=auth_headers(subject=user_id),
            json={"active_language": "ibo", "meta_language": "nld"},
        )

    assert response.status_code == 200
    assert response.json()["preferences"]["active_language"] == "ibo"
    assert response.json()["preferences"]["meta_language"] == "nld"


async def test_complete_onboarding_is_idempotent_and_keeps_completed_at(
    client, database_url, user_id, auth_headers
):
    headers = auth_headers(subject=user_id)
    with remove_test_users(database_url, user_id):
        first = await client.post("/v1/me/onboarding/complete", headers=headers)
        second = await client.post("/v1/me/onboarding/complete", headers=headers)

        assert first.status_code == second.status_code == 200
        first_preferences = first.json()["preferences"]
        second_preferences = second.json()["preferences"]
        assert first_preferences["onboarding_status"] == "completed"
        assert first_preferences["completed_at"] is not None
        assert second_preferences["completed_at"] == first_preferences["completed_at"]


async def test_skip_onboarding_records_screen_four(client, database_url, user_id, auth_headers):
    with remove_test_users(database_url, user_id):
        response = await client.post(
            "/v1/me/onboarding/skip",
            headers=auth_headers(subject=user_id),
            json={"onboarding_last_screen": 4},
        )

        assert response.status_code == 200
        preferences = response.json()["preferences"]
        assert preferences["onboarding_status"] == "skipped"
        assert preferences["onboarding_last_screen"] == 4


async def test_onboarding_screen_ten_is_accepted_by_preferences_and_skip(
    client, database_url, user_id, auth_headers
):
    headers = auth_headers(subject=user_id)
    with remove_test_users(database_url, user_id):
        preferences_response = await client.patch(
            "/v1/me/preferences",
            headers=headers,
            json={"onboarding_last_screen": 10},
        )
        skip_response = await client.post(
            "/v1/me/onboarding/skip",
            headers=headers,
            json={"onboarding_last_screen": 10},
        )

    assert preferences_response.status_code == 200
    assert preferences_response.json()["preferences"]["onboarding_last_screen"] == 10
    assert skip_response.status_code == 200
    assert skip_response.json()["preferences"]["onboarding_last_screen"] == 10


@pytest.mark.parametrize("screen", [0, 21])
async def test_onboarding_screen_outside_sanity_bound_is_rejected(
    client, user_id, auth_headers, screen
):
    headers = auth_headers(subject=user_id)

    preferences_response = await client.patch(
        "/v1/me/preferences",
        headers=headers,
        json={"onboarding_last_screen": screen},
    )
    skip_response = await client.post(
        "/v1/me/onboarding/skip",
        headers=headers,
        json={"onboarding_last_screen": screen},
    )

    assert preferences_response.status_code == 422
    assert skip_response.status_code == 422


async def test_skip_without_body_preserves_existing_screen(
    client, database_url, user_id, auth_headers
):
    headers = auth_headers(subject=user_id)
    with remove_test_users(database_url, user_id):
        assert (
            await client.patch(
                "/v1/me/preferences",
                headers=headers,
                json={"onboarding_last_screen": 3},
            )
        ).status_code == 200

        response = await client.post("/v1/me/onboarding/skip", headers=headers)

        assert response.status_code == 200
        preferences = response.json()["preferences"]
        assert preferences["onboarding_status"] == "skipped"
        assert preferences["onboarding_last_screen"] == 3


async def test_skip_with_explicit_null_clears_existing_screen(
    client, database_url, user_id, auth_headers
):
    headers = auth_headers(subject=user_id)
    with remove_test_users(database_url, user_id):
        assert (
            await client.patch(
                "/v1/me/preferences",
                headers=headers,
                json={"onboarding_last_screen": 3},
            )
        ).status_code == 200

        response = await client.post(
            "/v1/me/onboarding/skip",
            headers=headers,
            json={"onboarding_last_screen": None},
        )

        assert response.status_code == 200
        preferences = response.json()["preferences"]
        assert preferences["onboarding_status"] == "skipped"
        assert preferences["onboarding_last_screen"] is None


async def test_repeated_skip_is_idempotent_and_preserves_first_terminal_screen(
    client, database_url, user_id, auth_headers
):
    headers = auth_headers(subject=user_id)
    with remove_test_users(database_url, user_id):
        first = await client.post(
            "/v1/me/onboarding/skip",
            headers=headers,
            json={"onboarding_last_screen": 5},
        )
        repeated = await client.post(
            "/v1/me/onboarding/skip",
            headers=headers,
            json={"onboarding_last_screen": 2},
        )

        assert first.status_code == repeated.status_code == 200
        assert first.json()["preferences"]["onboarding_status"] == "skipped"
        assert first.json()["preferences"]["onboarding_last_screen"] == 5
        repeated_preferences = repeated.json()["preferences"]
        assert repeated_preferences["onboarding_status"] == "skipped"
        assert repeated_preferences["onboarding_last_screen"] == 5


async def test_terminal_onboarding_states_cannot_overwrite_each_other(
    client, database_url, auth_headers
):
    completed_id, skipped_id = uuid.uuid4(), uuid.uuid4()
    completed_headers = auth_headers(subject=completed_id)
    skipped_headers = auth_headers(subject=skipped_id)
    with remove_test_users(database_url, completed_id, skipped_id):
        completed = await client.post("/v1/me/onboarding/complete", headers=completed_headers)
        completed_at = completed.json()["preferences"]["completed_at"]
        skip_after_complete = await client.post(
            "/v1/me/onboarding/skip",
            headers=completed_headers,
            json={"onboarding_last_screen": 4},
        )

        skipped = await client.post(
            "/v1/me/onboarding/skip",
            headers=skipped_headers,
            json={"onboarding_last_screen": 5},
        )
        complete_after_skip = await client.post(
            "/v1/me/onboarding/complete", headers=skipped_headers
        )

        assert completed.status_code == skip_after_complete.status_code == 200
        completed_preferences = skip_after_complete.json()["preferences"]
        assert completed_preferences["onboarding_status"] == "completed"
        assert completed_preferences["completed_at"] == completed_at
        assert completed_preferences["onboarding_last_screen"] is None

        assert skipped.status_code == complete_after_skip.status_code == 200
        skipped_preferences = complete_after_skip.json()["preferences"]
        assert skipped_preferences["onboarding_status"] == "skipped"
        assert skipped_preferences["onboarding_last_screen"] == 5
        assert skipped_preferences["completed_at"] is None


async def test_new_user_authenticated_track_resolves_default_foundations(
    client, database_url, user_id, auth_headers
):
    with remove_test_users(database_url, user_id):
        response = await client.get("/v1/me/track", headers=auth_headers(subject=user_id))

        assert response.status_code == 200
        resolved = response.json()
        assert resolved["track"]["slug"] == "ibo_foundations"
        assert resolved["track"]["units"]
        assert "matched_priority" in resolved
        assert resolved["is_fallback"] is True


async def test_authenticated_track_reports_correct_once_progress_even_out_of_order(
    client, database_url, user_id, auth_headers
):
    headers = auth_headers(subject=user_id)
    with remove_test_users(database_url, user_id):
        initial = await client.get("/v1/me/track", headers=headers)
        assert initial.status_code == 200
        initial_units = initial.json()["track"]["units"]
        first, second = initial_units[:2]
        assert first["progress"] == {"done": 0, "total": first["item_count"]}
        assert first["completed"] is False
        assert second["progress"] == {"done": 0, "total": second["item_count"]}
        assert second["completed"] is False

        first_ids = unit_content_ids(database_url, "ibo_foundations", first["position"])
        with db_connection(database_url) as conn:
            conn.execute(
                """
                INSERT INTO user_progress(user_id, content_id, times_seen, times_correct)
                VALUES (%s, %s, 1, 0)
                """,
                (user_id, first_ids[0]),
            )

        seen_only = await client.get("/v1/me/track", headers=headers)
        seen_only_first = seen_only.json()["track"]["units"][0]
        assert seen_only_first["progress"]["done"] == 0
        assert seen_only_first["completed"] is False

        second_ids = unit_content_ids(database_url, "ibo_foundations", second["position"])
        with db_connection(database_url) as conn:
            conn.executemany(
                """
                INSERT INTO user_progress(user_id, content_id, times_seen, times_correct)
                VALUES (%s, %s, 1, 1)
                """,
                [(user_id, content_id) for content_id in second_ids],
            )

        out_of_order = await client.get("/v1/me/track", headers=headers)
        out_of_order_units = out_of_order.json()["track"]["units"]
        assert out_of_order_units[0]["progress"]["done"] == 0
        assert out_of_order_units[0]["completed"] is False
        assert out_of_order_units[1]["progress"] == {
            "done": len(second_ids),
            "total": len(second_ids),
        }
        assert out_of_order_units[1]["completed"] is True

        with db_connection(database_url) as conn:
            conn.executemany(
                """
                INSERT INTO user_progress(user_id, content_id, times_seen, times_correct)
                VALUES (%s, %s, 1, 1)
                ON CONFLICT (user_id, content_id) DO UPDATE
                    SET times_seen = EXCLUDED.times_seen,
                        times_correct = EXCLUDED.times_correct
                """,
                [(user_id, content_id) for content_id in first_ids],
            )

        advanced = await client.get("/v1/me/track", headers=headers)
        advanced_first = advanced.json()["track"]["units"][0]
        assert advanced_first["progress"] == {
            "done": len(first_ids),
            "total": len(first_ids),
        }
        assert advanced_first["completed"] is True


async def test_authenticated_track_uses_only_token_owners_stored_preferences(
    client, database_url, auth_headers
):
    native_id, other_id = uuid.uuid4(), uuid.uuid4()
    native_headers = auth_headers(subject=native_id)
    other_headers = auth_headers(subject=other_id)
    with remove_test_users(database_url, native_id, other_id):
        assert (await client.get("/v1/me", headers=other_headers)).status_code == 200
        patched = await client.patch(
            "/v1/me/preferences",
            headers=native_headers,
            json={"connection": "aboriginal_native"},
        )
        assert patched.status_code == 200

        authenticated = await client.get(
            "/v1/me/track",
            headers=native_headers,
            params={"user_id": str(other_id)},
        )
        public = await client.get("/v1/tracks/resolve", params={"connection": "aboriginal_native"})
        other = await client.get("/v1/me/track", headers=other_headers)

        assert authenticated.status_code == public.status_code == other.status_code == 200
        authenticated_body = authenticated.json()
        public_body = public.json()
        assert authenticated_body["track"]["slug"] == public_body["track"]["slug"]
        assert len(authenticated_body["track"]["units"]) == len(public_body["track"]["units"])
        for authenticated_unit, public_unit in zip(
            authenticated_body["track"]["units"], public_body["track"]["units"], strict=True
        ):
            assert {key: authenticated_unit[key] for key in public_unit} == public_unit
            assert authenticated_unit["progress"] == {
                "done": 0,
                "total": min(public_unit["available"], public_unit["item_count"]),
            }
            assert authenticated_unit["completed"] is False
            assert "progress" not in public_unit
            assert "completed" not in public_unit
        assert authenticated_body["track"]["slug"] == "ibo_native_advanced"
        assert authenticated_body["track"]["units"]
        assert "matched_priority" in authenticated_body
        assert authenticated_body["is_fallback"] is False
        assert other.json()["track"]["slug"] == "ibo_foundations"
