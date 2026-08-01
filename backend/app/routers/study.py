from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.auth import current_user
from app.schemas import StudyAnswersRequest, StudyAnswersResponse
from app.services.study_progress import get_utc_now, record_answers

router = APIRouter(prefix="/v1/study", tags=["study"])


@router.post("/answers", response_model=StudyAnswersResponse)
async def submit_answers(
    payload: StudyAnswersRequest,
    user: Annotated[dict, Depends(current_user)],
    now: Annotated[datetime, Depends(get_utc_now)],
) -> dict:
    return await record_answers(UUID(str(user["id"])), payload.answers, now)
