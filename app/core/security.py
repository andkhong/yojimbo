import logging
from datetime import datetime

import bcrypt
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import DashboardUser

logger = logging.getLogger(__name__)


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
