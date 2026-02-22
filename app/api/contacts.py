"""Contact management API endpoints — CRUD + history + merge + tags."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.appointment import Appointment
from app.models.call import Call
from app.models.contact import Contact
from app.models.message import SMSMessage
from app.schemas.contact import ContactCreate, ContactResponse, ContactUpdate

router = APIRouter(prefix="/api/contacts", tags=["contacts"])


@router.get("")
async def list_contacts(
    db: AsyncSession = Depends(get_db),
    search: str | None = None,
    language: str | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    query = select(Contact).order_by(Contact.created_at.desc())

    if search:
        query = query.where(
            or_(
                Contact.name.ilike(f"%{search}%"),
                Contact.phone_number.ilike(f"%{search}%"),
                Contact.email.ilike(f"%{search}%"),
            )
        )
    if language:
        query = query.where(Contact.preferred_language == language)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    contacts = result.scalars().all()

    return {
        "contacts": [ContactResponse.model_validate(c) for c in contacts],
        "total": total,
        "page": page,
    }


@router.post("", status_code=201)
async def create_contact(
    data: ContactCreate,
    db: AsyncSession = Depends(get_db),
):
    contact = Contact(**data.model_dump())
    db.add(contact)
    await db.flush()
    await db.refresh(contact)
    return {"contact": ContactResponse.model_validate(contact)}


@router.get("/{contact_id}")
async def get_contact(
    contact_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Contact).where(Contact.id == contact_id))
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    # Recent calls
    calls_result = await db.execute(
        select(Call).where(Call.contact_id == contact_id).order_by(Call.started_at.desc()).limit(10)
    )
    recent_calls = calls_result.scalars().all()

    # Upcoming appointments

    appts_result = await db.execute(
        select(Appointment)
        .where(
            Appointment.contact_id == contact_id,
            Appointment.scheduled_start >= datetime.utcnow(),
            Appointment.status == "confirmed",
        )
        .order_by(Appointment.scheduled_start)
        .limit(5)
    )
    appointments = appts_result.scalars().all()

    return {
        "contact": ContactResponse.model_validate(contact),
        "recent_calls": [
            {"id": c.id, "status": c.status, "started_at": c.started_at.isoformat()}
            for c in recent_calls
        ],
        "appointments": [
            {
                "id": a.id,
                "title": a.title,
                "scheduled_start": a.scheduled_start.isoformat(),
                "status": a.status,
            }
            for a in appointments
        ],
    }


@router.patch("/{contact_id}")
async def update_contact(
    contact_id: int,
    data: ContactUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Contact).where(Contact.id == contact_id))
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(contact, field, value)

    return {"contact": ContactResponse.model_validate(contact)}


@router.get("/{contact_id}/history", summary="Full history for a contact")
async def get_contact_history(
    contact_id: int,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    """Return all calls, appointments, and SMS messages for a contact, most recent first."""
    contact = (
        await db.execute(select(Contact).where(Contact.id == contact_id))
    ).scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    # All calls
    calls = (
        (
            await db.execute(
                select(Call).where(Call.contact_id == contact_id).order_by(Call.started_at.desc())
            )
        )
        .scalars()
        .all()
    )

    # All appointments
    appts = (
        (
            await db.execute(
                select(Appointment)
                .where(Appointment.contact_id == contact_id)
                .order_by(Appointment.scheduled_start.desc())
            )
        )
        .scalars()
        .all()
    )

    # All SMS messages
    messages = (
        (
            await db.execute(
                select(SMSMessage)
                .where(SMSMessage.contact_id == contact_id)
                .order_by(SMSMessage.created_at.desc())
            )
        )
        .scalars()
        .all()
    )

    # Unified timeline
    events = []
    for c in calls:
        events.append(
            {
                "type": "call",
                "id": c.id,
                "timestamp": c.started_at.isoformat(),
                "status": c.status,
                "direction": c.direction,
                "language": c.detected_language,
                "duration_seconds": c.duration_seconds,
                "resolution": c.resolution_status,
            }
        )
    for a in appts:
        events.append(
            {
                "type": "appointment",
                "id": a.id,
                "timestamp": a.scheduled_start.isoformat(),
                "status": a.status,
                "title": a.title,
                "department_id": a.department_id,
            }
        )
    for m in messages:
        events.append(
            {
                "type": "sms",
                "id": m.id,
                "timestamp": m.created_at.isoformat(),
                "direction": m.direction,
                "body": m.body,
            }
        )

    events.sort(key=lambda e: e["timestamp"], reverse=True)
    total = len(events)
    start = (page - 1) * per_page
    paged = events[start : start + per_page]

    return {
        "contact": ContactResponse.model_validate(contact),
        "total_events": total,
        "page": page,
        "per_page": per_page,
        "events": paged,
    }


class ContactMergeRequest(BaseModel):
    primary_contact_id: int
    duplicate_contact_id: int


@router.post("/merge", summary="Merge duplicate contacts")
async def merge_contacts(
    data: ContactMergeRequest,
    db: AsyncSession = Depends(get_db),
):
    """Merge a duplicate contact into the primary contact.

    All calls, appointments, and SMS messages are re-assigned to the primary contact.
    The duplicate contact is then deactivated (notes appended).
    """
    primary = (
        await db.execute(select(Contact).where(Contact.id == data.primary_contact_id))
    ).scalar_one_or_none()
    duplicate = (
        await db.execute(select(Contact).where(Contact.id == data.duplicate_contact_id))
    ).scalar_one_or_none()

    if not primary:
        raise HTTPException(status_code=404, detail="Primary contact not found")
    if not duplicate:
        raise HTTPException(status_code=404, detail="Duplicate contact not found")
    if primary.id == duplicate.id:
        raise HTTPException(status_code=400, detail="Cannot merge a contact with itself")

    # Re-assign relationships using sqlalchemy update
    from sqlalchemy import update as sa_update

    await db.execute(
        sa_update(Call).where(Call.contact_id == duplicate.id).values(contact_id=primary.id)
    )
    await db.execute(
        sa_update(Appointment)
        .where(Appointment.contact_id == duplicate.id)
        .values(contact_id=primary.id)
    )
    await db.execute(
        sa_update(SMSMessage)
        .where(SMSMessage.contact_id == duplicate.id)
        .values(contact_id=primary.id)
    )

    # Merge notes
    if duplicate.notes:
        primary.notes = (
            primary.notes or ""
        ) + f"\n[Merged from {duplicate.phone_number}]: {duplicate.notes}"

    # Prefer the more complete name/email
    if not primary.name and duplicate.name:
        primary.name = duplicate.name
    if not primary.email and duplicate.email:
        primary.email = duplicate.email

    # Mark duplicate as deleted (set phone to a placeholder)
    duplicate.notes = f"[MERGED INTO {primary.phone_number}]"
    duplicate.phone_number = f"MERGED-{duplicate.phone_number}"

    await db.flush()
    return {
        "merged": True,
        "primary_contact": ContactResponse.model_validate(primary),
        "duplicate_contact_id": data.duplicate_contact_id,
    }


class ContactTagRequest(BaseModel):
    tags: list[str]


@router.post("/{contact_id}/tags", summary="Set tags on a contact")
async def set_contact_tags(
    contact_id: int,
    data: ContactTagRequest,
    db: AsyncSession = Depends(get_db),
):
    """Set/replace the tags on a contact. Tags are stored in the notes field as JSON metadata."""
    contact = (
        await db.execute(select(Contact).where(Contact.id == contact_id))
    ).scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    # Store tags in notes as a structured prefix (simple approach without schema change)
    import json as _json

    existing_notes = contact.notes or ""
    # Strip any existing tag block
    if existing_notes.startswith("__TAGS__:"):
        lines = existing_notes.split("\n", 1)
        existing_notes = lines[1] if len(lines) > 1 else ""

    tag_line = "__TAGS__:" + _json.dumps(sorted(set(data.tags)))
    contact.notes = tag_line + ("\n" + existing_notes if existing_notes else "")

    return {"contact_id": contact_id, "tags": data.tags}


@router.get("/{contact_id}/tags", summary="Get tags for a contact")
async def get_contact_tags(
    contact_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Return the tags set on a contact."""
    import json as _json

    contact = (
        await db.execute(select(Contact).where(Contact.id == contact_id))
    ).scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    tags: list[str] = []
    if contact.notes and contact.notes.startswith("__TAGS__:"):
        first_line = contact.notes.split("\n", 1)[0]
        try:
            tags = _json.loads(first_line[len("__TAGS__:") :])
        except Exception:
            tags = []

    return {"contact_id": contact_id, "tags": tags}
