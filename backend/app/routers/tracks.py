from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.config import get_settings
from app.schemas import (
    AgeBand,
    Connection,
    Goal,
    ResolvedTrack,
    StudyDirection,
    StudySession,
    Style,
    Track,
)
from app.services import study, track_resolver
from app.services.meta_languages import resolve_meta_languages

router = APIRouter(prefix="/v1/tracks", tags=["tracks"])


def _lang(language: str | None) -> str:
    return language or get_settings().default_language


@router.get("", response_model=list[Track])
async def list_tracks(language: str | None = None) -> list[dict]:
    return await track_resolver.list_tracks(_lang(language))


@router.get("/resolve", response_model=ResolvedTrack)
async def resolve_track(
    language: str | None = None,
    age: AgeBand | None = Query(default=None, description="onboarding screen 2"),
    connection: Connection | None = Query(default=None, description="screen 3"),
    goal: Goal | None = Query(default=None, description="screen 4"),
    style: Style | None = Query(default=None, description="screen 5"),
) -> dict:
    """Map onboarding answers to a curriculum track.

    Every parameter is optional. Onboarding is skippable at any screen, so a
    request with no parameters at all is valid and returns the default track.
    """
    code = _lang(language)
    track, priority = await track_resolver.resolve(
        code,
        age=age.value if age else None,
        connection=connection.value if connection else None,
        goal=goal.value if goal else None,
        style=style.value if style else None,
    )
    if track is None:
        raise HTTPException(
            status_code=404,
            detail=f"no track resolved for language {code!r} — is it seeded?",
        )
    track = dict(track)
    track["units"] = await track_resolver.get_units(code, track["slug"])
    return {
        "track": track,
        "matched_priority": priority,
        "is_fallback": bool(track["is_default"]),
    }


@router.get("/{slug}", response_model=Track)
async def get_track(slug: str, language: str | None = None) -> dict:
    code = _lang(language)
    track = await track_resolver.get_track(code, slug)
    if track is None:
        raise HTTPException(status_code=404, detail=f"no track {slug!r}")
    track = dict(track)
    track["units"] = await track_resolver.get_units(code, slug)
    return track


@router.get("/{slug}/units/{position}/items", response_model=StudySession)
async def get_unit_items(
    slug: str,
    position: int,
    language: str | None = None,
    meta_language: str | None = None,
    direction: StudyDirection = StudyDirection.target_to_meta,
    shuffle_seed: int | None = Query(
        default=None,
        description="Pass a seed for reproducible ordering; omit for source order.",
    ),
) -> dict:
    settings = get_settings()
    requested_meta_language, default_meta_language = await resolve_meta_languages(
        meta_language, settings.default_meta_language
    )
    session = await study.build_session(
        _lang(language),
        slug,
        position,
        requested_meta_language,
        default_meta_language,
        direction,
        shuffle_seed,
    )
    if session is None:
        raise HTTPException(status_code=404, detail=f"no unit {position} on track {slug!r}")
    return session
