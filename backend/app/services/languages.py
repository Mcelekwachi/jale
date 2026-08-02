from __future__ import annotations

from fastapi import HTTPException

from app.db import fetch_one


async def resolve_learnable_language_id(code: str) -> int:
    """Resolve a learnable language code for preference writes."""
    language = await fetch_one(
        "SELECT id FROM languages WHERE code = %(code)s AND is_learnable",
        {"code": code},
    )
    if language is None:
        raise HTTPException(status_code=422, detail=f"invalid learnable language {code!r}")
    return language["id"]
