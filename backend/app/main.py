"""Jalɛ API.

Phase 1 read path. No authentication yet: everything here is public content.
Write endpoints (progress, streaks, flags) arrive with Supabase Auth in the
next step and will sit behind a dependency, not scattered checks.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import close_pool, open_pool
from app.routers import (
    admin,
    children,
    content,
    flags,
    health,
    languages,
    me,
    profiles,
    study,
    tracks,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await open_pool()
    yield
    await close_pool()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Jalɛ API",
        version="0.1.0",
        description="African language learning. Phase 1: Central Igbo.",
        lifespan=lifespan,
        # Docs stay open in Phase 1 — it is how you and testers explore the API.
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(languages.router)
    app.include_router(content.router)
    app.include_router(flags.router)
    app.include_router(tracks.router)
    app.include_router(me.router)
    app.include_router(children.router)
    app.include_router(profiles.router)
    app.include_router(study.router)
    app.include_router(admin.router)
    return app


app = create_app()
