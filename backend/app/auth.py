from __future__ import annotations

import uuid
from functools import lru_cache
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings
from app.services.children import get_child_for_parent
from app.services.users import provision_user

_bearer = HTTPBearer(auto_error=False)
_AUTH_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid authentication credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


@lru_cache
def _jwks_client(jwks_url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(jwks_url, cache_keys=True, cache_jwk_set=True)


def _decode(credentials: HTTPAuthorizationCredentials | None) -> dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _AUTH_ERROR
    settings = get_settings()
    try:
        token = credentials.credentials
        header = jwt.get_unverified_header(token)
        algorithm = header.get("alg")
        if algorithm == "HS256":
            if not settings.supabase_jwt_secret:
                raise jwt.InvalidKeyError("HS256 secret is not configured")
            verification_key: Any = settings.supabase_jwt_secret
        elif algorithm in {"ES256", "RS256"}:
            if not isinstance(header.get("kid"), str):
                raise jwt.InvalidTokenError("asymmetric token has no key id")
            jwks_url = f"{settings.supabase_project_url}/auth/v1/.well-known/jwks.json"
            signing_key = _jwks_client(jwks_url).get_signing_key_from_jwt(token)
            if signing_key.algorithm_name != algorithm:
                raise jwt.InvalidAlgorithmError("token and signing key algorithms differ")
            verification_key = signing_key.key
        else:
            raise jwt.InvalidAlgorithmError("unsupported token algorithm")

        claims = jwt.decode(
            token,
            verification_key,
            algorithms=[algorithm],
            audience=settings.supabase_jwt_audience,
            options={"require": ["exp", "sub", "aud"]},
        )
        uuid.UUID(str(claims["sub"]))
    except Exception:  # noqa: BLE001 — all authentication failures must be indistinguishable
        raise _AUTH_ERROR from None
    return claims


async def current_account(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> dict[str, Any]:
    """The signed-in person themselves, ignoring any selected child profile."""
    return await provision_user(_decode(credentials))


async def current_user(
    request: Request,
    account: Annotated[dict[str, Any], Depends(current_account)],
) -> dict[str, Any]:
    """The learner the request is for: the account, or one of its child profiles.

    A parent selects a child with the X-Profile-Id header. Only the parent's own
    children can be selected, so the header can never reach another account.
    """
    raw = request.headers.get("x-profile-id")
    if not raw:
        return account
    try:
        child_id = uuid.UUID(raw)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid profile id") from None
    child = await get_child_for_parent(account["id"], child_id)
    if child is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return child


async def optional_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> dict[str, Any] | None:
    if "authorization" not in request.headers:
        return None
    return await provision_user(_decode(credentials))


async def require_admin(
    user: Annotated[dict[str, Any], Depends(current_user)],
) -> dict[str, Any]:
    if user["role"] != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user
