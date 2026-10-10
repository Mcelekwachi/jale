"""Parental consent: child profiles, age gate, export and deletion."""

from __future__ import annotations

import uuid

import psycopg
import pytest
from db_test_utils import db_connection, isolated_test_users

pytestmark = pytest.mark.asyncio

CHILD = {"nickname": "Ada", "birth_year": 2018, "consent": True}


async def _parent(client, auth_headers, *, confirmed: bool = True):
    parent_id = uuid.uuid4()
    headers = auth_headers(subject=parent_id)
    if confirmed:
        assert (await client.post("/v1/me/age", headers=headers)).status_code == 200
    return parent_id, headers


async def _add_child(client, headers, **overrides):
    response = await client.post("/v1/me/children", headers=headers, json={**CHILD, **overrides})
    assert response.status_code == 201, response.text
    return response.json()


async def test_adding_a_child_needs_age_gate_and_consent(client, auth_headers):
    parent_id, headers = await _parent(client, auth_headers, confirmed=False)
    with isolated_test_users(parent_id):
        denied = await client.post("/v1/me/children", headers=headers, json=CHILD)
        assert denied.status_code == 403

        await client.post("/v1/me/age", headers=headers)
        no_consent = await client.post(
            "/v1/me/children", headers=headers, json={**CHILD, "consent": False}
        )
        assert no_consent.status_code == 422
        bad_year = await client.post(
            "/v1/me/children", headers=headers, json={**CHILD, "birth_year": 1990}
        )
        assert bad_year.status_code == 422

        child = await _add_child(client, headers)
        assert child["nickname"] == "Ada"
        me = (await client.get("/v1/me", headers=headers)).json()
        assert me["age_confirmed_at"] is not None and me["is_child"] is False


async def test_child_profile_is_a_plain_private_learner(client, auth_headers, database_url):
    parent_id, headers = await _parent(client, auth_headers)
    with isolated_test_users(parent_id):
        child = await _add_child(client, headers)
        as_child = {**headers, "X-Profile-Id": child["id"]}

        me = (await client.get("/v1/me", headers=as_child)).json()
        assert me["id"] == child["id"]
        assert me["is_child"] is True
        assert me["email"] is None and me["share_slug"] is None
        assert me["preferences"]["age_band"] == "child_u13"

        with db_connection(database_url) as conn:
            consents = conn.execute(
                "SELECT policy_version FROM parental_consents WHERE child_user_id = %s",
                (child["id"],),
            ).fetchall()
            assert len(consents) == 1
            with pytest.raises(psycopg.errors.CheckViolation):
                conn.execute("UPDATE app_users SET role = 'admin' WHERE id = %s", (child["id"],))


async def test_profile_header_only_selects_own_children(client, auth_headers):
    parent_id, headers = await _parent(client, auth_headers)
    other_id, other_headers = await _parent(client, auth_headers)
    with isolated_test_users(parent_id, other_id):
        child = await _add_child(client, headers)

        stolen = await client.get("/v1/me", headers={**other_headers, "X-Profile-Id": child["id"]})
        assert stolen.status_code == 404
        unknown = await client.get("/v1/me", headers={**headers, "X-Profile-Id": str(uuid.uuid4())})
        assert unknown.status_code == 404
        garbage = await client.get("/v1/me", headers={**headers, "X-Profile-Id": "nope"})
        assert garbage.status_code == 400


async def test_child_progress_is_separate_and_never_admin(client, auth_headers, database_url):
    parent_id, headers = await _parent(client, auth_headers)
    with isolated_test_users(parent_id):
        with db_connection(database_url) as conn:
            conn.execute("UPDATE app_users SET role = 'admin' WHERE id = %s", (parent_id,))
        child = await _add_child(client, headers)
        as_child = {**headers, "X-Profile-Id": child["id"]}

        assert (await client.get("/v1/admin/users", headers=headers)).status_code == 200
        assert (await client.get("/v1/admin/users", headers=as_child)).status_code == 403

        parent_stats = (await client.get("/v1/me/stats", headers=headers)).json()
        child_stats = (await client.get("/v1/me/stats", headers=as_child)).json()
        assert parent_stats["total_mastered"] == child_stats["total_mastered"] == 0


async def test_child_has_no_public_profile(client, auth_headers, database_url):
    parent_id, headers = await _parent(client, auth_headers)
    with isolated_test_users(parent_id):
        child = await _add_child(client, headers)
        # The database refuses a public slug on a child outright.
        with db_connection(database_url) as conn, pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(
                "UPDATE app_users SET share_slug = 'kid-slug' WHERE id = %s", (child["id"],)
            )
        assert (await client.get("/v1/profile/kid-slug")).status_code == 404


async def test_child_limit(client, auth_headers):
    parent_id, headers = await _parent(client, auth_headers)
    with isolated_test_users(parent_id):
        for index in range(10):
            await _add_child(client, headers, nickname=f"Kid{index}")
        over = await client.post("/v1/me/children", headers=headers, json=CHILD)
        assert over.status_code == 409


async def test_export_then_delete_child(client, auth_headers, database_url):
    parent_id, headers = await _parent(client, auth_headers)
    with isolated_test_users(parent_id):
        child = await _add_child(client, headers)

        exported = await client.get(f"/v1/me/children/{child['id']}/export", headers=headers)
        assert exported.status_code == 200
        assert exported.json()["account"]["id"] == child["id"]
        assert "parent_pin_hash" not in exported.json()["account"]

        everything = (await client.get("/v1/me/export", headers=headers)).json()
        assert [c["account"]["id"] for c in everything["children"]] == [child["id"]]

        assert (
            await client.delete(f"/v1/me/children/{child['id']}", headers=headers)
        ).status_code == 204
        assert (await client.get("/v1/me/children", headers=headers)).json() == []
        with db_connection(database_url) as conn:
            for table, column in (
                ("app_users", "id"),
                ("user_preferences", "user_id"),
                ("user_stats", "user_id"),
                ("parental_consents", "child_user_id"),
            ):
                count = conn.execute(
                    f"SELECT count(*) FROM {table} WHERE {column} = %s", (child["id"],)
                ).fetchone()[0]
                assert count == 0, table
        again = await client.delete(f"/v1/me/children/{child['id']}", headers=headers)
        assert again.status_code == 404


async def test_delete_account_erases_children_too(client, auth_headers, database_url):
    parent_id, headers = await _parent(client, auth_headers)
    with isolated_test_users(parent_id):
        child = await _add_child(client, headers)

        refused = await client.delete("/v1/me", headers=headers)
        assert refused.status_code == 422

        assert (await client.delete("/v1/me?confirm=true", headers=headers)).status_code == 204
        with db_connection(database_url) as conn:
            remaining = conn.execute(
                "SELECT count(*) FROM app_users WHERE id = ANY(%s)",
                ([parent_id, uuid.UUID(child["id"])],),
            ).fetchone()[0]
        assert remaining == 0


async def test_parent_pin(client, auth_headers, database_url):
    parent_id, headers = await _parent(client, auth_headers)
    with isolated_test_users(parent_id):
        assert (await client.get("/v1/me/pin", headers=headers)).json() == {"has_pin": False}
        assert (
            await client.post("/v1/me/pin/verify", headers=headers, json={"pin": "1234"})
        ).json() == {"valid": False}
        assert (
            await client.put("/v1/me/pin", headers=headers, json={"pin": "1234"})
        ).status_code == 204
        assert (
            await client.post("/v1/me/pin/verify", headers=headers, json={"pin": "1234"})
        ).json() == {"valid": True}
        assert (
            await client.post("/v1/me/pin/verify", headers=headers, json={"pin": "9999"})
        ).json() == {"valid": False}
        assert (
            await client.put("/v1/me/pin", headers=headers, json={"pin": "12"})
        ).status_code == 422
        assert (await client.get("/v1/me/pin", headers=headers)).json() == {"has_pin": True}
        with db_connection(database_url) as conn:
            stored = conn.execute(
                "SELECT parent_pin_hash FROM app_users WHERE id = %s", (parent_id,)
            ).fetchone()[0]
        assert "1234" not in stored
