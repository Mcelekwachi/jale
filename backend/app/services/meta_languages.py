from __future__ import annotations

from fastapi import HTTPException

from app.db import fetch_one


async def validate_meta_language(code: str) -> str:
    """Return *code* when it names a configured meta language."""
    language = await fetch_one(
        "SELECT code FROM languages WHERE code = %(code)s AND is_meta",
        {"code": code},
    )
    if language is None:
        raise HTTPException(status_code=400, detail=f"invalid meta language {code!r}")
    return language["code"]
