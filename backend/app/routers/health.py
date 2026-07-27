"""Liveness and readiness.

/health   never touches the database — Railway and Render use it to decide
          whether the container is up.
/health/db verifies the pool and that content has actually been seeded, which
          is the failure that would otherwise reach users as an empty app.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.config import get_settings
from app.db import fetch_one

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "env": get_settings().env}


@router.get("/health/db")
async def health_db(response: Response) -> dict:
    try:
        row = await fetch_one(
            """
            SELECT (SELECT count(*) FROM content_items WHERE status='published') AS content,
                   (SELECT count(*) FROM tracks) AS tracks,
                   (SELECT count(*) FROM languages WHERE is_active) AS languages
            """
        )
    except Exception as exc:  # noqa: BLE001 — surfaced as an unhealthy response
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable", "error": str(exc)}

    seeded = bool(row and row["content"] > 0 and row["tracks"] > 0)
    if not seeded:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ok" if seeded else "not_seeded",
        "content_items": row["content"] if row else 0,
        "tracks": row["tracks"] if row else 0,
        "active_languages": row["languages"] if row else 0,
    }
