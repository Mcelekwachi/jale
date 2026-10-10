"""Configuration. Everything comes from the environment — nothing is baked
into the image, so the same container runs locally, in CI and in production."""

from __future__ import annotations

import os
from functools import lru_cache
from urllib.parse import urlparse


class Settings:
    def __init__(self) -> None:
        self.env: str = os.getenv("APP_ENV", "development")
        self.database_url: str = os.getenv("DATABASE_URL", "")
        self.default_language: str = os.getenv("DEFAULT_LANGUAGE", "ibo")
        self.default_meta_language: str = os.getenv("DEFAULT_META_LANGUAGE", "eng")
        self.supabase_jwt_secret: str | None = os.getenv("SUPABASE_JWT_SECRET") or None
        project_url = os.getenv("SUPABASE_PROJECT_URL", "").strip().rstrip("/")
        if not project_url:
            raise ValueError(
                "SUPABASE_PROJECT_URL is required — JWKS verification cannot run without it"
            )
        parsed_project_url = urlparse(project_url)
        try:
            _ = parsed_project_url.port
        except ValueError:
            raise ValueError("SUPABASE_PROJECT_URL must be a valid https URL") from None
        if (
            parsed_project_url.scheme != "https"
            or not parsed_project_url.hostname
            or parsed_project_url.username
            or parsed_project_url.password
            or parsed_project_url.path not in {"", "/"}
            or parsed_project_url.params
            or parsed_project_url.query
            or parsed_project_url.fragment
        ):
            raise ValueError("SUPABASE_PROJECT_URL must be a valid https URL")
        self.supabase_project_url: str = project_url
        self.supabase_jwt_audience: str = os.getenv("SUPABASE_JWT_AUDIENCE", "authenticated")
        # Optional. Only used to delete a person's login when they delete their account.
        self.supabase_service_role_key: str | None = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or None

        # Vercel preview deployments get their own URL per branch, so the
        # frontend origin list has to be configurable rather than hardcoded.
        raw_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173")
        self.cors_origins: list[str] = [o.strip() for o in raw_origins.split(",") if o.strip()]

        self.pool_min_size: int = int(os.getenv("DB_POOL_MIN", "1"))
        self.pool_max_size: int = int(os.getenv("DB_POOL_MAX", "5"))
        self.max_page_size: int = int(os.getenv("MAX_PAGE_SIZE", "200"))
        self.admin_emails: frozenset[str] = frozenset(
            email.strip().casefold()
            for email in os.getenv("ADMIN_EMAILS", "").split(",")
            if email.strip()
        )

    def is_admin_email(self, email: str | None) -> bool:
        return isinstance(email, str) and email.strip().casefold() in self.admin_emails

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
