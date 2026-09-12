from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from app import auth
from app.config import Settings, get_settings
from app.routers.health import health
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

AUDIENCE = "authenticated"
PROJECT_URL = "https://test-project.supabase.co"
JWT_SECRET = "0123456789abcdef0123456789abcdef"


def credentials(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def claims(*, audience: str = AUDIENCE, expires_at: datetime | None = None) -> dict[str, object]:
    return {
        "sub": str(uuid.uuid4()),
        "aud": audience,
        "exp": expires_at or datetime.now(UTC) + timedelta(minutes=5),
    }


@pytest.fixture
def ec_signing_material():
    private_key = ec.generate_private_key(ec.SECP256R1())
    jwk = jwt.algorithms.ECAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    jwk.update({"kid": "test-ec-key", "use": "sig", "alg": "ES256"})
    return private_key, jwk


@pytest.fixture(autouse=True)
def auth_settings(monkeypatch):
    monkeypatch.setenv("SUPABASE_PROJECT_URL", PROJECT_URL)
    monkeypatch.setenv("SUPABASE_JWT_SECRET", JWT_SECRET)
    monkeypatch.setenv("SUPABASE_JWT_AUDIENCE", AUDIENCE)
    get_settings.cache_clear()
    if hasattr(auth, "_jwks_client"):
        auth._jwks_client.cache_clear()
    yield
    get_settings.cache_clear()
    if hasattr(auth, "_jwks_client"):
        auth._jwks_client.cache_clear()


def install_jwks(monkeypatch, jwk: dict[str, object], *, fail: bool = False) -> list[str]:
    requests: list[str] = []

    def fetch_jwks(client: jwt.PyJWKClient):
        requests.append(client.uri)
        if fail:
            raise jwt.PyJWKClientConnectionError("JWKS unavailable")
        jwk_set = {"keys": [jwk]}
        if client.jwk_set_cache is not None:
            client.jwk_set_cache.put(jwk_set)
        return jwk_set

    monkeypatch.setattr(jwt.PyJWKClient, "fetch_data", fetch_jwks)
    return requests


def mint_es256(private_key, *, kid: str = "test-ec-key", **claim_overrides) -> str:
    return jwt.encode(
        claims(**claim_overrides),
        private_key,
        algorithm="ES256",
        headers={"kid": kid},
    )


def assert_generic_401(token: str) -> None:
    with pytest.raises(HTTPException) as caught:
        auth._decode(credentials(token))
    assert caught.value.status_code == 401
    assert caught.value.detail == "Invalid authentication credentials"


def test_settings_requires_supabase_project_url(monkeypatch):
    monkeypatch.delenv("SUPABASE_PROJECT_URL", raising=False)

    with pytest.raises(ValueError, match="SUPABASE_PROJECT_URL"):
        Settings()


@pytest.mark.parametrize(
    "project_url",
    [
        "http://example.test",
        "not-a-url",
        "https://",
        "https://example.test/path",
        "https://example.test?query=value",
        "https://example.test#fragment",
        "https://example.test:invalid-port",
    ],
)
def test_settings_rejects_invalid_supabase_project_url(monkeypatch, project_url):
    monkeypatch.setenv("SUPABASE_PROJECT_URL", project_url)

    with pytest.raises(ValueError, match="SUPABASE_PROJECT_URL"):
        Settings()


def test_settings_allow_legacy_jwt_secret_to_be_absent(monkeypatch):
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)

    assert Settings().supabase_jwt_secret is None


@pytest.mark.asyncio
async def test_health_liveness_does_not_require_auth_configuration(monkeypatch):
    monkeypatch.delenv("SUPABASE_PROJECT_URL", raising=False)
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)

    assert await health() == {"status": "ok", "env": "development"}


def test_valid_es256_token_authenticates(monkeypatch, ec_signing_material):
    private_key, jwk = ec_signing_material
    requests = install_jwks(monkeypatch, jwk)

    decoded = auth._decode(credentials(mint_es256(private_key)))

    assert decoded["aud"] == AUDIENCE
    assert len(requests) == 1


def test_valid_hs256_token_still_authenticates():
    token = jwt.encode(claims(), JWT_SECRET, algorithm="HS256")

    assert auth._decode(credentials(token))["aud"] == AUDIENCE


def test_key_absent_from_jwks_is_rejected(monkeypatch, ec_signing_material):
    private_key, jwk = ec_signing_material
    install_jwks(monkeypatch, jwk)

    assert_generic_401(mint_es256(private_key, kid="unknown-key"))


def test_alg_none_is_rejected():
    token = jwt.encode(claims(), key="", algorithm="none")

    assert_generic_401(token)


def test_expired_es256_token_is_rejected(monkeypatch, ec_signing_material):
    private_key, jwk = ec_signing_material
    install_jwks(monkeypatch, jwk)
    token = mint_es256(private_key, expires_at=datetime.now(UTC) - timedelta(seconds=1))

    assert_generic_401(token)


def test_wrong_audience_es256_token_is_rejected(monkeypatch, ec_signing_material):
    private_key, jwk = ec_signing_material
    install_jwks(monkeypatch, jwk)

    assert_generic_401(mint_es256(private_key, audience="wrong-audience"))


def test_jwks_fetch_failure_is_rejected(monkeypatch, ec_signing_material):
    private_key, jwk = ec_signing_material
    install_jwks(monkeypatch, jwk, fail=True)

    assert_generic_401(mint_es256(private_key))


def test_jwks_is_fetched_once_across_many_tokens(monkeypatch, ec_signing_material):
    private_key, jwk = ec_signing_material
    requests = install_jwks(monkeypatch, jwk)

    for _ in range(10):
        auth._decode(credentials(mint_es256(private_key)))

    assert requests == [f"{PROJECT_URL}/auth/v1/.well-known/jwks.json"]


def test_token_algorithm_must_match_jwk_algorithm(monkeypatch, ec_signing_material):
    private_key, jwk = ec_signing_material
    jwk["alg"] = "RS256"
    install_jwks(monkeypatch, jwk)

    assert_generic_401(mint_es256(private_key))
