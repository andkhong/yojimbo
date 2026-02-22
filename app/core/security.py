import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import DashboardUser

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

_ALGORITHM = "HS256"
_ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 8  # 8-hour tokens for staff dashboards
_REFRESH_TOKEN_EXPIRE_DAYS = 30

_bearer = HTTPBearer(auto_error=False)


def create_access_token(
    subject: int | str,
    role: str = "operator",
    expires_minutes: int = _ACCESS_TOKEN_EXPIRE_MINUTES,
    extra: dict[str, Any] | None = None,
) -> str:
    """Create a signed JWT access token."""
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes),
        "type": "access",
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=_ALGORITHM)


def create_refresh_token(subject: int | str) -> str:
    """Create a longer-lived refresh token."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(subject),
        "iat": now,
        "exp": now + timedelta(days=_REFRESH_TOKEN_EXPIRE_DAYS),
        "type": "refresh",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """Decode and verify a JWT token. Raises HTTPException on failure."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[_ALGORITHM])
        return payload
    except JWTError as exc:
        raise HTTPException(
            status_code=401,
            detail=f"Invalid or expired token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user_from_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> DashboardUser | None:
    """Dependency: extract user from Bearer token (returns None if no token)."""
    if credentials is None:
        return None
    payload = decode_token(credentials.credentials)
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Not an access token")
    user_id = int(payload["sub"])
    user = (await db.execute(
        select(DashboardUser).where(
            DashboardUser.id == user_id,
            DashboardUser.is_active.is_(True),
        )
    )).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


async def require_auth(
    session_user: DashboardUser | None = Depends(get_current_user_from_token),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
) -> DashboardUser:
    """Dependency: require authentication via Bearer token OR session cookie.

    Checks JWT Bearer first, then falls back to session cookie.
    Raises 401 if neither is present/valid.
    """
    if session_user is not None:
        return session_user

    # Fallback: session cookie
    if request is not None:
        user_id = request.session.get("user_id")
        if user_id:
            user = (await db.execute(
                select(DashboardUser).where(
                    DashboardUser.id == user_id,
                    DashboardUser.is_active.is_(True),
                )
            )).scalar_one_or_none()
            if user:
                return user

    raise HTTPException(
        status_code=401,
        detail="Authentication required. Provide a Bearer token or session cookie.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def validate_twilio_request(request: Request) -> bool:
    """Validate that a request came from Twilio.

    In production, this should use twilio.request_validator.RequestValidator.
    For the MVP, we check if the account SID matches.
    """
    if settings.debug:
        return True

    try:
        from twilio.request_validator import RequestValidator

        validator = RequestValidator(settings.twilio_auth_token)
        url = str(request.url)
        signature = request.headers.get("X-Twilio-Signature", "")
        return validator.validate(url, {}, signature)
    except Exception:
        logger.warning("Twilio request validation failed")
        return False


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> DashboardUser:
    """Get the current authenticated user from the session cookie."""
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    result = await db.execute(
        select(DashboardUser).where(DashboardUser.id == user_id, DashboardUser.is_active.is_(True))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user


async def authenticate_user(db: AsyncSession, username: str, password: str) -> DashboardUser | None:
    result = await db.execute(
        select(DashboardUser).where(
            DashboardUser.username == username, DashboardUser.is_active.is_(True)
        )
    )
    user = result.scalar_one_or_none()
    if user and verify_password(password, user.password_hash):
        user.last_login = datetime.utcnow()
        return user
    return None
