"""Contact management API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.appointment import Appointment
from app.models.call import Call
from app.models.contact import Contact
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
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    # Recent calls
    calls_result = await db.execute(
        select(Call)
        .where(Call.contact_id == contact_id)
        .order_by(Call.started_at.desc())
        .limit(10)
    )
    recent_calls = calls_result.scalars().all()

    # Upcoming appointments
    from datetime import datetime

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
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(contact, field, value)

    return {"contact": ContactResponse.model_validate(contact)}
