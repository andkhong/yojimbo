"""Appointment booking engine: availability checking, booking, and cancellation."""

import json
import logging
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment, TimeSlot
from app.models.contact import Contact

logger = logging.getLogger(__name__)


class BookingConflictError(Exception):
    """Raised when a time slot is already at capacity."""


class OutsideOperatingHoursError(Exception):
    """Raised when appointment time is outside department operating hours.

    Provides i18n-ready metadata while still rendering a human-readable message.
    """

    def __init__(self, message_key: str, message: str, **params):
        super().__init__(message)
        self.message_key = message_key
        self.params = params


# Day index → key used in operating_hours JSON
_DAY_KEYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_SHORT_DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _parse_hhmm(value: str) -> time:
    hour, minute = map(int, value.split(":"))
    return time(hour, minute)


def _extract_day_hours(hours: dict, day_index: int) -> tuple[time, time] | None:
    """Return (open, close) for the given weekday index, if configured.

    Supports both formats:
    - {"monday": {"open": "09:00", "close": "17:00"}}
    - {"mon-fri": "9:00-16:00"}
    """
    day_key = _DAY_KEYS[day_index]
    short_key = _SHORT_DAY_KEYS[day_index]

    # Preferred structured format
    day_hours = hours.get(day_key)
    if isinstance(day_hours, dict):
        open_s = day_hours.get("open")
        close_s = day_hours.get("close")
        if isinstance(open_s, str) and isinstance(close_s, str):
            return _parse_hhmm(open_s), _parse_hhmm(close_s)

    # Alternate short key format, e.g. {"mon": {"open": ..., "close": ...}}
    day_hours = hours.get(short_key)
    if isinstance(day_hours, dict):
        open_s = day_hours.get("open")
        close_s = day_hours.get("close")
        if isinstance(open_s, str) and isinstance(close_s, str):
            return _parse_hhmm(open_s), _parse_hhmm(close_s)

    # Legacy range format, e.g. {"mon-fri": "9:00-16:00", "sat": "10:00-14:00"}
    for key, value in hours.items():
        if not isinstance(value, str) or "-" not in value:
            continue

        start_s, end_s = value.split("-", 1)
        try:
            open_time, close_time = _parse_hhmm(start_s), _parse_hhmm(end_s)
        except ValueError:
            continue

        normalized = key.strip().lower()
        if normalized in {day_key, short_key}:
            return open_time, close_time

        if "-" in normalized:
            left, right = [part.strip() for part in normalized.split("-", 1)]
            if left in _SHORT_DAY_KEYS and right in _SHORT_DAY_KEYS:
                left_i = _SHORT_DAY_KEYS.index(left)
                right_i = _SHORT_DAY_KEYS.index(right)
                if left_i <= day_index <= right_i:
                    return open_time, close_time

    return None


def _uses_structured_operating_hours(operating_hours_json: str | None) -> bool:
    """Return True when hours use explicit per-day object format.

    Structured example: {"monday": {"open": "09:00", "close": "17:00"}}
    """
    if not operating_hours_json:
        return False
    try:
        hours = json.loads(operating_hours_json)
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(hours, dict):
        return False
    return any(isinstance(v, dict) and "open" in v and "close" in v for v in hours.values())


def check_operating_hours(
    operating_hours_json: str | None,
    scheduled_start: datetime,
    scheduled_end: datetime,
) -> None:
    """Validate that a time window falls within department operating hours.

    operating_hours_json format:
      {"monday": {"open": "09:00", "close": "17:00"}, ...}

    Raises OutsideOperatingHoursError with a human-readable message if the
    appointment is outside configured hours. Does nothing if no hours configured.
    """
    if not operating_hours_json:
        return  # No restriction — open always

    try:
        hours = json.loads(operating_hours_json)
    except (json.JSONDecodeError, TypeError):
        return  # Unparseable hours — don't block

    day_index = scheduled_start.weekday()
    window_day_index = day_index
    day_key = _DAY_KEYS[window_day_index]

    try:
        day_window = _extract_day_hours(hours, day_index)
    except (ValueError, TypeError, AttributeError):
        return  # Can't parse hours — allow booking

    open_dt: datetime | None = None
    close_dt: datetime | None = None

    # If current day has no schedule, allow early-morning spillover from
    # previous day's overnight window (e.g. Mon 22:00-02:00 for Tue 01:00).
    if not day_window:
        prev_day_index = (day_index - 1) % 7
        prev_day_window = _extract_day_hours(hours, prev_day_index)
        if prev_day_window:
            prev_open_time, prev_close_time = prev_day_window
            if prev_close_time <= prev_open_time:
                candidate_open_dt = datetime.combine(
                    scheduled_start.date() - timedelta(days=1),
                    prev_open_time,
                )
                candidate_close_dt = datetime.combine(scheduled_start.date(), prev_close_time)
                if candidate_open_dt <= scheduled_start <= candidate_close_dt:
                    day_window = prev_day_window
                    window_day_index = prev_day_index
                    day_key = _DAY_KEYS[window_day_index]
                    open_dt = candidate_open_dt
                    close_dt = candidate_close_dt

    if not day_window:
        raise OutsideOperatingHoursError(
            "appointments.operating_hours.closed_day",
            f"The department is closed on {day_key.capitalize()}.",
            day=day_key,
        )

    open_time, close_time = day_window
    if open_dt is None or close_dt is None:
        open_dt = datetime.combine(scheduled_start.date(), open_time)
        close_dt = datetime.combine(scheduled_start.date(), close_time)

        # Support overnight windows, e.g. 22:00 -> 02:00 next day
        if close_time <= open_time:
            close_dt += timedelta(days=1)

    if scheduled_start < open_dt:
        raise OutsideOperatingHoursError(
            "appointments.operating_hours.before_open",
            f"Appointment starts at {scheduled_start.strftime('%H:%M')} but the department "
            f"opens at {open_time.strftime('%H:%M')} on {day_key.capitalize()}.",
            day=day_key,
            opens_at=open_time.strftime("%H:%M"),
            starts_at=scheduled_start.strftime("%H:%M"),
        )
    if scheduled_end > close_dt:
        raise OutsideOperatingHoursError(
            "appointments.operating_hours.after_close",
            f"Appointment ends at {scheduled_end.strftime('%H:%M')} but the department "
            f"closes at {close_time.strftime('%H:%M')} on {day_key.capitalize()}.",
            day=day_key,
            closes_at=close_time.strftime("%H:%M"),
            ends_at=scheduled_end.strftime("%H:%M"),
        )


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
    skip_conflict_check: bool = False,
    enforce_operating_hours: bool = False,
) -> Appointment:
    """Book an appointment. Returns the created Appointment.

    Raises:
      BookingConflictError: if the time slot is already at capacity.
      OutsideOperatingHoursError: if appointment is outside dept operating hours.
    """
    if enforce_operating_hours:
        from app.models.department import Department

        dept = (
            await db.execute(select(Department).where(Department.id == department_id))
        ).scalar_one_or_none()
        if dept and _uses_structured_operating_hours(dept.operating_hours):
            check_operating_hours(dept.operating_hours, scheduled_start, scheduled_end)

    if not skip_conflict_check:
        await _check_booking_capacity(db, department_id, scheduled_start, scheduled_end)

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


async def _check_booking_capacity(
    db: AsyncSession,
    department_id: int,
    scheduled_start: datetime,
    scheduled_end: datetime,
) -> None:
    """Verify the slot has capacity. Raises BookingConflictError if full.

    Finds the TimeSlot configuration covering this window and checks whether
    existing confirmed/pending appointments have exhausted max_concurrent.
    """
    day_of_week = scheduled_start.weekday()

    # Find the TimeSlot config for this department/day that covers the window
    result = await db.execute(
        select(TimeSlot).where(
            TimeSlot.department_id == department_id,
            TimeSlot.day_of_week == day_of_week,
            TimeSlot.is_active.is_(True),
        )
    )
    slot_configs = result.scalars().all()

    # Determine the applicable max_concurrent (use the first matching config)
    max_concurrent = 1
    for config in slot_configs:
        config_start = datetime.combine(scheduled_start.date(), config.start_time)
        config_end = datetime.combine(scheduled_start.date(), config.end_time)
        if config_start <= scheduled_start and scheduled_end <= config_end:
            max_concurrent = config.max_concurrent
            break

    # Count existing overlapping confirmed/pending appointments
    overlapping_count = (
        await db.execute(
            select(func.count()).where(
                Appointment.department_id == department_id,
                Appointment.status.in_(["confirmed", "pending"]),
                Appointment.scheduled_start < scheduled_end,
                Appointment.scheduled_end > scheduled_start,
            )
        )
    ).scalar() or 0

    if overlapping_count >= max_concurrent:
        raise BookingConflictError(
            f"Time slot {scheduled_start.isoformat()} is fully booked "
            f"({overlapping_count}/{max_concurrent} slots taken)."
        )


async def cancel_appointment(
    db: AsyncSession,
    appointment_id: int,
    reason: str | None = None,
) -> Appointment | None:
    """Cancel an appointment by ID. Returns the updated appointment or None."""
    result = await db.execute(select(Appointment).where(Appointment.id == appointment_id))
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
    result = await db.execute(select(Contact).where(Contact.phone_number == phone_number))
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
    result = await db.execute(select(Contact).where(Contact.phone_number == phone_number))
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
