from __future__ import annotations

import uuid

import pytest
from app.auth import current_user
from app.config import Settings
from app.main import create_app
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


@pytest.mark.asyncio
async def test_all_admin_routes_return_403_for_a_learner():
    app: FastAPI = create_app()
    app.dependency_overrides[current_user] = lambda: {"id": uuid.uuid4(), "role": "learner"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for method, path, body in ADMIN_REQUESTS:
            response = await client.request(method, path, json=body)
            assert response.status_code == 403, (method, path, response.text)


@pytest.mark.asyncio
async def test_all_admin_routes_return_401_without_authentication():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for method, path, body in ADMIN_REQUESTS:
            response = await client.request(method, path, json=body)
            assert response.status_code == 401, (method, path, response.text)


def test_admin_email_matching_is_trimmed_and_case_insensitive(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", " Founder@Example.com, admin@example.com ,, ")
    settings = Settings()
    assert settings.is_admin_email("founder@example.com")
    assert settings.is_admin_email(" ADMIN@example.COM ")
    assert not settings.is_admin_email("learner@example.com")
