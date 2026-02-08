"""Appointment booking engine: availability checking, booking, and cancellation."""

import json
import logging
from datetime import date, datetime, time, timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment, TimeSlot
from app.models.contact import Contact
from app.models.department import Department

logger = logging.getLogger(__name__)


async def get_available_slots(
    db: AsyncSession,
    department_id: int,
    target_date: date,
) -> list[dict]:
    """Return available appointment time slots for a department on a given date."""
    day_of_week = target_date.weekday()  # 0=Monday

    # Get the department's time slot configuration for this day
    result = await db.execute(
        select(TimeSlot).where(
            TimeSlot.department_id == department_id,
            TimeSlot.day_of_week == day_of_week,
            TimeSlot.is_active.is_(True),
        )
    )
    time_slot_configs = result.scalars().all()

    if not time_slot_configs:
        return []

    # Get existing appointments for this department on this date
    day_start = datetime.combine(target_date, time.min)
    day_end = datetime.combine(target_date, time.max)

    result = await db.execute(
        select(Appointment).where(
            Appointment.department_id == department_id,
            Appointment.scheduled_start >= day_start,
            Appointment.scheduled_start <= day_end,
            Appointment.status.in_(["confirmed", "completed"]),
        )
    )
    existing_appointments = result.scalars().all()

    # Generate individual slots and check availability
    available = []
    for config in time_slot_configs:
        current = datetime.combine(target_date, config.start_time)
        end = datetime.combine(target_date, config.end_time)
        duration = timedelta(minutes=config.slot_duration_minutes)

        while current + duration <= end:
            slot_end = current + duration
            # Count overlapping appointments
            overlapping = sum(
                1
                for appt in existing_appointments
                if appt.scheduled_start < slot_end and appt.scheduled_end > current
            )

            if overlapping < config.max_concurrent:
                available.append(
                    {
                        "start": current.isoformat(),
                        "end": slot_end.isoformat(),
                    }
                )
            current = slot_end

    return available


async def book_appointment(
    db: AsyncSession,
    contact_id: int,
    department_id: int,
    scheduled_start: datetime,
    scheduled_end: datetime,
    title: str,
    description: str | None = None,
    language: str = "en",
    call_id: int | None = None,
) -> Appointment:
    """Book an appointment. Returns the created Appointment."""
    appointment = Appointment(
        contact_id=contact_id,
        department_id=department_id,
        call_id=call_id,
        title=title,
        description=description,
        status="confirmed",
        scheduled_start=scheduled_start,
        scheduled_end=scheduled_end,
        language=language,
    )
    db.add(appointment)
    await db.flush()
    await db.refresh(appointment)
    return appointment


async def cancel_appointment(
    db: AsyncSession,
    appointment_id: int,
    reason: str | None = None,
) -> Appointment | None:
    """Cancel an appointment by ID. Returns the updated appointment or None."""
    result = await db.execute(
        select(Appointment).where(Appointment.id == appointment_id)
    )
    appointment = result.scalar_one_or_none()
    if not appointment:
        return None

    appointment.status = "cancelled"
    if reason:
        appointment.description = (appointment.description or "") + f"\nCancelled: {reason}"
    await db.flush()
    return appointment


async def lookup_appointments_by_phone(
    db: AsyncSession,
    phone_number: str,
) -> list[Appointment]:
    """Look up upcoming appointments for a phone number."""
    result = await db.execute(
        select(Contact).where(Contact.phone_number == phone_number)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        return []

    result = await db.execute(
        select(Appointment)
        .where(
            Appointment.contact_id == contact.id,
            Appointment.status == "confirmed",
            Appointment.scheduled_start >= datetime.utcnow(),
        )
        .order_by(Appointment.scheduled_start)
    )
    return list(result.scalars().all())


async def get_or_create_contact(
    db: AsyncSession,
    phone_number: str,
    name: str | None = None,
    language: str = "en",
) -> Contact:
    """Get an existing contact by phone number or create a new one."""
    result = await db.execute(
        select(Contact).where(Contact.phone_number == phone_number)
    )
    contact = result.scalar_one_or_none()

    if contact:
        if name and not contact.name:
            contact.name = name
        if language != "en":
            contact.preferred_language = language
        return contact

    contact = Contact(
        phone_number=phone_number,
        name=name,
        preferred_language=language,
    )
    db.add(contact)
    await db.flush()
    await db.refresh(contact)
    return contact
