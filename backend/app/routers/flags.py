from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.auth import current_user
from app.schemas import ContentFlag, ContentFlagCreate, ContentFlagDelete
from app.services import flags
from app.services.meta_languages import resolve_meta_language_id

router = APIRouter(prefix="/v1/content", tags=["content-flags"])


@router.post("/{content_id}/flag", response_model=ContentFlag)
async def create_content_flag(
    content_id: int,
    payload: ContentFlagCreate,
    user: Annotated[dict, Depends(current_user)],
) -> dict:
    meta_language_id = (
        await resolve_meta_language_id(payload.meta_language)
        if payload.meta_language is not None
        else None
    )
    return await flags.create_flag(
        content_id,
        UUID(str(user["id"])),
        payload.reason.value,
        payload.note,
        meta_language_id,
    )


@router.delete("/{content_id}/flag", response_model=ContentFlagDelete)
async def delete_content_flag(
    content_id: int,
    user: Annotated[dict, Depends(current_user)],
    meta_language: str | None = None,
) -> dict:
    meta_language_id = (
        await resolve_meta_language_id(meta_language) if meta_language is not None else None
    )
    await flags.delete_flag(content_id, UUID(str(user["id"])), meta_language_id)
    return {"deleted": True}
