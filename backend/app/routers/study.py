from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.auth import current_user
from app.config import get_settings
from app.schemas import (
    DueStudyItems,
    StudyAnswersRequest,
    StudyAnswersResponse,
    StudyDirection,
)
from app.services import study
from app.services.meta_languages import resolve_meta_languages
from app.services.study_progress import get_utc_now, record_answers

router = APIRouter(prefix="/v1/study", tags=["study"])


@router.get("/due", response_model=DueStudyItems)
async def get_due_items(
    user: Annotated[dict, Depends(current_user)],
    now: Annotated[datetime, Depends(get_utc_now)],
    meta_language: str | None = None,
    direction: StudyDirection = StudyDirection.target_to_meta,
    limit: int = Query(default=20, ge=1, le=50),
) -> dict:
    settings = get_settings()
    requested_meta_language, default_meta_language = await resolve_meta_languages(
        meta_language, settings.default_meta_language
    )
    items = await study.build_due_items(
        UUID(str(user["id"])),
        requested_meta_language,
        default_meta_language,
        direction,
        now,
        limit,
    )
    return {"items": items}


@router.post("/answers", response_model=StudyAnswersResponse)
async def submit_answers(
    payload: StudyAnswersRequest,
    user: Annotated[dict, Depends(current_user)],
    now: Annotated[datetime, Depends(get_utc_now)],
) -> dict:
    return await record_answers(UUID(str(user["id"])), payload.answers, now)
