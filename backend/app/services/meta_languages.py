from __future__ import annotations

from fastapi import HTTPException

from app.db import fetch_one


async def validate_meta_language_id(language_id: int) -> int:
    """Return an id only when it identifies a configured meta language."""
    language = await fetch_one(
        "SELECT id FROM languages WHERE id = %(language_id)s AND is_meta",
        {"language_id": language_id},
    )
    if language is None:
        raise HTTPException(status_code=422, detail="invalid meta language id")
    return language["id"]


async def resolve_meta_language_id(code: str) -> int:
    """Resolve a configured meta-language code for write endpoints."""
    language = await fetch_one(
        "SELECT id FROM languages WHERE code = %(code)s AND is_meta",
        {"code": code},
    )
    if language is None:
        raise HTTPException(status_code=422, detail=f"invalid meta language {code!r}")
    return language["id"]


async def resolve_available_meta_language_id(code: str) -> int:
    """Resolve an active meta-language code for preference writes."""
    language = await fetch_one(
        "SELECT id, name, is_active FROM languages WHERE code = %(code)s AND is_meta",
        {"code": code},
    )
    if language is None:
        raise HTTPException(status_code=422, detail=f"invalid meta language {code!r}")
    if not language["is_active"]:
        raise HTTPException(
            status_code=422, detail=f"{language['name']} ({code}) is not yet available"
        )
    return language["id"]


async def validate_meta_language(code: str) -> str:
    """Return *code* when it names a configured meta language."""
    language = await fetch_one(
        "SELECT code FROM languages WHERE code = %(code)s AND is_meta",
        {"code": code},
    )
    if language is None:
        raise HTTPException(status_code=400, detail=f"invalid meta language {code!r}")
    return language["code"]


async def resolve_meta_languages(requested: str | None, default: str) -> tuple[str, str]:
    """Validate the configured default and requested meta-language codes."""
    validated_default = await validate_meta_language(default)
    if requested is None or requested == validated_default:
        return validated_default, validated_default
    return await validate_meta_language(requested), validated_default
