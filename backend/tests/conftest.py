"""Test fixtures.

These tests run against a real PostgreSQL with the real schema and the real
235-row seed. Nothing is mocked: the queries contain enum casts and array
containment that a mock would happily accept and production would reject.

DATABASE_URL must point at a disposable database. CI provides one as a
service container; locally, use `docker compose up -d db`.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import jwt
import pytest
import pytest_asyncio
from db_test_utils import db_connection, pending_user_cleanup
from httpx import ASGITransport, AsyncClient

REPO_ROOT = Path(__file__).resolve().parents[2]

_TEST_JWT_SECRET = "0123456789abcdef0123456789abcdef"
_TEST_JWT_AUDIENCE = "authenticated"

# Settings are cached when the application is created, so auth configuration
# must exist before any fixture imports app.main.
os.environ["SUPABASE_JWT_SECRET"] = _TEST_JWT_SECRET
os.environ["SUPABASE_JWT_AUDIENCE"] = _TEST_JWT_AUDIENCE
os.environ["SUPABASE_PROJECT_URL"] = "https://test-project.supabase.co"
os.environ["PGOPTIONS"] = "-c lock_timeout=5s -c statement_timeout=10s"

pytest_plugins = ("pytest_asyncio",)


@pytest_asyncio.fixture(autouse=True)
async def cleanup_test_users(database_url: str):
    """Close API connections before bounded user-row teardown."""
    pending_user_cleanup.clear()
    yield

    from app.db import close_pool

    await close_pool()
    if pending_user_cleanup:
        with db_connection(database_url) as conn:
            conn.execute(
                "DELETE FROM app_users WHERE id = ANY(%s)",
                (list(pending_user_cleanup),),
            )
    pending_user_cleanup.clear()


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def mint_token() -> Callable[..., str]:
    def mint(
        *,
        subject: uuid.UUID | str | None = None,
        audience: str = _TEST_JWT_AUDIENCE,
        expires_at: datetime | None = None,
        email: str | None = None,
        user_metadata: dict[str, Any] | None = None,
        name: str | None = None,
        avatar_url: str | None = None,
    ) -> str:
        token_subject = str(subject or uuid.uuid4())
        claims: dict[str, Any] = {
            "sub": token_subject,
            "aud": audience,
            "exp": expires_at or datetime.now(UTC) + timedelta(minutes=15),
            "email": email or f"{token_subject}@example.test",
        }
        if user_metadata is not None:
            claims["user_metadata"] = user_metadata
        if name is not None:
            claims["name"] = name
        if avatar_url is not None:
            claims["avatar_url"] = avatar_url
        return jwt.encode(claims, _TEST_JWT_SECRET, algorithm="HS256")

    return mint


@pytest.fixture
def auth_headers(mint_token: Callable[..., str]) -> Callable[..., dict[str, str]]:
    def headers(**claims: Any) -> dict[str, str]:
        return {"Authorization": f"Bearer {mint_token(**claims)}"}

    return headers


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set")
    return url


@pytest.fixture(scope="session", autouse=True)
def seeded_database(database_url: str) -> str:
    """Apply schema.sql and seed Igbo content once per test session."""
    with db_connection(database_url) as conn:
        already = conn.execute("SELECT to_regclass('public.content_items') IS NOT NULL").fetchone()[
            0
        ]
        if not already:
            conn.execute((REPO_ROOT / "db" / "schema.sql").read_text(encoding="utf-8"))

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "db" / "seed" / "seed.py"), "--language", "ibo"],
        env={**os.environ, "DATABASE_URL": database_url},
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        pytest.fail(f"seed failed:\n{result.stdout}\n{result.stderr}")
    return database_url


@pytest_asyncio.fixture
async def client(seeded_database: str, cleanup_test_users: None):
    os.environ.setdefault("APP_ENV", "test")
    from app.db import close_pool
    from app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as c,
        app.router.lifespan_context(app),
    ):
        yield c
    await close_pool()
