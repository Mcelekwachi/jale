from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response

from app.auth import current_account
from app.children_schemas import Child, ChildCreate, PinBody, PinResult
from app.schemas import UserProfile
from app.services import children
from app.services.users import get_user_profile

# Everything here acts on the signed-in person's own account and ignores any
# selected child profile. Keeping a child out of this area on a shared device is
# the job of the parent PIN in the app; children have no login of their own.
router = APIRouter(prefix="/v1/me", tags=["family"])

Account = Annotated[dict, Depends(current_account)]


@router.post("/age", response_model=UserProfile)
async def confirm_age(account: Account) -> dict:
    """The person confirmed they are 16 or older."""
    await children.confirm_age(account["id"])
    return await get_user_profile(UUID(str(account["id"])))


@router.get("/children", response_model=list[Child])
async def list_children(account: Account) -> list[dict]:
    return await children.list_children(account["id"])


@router.post("/children", response_model=Child, status_code=201)
async def add_child(payload: ChildCreate, account: Account) -> dict:
    if not payload.consent:
        raise HTTPException(status_code=422, detail="Parental consent is required")
    if account["age_confirmed_at"] is None:
        raise HTTPException(status_code=403, detail="Confirm you are 16 or older first")
    child = await children.create_child(account["id"], payload.nickname, payload.birth_year)
    if child is None:
        raise HTTPException(status_code=409, detail="Child profile limit reached")
    return child


@router.delete("/children/{child_id}", status_code=204)
async def remove_child(child_id: UUID, account: Account) -> Response:
    if not await children.delete_child(account["id"], child_id):
        raise HTTPException(status_code=404, detail="Profile not found")
    return Response(status_code=204)


@router.get("/children/{child_id}/export")
async def export_child(child_id: UUID, account: Account) -> dict:
    data = await children.export_child(account["id"], child_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return data


@router.get("/export")
async def export_me(account: Account) -> dict:
    return await children.export_user(account["id"], include_children=True)


@router.delete("", status_code=204)
async def delete_me(account: Account, confirm: bool = False) -> Response:
    if not confirm:
        raise HTTPException(status_code=422, detail="Pass confirm=true to delete the account")
    if not await children.delete_account(account["id"]):
        raise HTTPException(
            status_code=409,
            detail="This account has payment records that must be kept. Contact support.",
        )
    return Response(status_code=204)


@router.put("/pin", status_code=204)
async def set_pin(payload: PinBody, account: Account) -> Response:
    await children.set_pin(account["id"], payload.pin)
    return Response(status_code=204)


@router.post("/pin/verify", response_model=PinResult)
async def verify_pin(payload: PinBody, account: Account) -> dict:
    return {"valid": await children.verify_pin(account["id"], payload.pin)}
