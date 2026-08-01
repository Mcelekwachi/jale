from __future__ import annotations

from fastapi import APIRouter

from app.schemas import PublicProfile
from app.services.profiles import get_public_profile

router = APIRouter(prefix="/v1/profile", tags=["profiles"])


@router.get("/{share_slug}", response_model=PublicProfile)
async def read_public_profile(share_slug: str) -> dict:
    return await get_public_profile(share_slug)
