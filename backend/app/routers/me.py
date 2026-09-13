from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException

from app.auth import current_user
from app.schemas import (
    PreferencesPatch,
    ResolvedUserTrack,
    SkipOnboarding,
    UserProfile,
    UserStats,
    patch_values,
)
from app.services import track_resolver
from app.services.languages import resolve_learnable_language_id
from app.services.meta_languages import resolve_available_meta_language_id
from app.services.study_progress import get_stats, get_utc_now
from app.services.users import (
    complete_onboarding,
    get_user_profile,
    get_user_track_preferences,
    skip_onboarding,
    update_preferences,
)

router = APIRouter(prefix="/v1/me", tags=["me"])


def _user_id(user: dict) -> UUID:
    return UUID(str(user["id"]))


@router.get("", response_model=UserProfile)
async def read_me(user: Annotated[dict, Depends(current_user)]) -> dict:
    return await get_user_profile(_user_id(user))


@router.get("/stats", response_model=UserStats)
async def read_stats(
    user: Annotated[dict, Depends(current_user)],
    now: Annotated[datetime, Depends(get_utc_now)],
) -> dict:
    return await get_stats(_user_id(user), now)


@router.get("/track", response_model=ResolvedUserTrack)
async def read_my_track(user: Annotated[dict, Depends(current_user)]) -> dict:
    user_id = _user_id(user)
    preferences = await get_user_track_preferences(user_id)
    language = preferences.pop("language")
    track, priority = await track_resolver.resolve(language, **preferences)
    if track is None:
        raise HTTPException(
            status_code=404,
            detail=f"no track resolved for language {language!r} — is it seeded?",
        )
    track = dict(track)
    track["units"] = await track_resolver.get_units_with_progress(language, track["slug"], user_id)
    return {
        "track": track,
        "matched_priority": priority,
        "is_fallback": bool(track["is_default"]),
    }


@router.patch("/preferences", response_model=UserProfile)
async def patch_preferences(
    payload: PreferencesPatch,
    user: Annotated[dict, Depends(current_user)],
) -> dict:
    changes = patch_values(payload)
    if "active_language" in changes:
        changes["active_language_id"] = await resolve_learnable_language_id(
            changes.pop("active_language")
        )
    if "meta_language" in changes:
        code = changes.pop("meta_language")
        changes["meta_language_id"] = (
            await resolve_available_meta_language_id(code) if code is not None else None
        )
    return await update_preferences(_user_id(user), changes)


@router.post("/onboarding/complete", response_model=UserProfile)
async def finish_onboarding(user: Annotated[dict, Depends(current_user)]) -> dict:
    return await complete_onboarding(_user_id(user))


@router.post("/onboarding/skip", response_model=UserProfile)
async def skip_onboarding_route(
    user: Annotated[dict, Depends(current_user)],
    payload: Annotated[SkipOnboarding | None, Body()] = None,
) -> dict:
    supplied = payload is not None and "onboarding_last_screen" in payload.model_fields_set
    return await skip_onboarding(
        _user_id(user),
        screen_supplied=supplied,
        screen=payload.onboarding_last_screen if payload is not None else None,
    )
