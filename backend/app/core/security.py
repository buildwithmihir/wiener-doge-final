"""Session tokens (JWT, HS256).

The token proves WHO the user is (sub = users.id) and nothing else. Roles and
account status are always re-read from the database on every request, so a
stolen or stale token can never grant admin rights.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from app.config import get_settings
from app.core.errors import Unauthorized

ALGORITHM = "HS256"
ISSUER = "wienerdoge"
AUDIENCE = "wienerdoge-miniapp"
CLOCK_SKEW_SECONDS = 10


def create_access_token(
    user_id: uuid.UUID | str,
    expires_minutes: int | None = None,
) -> tuple[str, datetime]:
    """Return (token, expiry time in UTC)."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=expires_minutes or settings.jwt_expire_minutes)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "iat": now,
        "nbf": now,
        "exp": expires_at,
        "iss": ISSUER,
        "aud": AUDIENCE,
        "jti": uuid.uuid4().hex,
        "typ": "access",
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)
    return token, expires_at


def decode_access_token(token: str) -> dict[str, Any]:
    """Validate a token and return its claims, or raise Unauthorized."""
    settings = get_settings()
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[ALGORITHM],  # pinned: never accept 'none' or other algs
            audience=AUDIENCE,
            issuer=ISSUER,
            leeway=CLOCK_SKEW_SECONDS,
            options={"require": ["exp", "iat", "sub", "iss", "aud"]},
        )
    except jwt.ExpiredSignatureError:
        raise Unauthorized("Session expired. Please reopen the app.", "token_expired") from None
    except jwt.InvalidTokenError:
        raise Unauthorized("Invalid session.", "invalid_token") from None

    if claims.get("typ") != "access":
        raise Unauthorized("Invalid session.", "invalid_token")
    try:
        uuid.UUID(str(claims["sub"]))
    except ValueError:
        raise Unauthorized("Invalid session.", "invalid_token") from None
    return claims
