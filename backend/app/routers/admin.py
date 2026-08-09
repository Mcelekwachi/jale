from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.admin_schemas import (
    AdminContentPage,
    AdminContentPatch,
    AdminContentRevision,
    AdminContentState,
    AdminFlagDecisionResult,
    AdminFlagQueueItem,
    AdminTranslationPatch,
    AdminTranslationState,
    BulkFlagResolution,
    BulkFlagResolutionResult,
    ContributorGrant,
    FlagDecision,
    VerificationChange,
)
from app.auth import require_admin
from app.config import get_settings
from app.schemas import ContentType, Difficulty, FlagReason, patch_values
from app.services import admin

router = APIRouter(prefix="/v1/admin", tags=["admin"], dependencies=[Depends(require_admin)])
AdminUser = Annotated[dict, Depends(require_admin)]


@router.get("/flags", response_model=list[AdminFlagQueueItem])
async def flags_queue(
    status: Literal["open", "in_review", "resolved", "rejected"] = "open",
    reason: FlagReason | None = None,
    language: str | None = None,
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    return await admin.list_flags(
        status=status,
        reason=reason.value if reason else None,
        language=language,
        limit=min(limit, get_settings().max_page_size),
        offset=offset,
    )


@router.patch("/flags/{flag_id}", response_model=AdminFlagDecisionResult)
async def decide_flag(flag_id: int, payload: FlagDecision, user: AdminUser) -> dict:
    return await admin.resolve_flag(
        flag_id, UUID(str(user["id"])), payload.status, payload.resolution_note
    )


@router.post("/content/{content_id}/flags/resolve", response_model=BulkFlagResolutionResult)
async def resolve_content_flags(
    content_id: int, payload: BulkFlagResolution, user: AdminUser
) -> dict:
    return await admin.bulk_resolve_flags(
        content_id, UUID(str(user["id"])), payload.resolution_note
    )


@router.get("/content", response_model=AdminContentPage)
async def admin_content(
    content_type: ContentType | None = None,
    difficulty: Difficulty | None = None,
    category: str | None = None,
    q: str | None = Query(default=None, description="substring of target or translation text"),
    status: Literal["draft", "published", "hidden"] | None = None,
    verified: bool | None = None,
    audio_state: Literal["missing", "placeholder", "verified"] | None = None,
    has_flags: bool | None = None,
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
) -> dict:
    return await admin.list_content(
        content_type=content_type.value if content_type else None,
        difficulty=difficulty.value if difficulty else None,
        category=category,
        q=q,
        status=status,
        verified=verified,
        audio_state=audio_state,
        has_flags=has_flags,
        limit=min(limit, get_settings().max_page_size),
        offset=offset,
    )


@router.patch("/content/{content_id}", response_model=AdminContentState)
async def edit_content(content_id: int, payload: AdminContentPatch, user: AdminUser) -> dict:
    values = patch_values(payload)
    note = values.pop("change_note", None)
    return await admin.patch_content(content_id, UUID(str(user["id"])), values, note)


@router.patch(
    "/content/{content_id}/translations/{meta_language}",
    response_model=AdminTranslationState,
)
async def edit_translation(
    content_id: int, meta_language: str, payload: AdminTranslationPatch, user: AdminUser
) -> dict:
    values = patch_values(payload)
    note = values.pop("change_note", None)
    return await admin.patch_translation(
        content_id, meta_language, UUID(str(user["id"])), values, note
    )


@router.post(
    "/content/{content_id}/verify",
    response_model=AdminContentState | AdminTranslationState,
)
async def verify_content(content_id: int, payload: VerificationChange, user: AdminUser) -> dict:
    return await admin.set_verified(
        content_id, payload.meta_language, UUID(str(user["id"])), True, payload.change_note
    )


@router.post(
    "/content/{content_id}/unverify",
    response_model=AdminContentState | AdminTranslationState,
)
async def unverify_content(content_id: int, payload: VerificationChange, user: AdminUser) -> dict:
    return await admin.set_verified(
        content_id, payload.meta_language, UUID(str(user["id"])), False, payload.change_note
    )


@router.get("/content/{content_id}/revisions", response_model=list[AdminContentRevision])
async def content_revisions(content_id: int) -> list[dict]:
    return await admin.list_revisions(content_id)


@router.get("/contributors")
async def contributors() -> list[dict]:
    return await admin.list_contributors()


@router.post("/contributors", status_code=status.HTTP_201_CREATED)
async def grant_contributor(payload: ContributorGrant, user: AdminUser) -> dict:
    return await admin.grant_contributor(
        payload.user_id, payload.language, payload.can_verify, UUID(str(user["id"]))
    )


@router.delete("/contributors/{user_id}/{language}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_contributor(user_id: UUID, language: str) -> Response:
    await admin.revoke_contributor(user_id, language)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/users")
async def users(q: str = Query(default="", max_length=200)) -> list[dict]:
    return await admin.search_users(q.strip())
