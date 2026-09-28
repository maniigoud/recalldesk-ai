"""Password hashing and JWT helpers.

Uses bcrypt directly (actively maintained) instead of the deprecated passlib
wrapper, and PyJWT for token creation/validation.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import bcrypt
import jwt

from app.core.config import settings
from app.core.errors import AuthenticationError

TOKEN_TYPE = "access"


def hash_password(plain_password: str) -> str:
    payload = plain_password.encode("utf-8")
    if len(payload) > 72:
        raise ValueError("Password must be 72 bytes or fewer.")
    return bcrypt.hashpw(payload, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), password_hash.encode("utf-8")
        )
    except (ValueError, TypeError):
        return False


def create_access_token(
    *,
    subject: str,
    role: str,
    organization_id: int,
    expires_minutes: Optional[int] = None,
) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(
        minutes=expires_minutes or settings.access_token_expire_minutes
    )
    claims: Dict[str, Any] = {
        "sub": subject,
        "role": role,
        "organization_id": organization_id,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "type": TOKEN_TYPE,
        "iss": settings.app_name,
    }
    return jwt.encode(claims, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> Dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Access token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError("Access token is invalid.") from exc

    if payload.get("type") != TOKEN_TYPE:
        raise AuthenticationError("Access token is invalid.")
    return payload
