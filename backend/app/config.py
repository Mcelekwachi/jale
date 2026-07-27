"""Configuration. Everything comes from the environment — nothing is baked
into the image, so the same container runs locally, in CI and in production."""

from __future__ import annotations

import os
from functools import lru_cache


class Settings:
    def __init__(self) -> None:
        self.env: str = os.getenv("APP_ENV", "development")
        self.database_url: str = os.getenv("DATABASE_URL", "")
        self.default_language: str = os.getenv("DEFAULT_LANGUAGE", "ibo")

        # Vercel preview deployments get their own URL per branch, so the
        # frontend origin list has to be configurable rather than hardcoded.
        raw_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173")
        self.cors_origins: list[str] = [o.strip() for o in raw_origins.split(",") if o.strip()]

        self.pool_min_size: int = int(os.getenv("DB_POOL_MIN", "1"))
        self.pool_max_size: int = int(os.getenv("DB_POOL_MAX", "10"))
        self.max_page_size: int = int(os.getenv("MAX_PAGE_SIZE", "200"))

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
