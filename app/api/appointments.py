"""Appointment management API endpoints."""

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.appointment import Appointment
from app.schemas.appointment import (
    AppointmentCreate,
    AppointmentResponse,
    AppointmentUpdate,
    AvailabilityResponse,
    AvailabilitySlot,
)
from app.services import appointment_engine, notification
from app.services.appointment_engine import BookingConflictError

router = APIRouter(prefix="/api/appointments", tags=["appointments"])


@router.get("")
async def list_appointments(
    db: AsyncSession = Depends(get_db),
    department_id: int | None = None,
    target_date: str | None = None,
    status: str | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    query = select(Appointment).order_by(Appointment.scheduled_start)

    if department_id:
        query = query.where(Appointment.department_id == department_id)
    if status:
        query = query.where(Appointment.status == status)
    if target_date:
        d = date.fromisoformat(target_date)
        query = query.where(
            Appointment.scheduled_start >= datetime.combine(d, datetime.min.time()),
            Appointment.scheduled_start < datetime.combine(d, datetime.max.time()),
        )

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    appointments = result.scalars().all()

    return {
        "appointments": [AppointmentResponse.model_validate(a) for a in appointments],
        "total": total,
        "page": page,
    }


@router.post("", status_code=201)
async def create_appointment(
    data: AppointmentCreate,
    db: AsyncSession = Depends(get_db),
):
    try:
        appt = await appointment_engine.book_appointment(
            db,
            contact_id=data.contact_id,
            department_id=data.department_id,
            scheduled_start=data.scheduled_start,
            scheduled_end=data.scheduled_end,
            title=data.title,
            description=data.description,
            language=data.language,
        )
    except BookingConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    await notification.notify_appointment_created(
        {
            "appointment_id": appt.id,
            "department_id": appt.department_id,
            "scheduled_start": appt.scheduled_start.isoformat(),
        }
    )

    return {"appointment": AppointmentResponse.model_validate(appt)}


@router.get("/availability")
async def check_availability(
    department_id: int,
    target_date: str,
    db: AsyncSession = Depends(get_db),
):
    d = date.fromisoformat(target_date)
    slots = await appointment_engine.get_available_slots(db, department_id, d)

    return AvailabilityResponse(
        department_id=department_id,
        date=target_date,
        slots=[AvailabilitySlot(**s) for s in slots],
    )


@router.get("/{appointment_id}")
async def get_appointment(
    appointment_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Appointment).where(Appointment.id == appointment_id))
    appt = result.scalar_one_or_none()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return {"appointment": AppointmentResponse.model_validate(appt)}


@router.patch("/{appointment_id}")
async def update_appointment(
    appointment_id: int,
    data: AppointmentUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Appointment).where(Appointment.id == appointment_id))
    appt = result.scalar_one_or_none()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(appt, field, value)

    await notification.notify_appointment_updated(
        {
            "appointment_id": appt.id,
            "status": appt.status,
        }
    )

    return {"appointment": AppointmentResponse.model_validate(appt)}


@router.delete("/{appointment_id}")
async def cancel_appointment_endpoint(
    appointment_id: int,
    db: AsyncSession = Depends(get_db),
):
    appt = await appointment_engine.cancel_appointment(db, appointment_id)
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    await notification.notify_appointment_updated(
        {
            "appointment_id": appt.id,
            "status": "cancelled",
        }
    )

    return {"appointment": AppointmentResponse.model_validate(appt)}
