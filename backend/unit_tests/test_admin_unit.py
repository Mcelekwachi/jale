from __future__ import annotations

import uuid

import pytest
from app.auth import current_user, require_admin
from app.config import Settings
from app.main import create_app
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


@pytest.mark.asyncio
async def test_flag_queue_rejects_invalid_reason_with_422():
    app = create_app()
    app.dependency_overrides[require_admin] = lambda: {"id": uuid.uuid4(), "role": "admin"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/admin/flags?reason=not_a_real_reason")

    assert response.status_code == 422


def test_admin_email_matching_is_trimmed_and_case_insensitive(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", " Founder@Example.com, admin@example.com ,, ")
    settings = Settings()
    assert settings.is_admin_email("founder@example.com")
    assert settings.is_admin_email(" ADMIN@example.COM ")
    assert not settings.is_admin_email("learner@example.com")


def test_admin_data_endpoints_publish_named_response_models():
    schema = create_app().openapi()

    expected_refs = {
        ("/v1/admin/flags", "get"): "AdminFlagQueueItem",
        ("/v1/admin/flags/{flag_id}", "patch"): "AdminFlagDecisionResult",
        ("/v1/admin/content/{content_id}/flags/resolve", "post"): "BulkFlagResolutionResult",
        ("/v1/admin/content", "get"): "AdminContentPage",
        ("/v1/admin/content/{content_id}", "get"): "AdminContentDetail",
        ("/v1/admin/content/{content_id}", "patch"): "AdminContentState",
        (
            "/v1/admin/content/{content_id}/translations/{meta_language}",
            "patch",
        ): "AdminTranslationState",
        ("/v1/admin/content/{content_id}/revisions", "get"): "AdminContentRevision",
    }

    for (path, method), model in expected_refs.items():
        response_schema = schema["paths"][path][method]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]
        refs = {response_schema.get("$ref"), response_schema.get("items", {}).get("$ref")}
        assert f"#/components/schemas/{model}" in refs, (path, method, response_schema)

    for method in ("verify", "unverify"):
        response_schema = schema["paths"][f"/v1/admin/content/{{content_id}}/{method}"]["post"][
            "responses"
        ]["200"]["content"]["application/json"]["schema"]
        assert response_schema == {"$ref": "#/components/schemas/AdminVerificationResult"}

    assert "AdminFlagQueueFlag" in schema["components"]["schemas"]
    models = schema["components"]["schemas"]
    content_fields = models["AdminContentState"]["properties"]
    assert {"language", "dialect", "category", "verified_by_name"} <= content_fields.keys()
    assert not {"language_id", "dialect_id", "category_id"} & content_fields.keys()

    translation_fields = models["AdminTranslationState"]["properties"]
    assert {"meta_language", "verified_by_name"} <= translation_fields.keys()
    assert "meta_language_id" not in translation_fields

    flag_fields = models["AdminFlagDecisionResult"]["properties"]
    assert "meta_language" in flag_fields
    assert "meta_language_id" not in flag_fields

    verification_fields = models["AdminVerificationResult"]["properties"]
    assert set(verification_fields) == {"target", "content", "translation"}

    revision_fields = models["AdminContentRevision"]["properties"]
    for field in ("before_state", "after_state"):
        assert "raw database snapshot" in revision_fields[field]["description"].lower()
