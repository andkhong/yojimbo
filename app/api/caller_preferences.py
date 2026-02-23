"""Caller Preferences API — persistent per-phone preferences for returning callers."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.caller_preference import CallerPreference

router = APIRouter(prefix="/api/preferences", tags=["caller-preferences"])


def _localized_error(message_key: str, fallback: str, **params):
    """Build i18n-ready error payloads with a stable message key + params."""
    return {
        "message_key": message_key,
        "message": fallback,
        "params": params,
    }


class CallerPreferenceResponse(BaseModel):
    id: int
    phone_number: str
    preferred_language: str
    name: str | None = None
    preferred_department_id: int | None = None
    hearing_impaired: bool
    speech_impaired: bool
    requires_interpreter: bool
    sms_opt_in: bool
    email_opt_in: bool
    preferred_reminder_hours: int
    notes: str | None = None
    call_count: int

    model_config = {"from_attributes": True}


class CallerPreferenceUpsert(BaseModel):
    preferred_language: str = "en"
    name: str | None = None
    preferred_department_id: int | None = None
    hearing_impaired: bool = False
    speech_impaired: bool = False
    requires_interpreter: bool = False
    sms_opt_in: bool = True
    email_opt_in: bool = False
    preferred_reminder_hours: int = 24
    notes: str | None = None


@router.get("/{phone_number:path}", summary="Get preferences for a caller by phone number")
async def get_preferences(phone_number: str, db: AsyncSession = Depends(get_db)):
    """Return stored preferences for a phone number, or 404 if none set."""
    pref = (await db.execute(
        select(CallerPreference).where(CallerPreference.phone_number == phone_number)
    )).scalar_one_or_none()
    if not pref:
        raise HTTPException(
            status_code=404,
            detail=_localized_error(
                "preferences.not_found",
                f"No preferences found for {phone_number}",
                phone_number=phone_number,
            ),
        )
    return {"preference": CallerPreferenceResponse.model_validate(pref)}


@router.put("/{phone_number:path}", summary="Upsert caller preferences")
async def upsert_preferences(
    phone_number: str,
    data: CallerPreferenceUpsert,
    db: AsyncSession = Depends(get_db),
):
    """Create or update preferences for a phone number."""
    pref = (await db.execute(
        select(CallerPreference).where(CallerPreference.phone_number == phone_number)
    )).scalar_one_or_none()

    if pref:
        for field, value in data.model_dump().items():
            setattr(pref, field, value)
    else:
        pref = CallerPreference(phone_number=phone_number, **data.model_dump())
        db.add(pref)

    await db.flush()
    await db.refresh(pref)
    return {"preference": CallerPreferenceResponse.model_validate(pref)}


@router.delete("/{phone_number:path}", status_code=204, summary="Delete caller preferences")
async def delete_preferences(phone_number: str, db: AsyncSession = Depends(get_db)):
    """Remove all stored preferences for a phone number."""
    pref = (await db.execute(
        select(CallerPreference).where(CallerPreference.phone_number == phone_number)
    )).scalar_one_or_none()
    if not pref:
        raise HTTPException(
            status_code=404,
            detail=_localized_error(
                "preferences.not_found",
                f"No preferences found for {phone_number}",
                phone_number=phone_number,
            ),
        )
    await db.delete(pref)
    return None


@router.post("/{phone_number:path}/increment-call", summary="Record a new call for this caller")
async def increment_call_count(phone_number: str, db: AsyncSession = Depends(get_db)):
    """Increment call count and update last_call_at. Creates preference record if needed."""
    from datetime import datetime

    pref = (await db.execute(
        select(CallerPreference).where(CallerPreference.phone_number == phone_number)
    )).scalar_one_or_none()

    if not pref:
        pref = CallerPreference(phone_number=phone_number)
        db.add(pref)

    pref.call_count = (pref.call_count or 0) + 1
    pref.last_call_at = datetime.utcnow()
    await db.flush()

    return {
        "phone_number": phone_number,
        "call_count": pref.call_count,
        "last_call_at": pref.last_call_at.isoformat(),
    }
