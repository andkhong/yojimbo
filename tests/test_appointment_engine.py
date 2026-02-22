"""Tests for the appointment booking engine."""

import pytest
from datetime import date, datetime, time, timedelta
from sqlalchemy import select

from app.models.appointment import TimeSlot
from app.models.department import Department
from app.services.appointment_engine import (
    BookingConflictError,
    book_appointment,
    cancel_appointment,
    get_available_slots,
    get_or_create_contact,
    lookup_appointments_by_phone,
)


@pytest.mark.asyncio
async def test_get_or_create_contact_creates_new(db):
    contact = await get_or_create_contact(db, "+15551112222", "Test User", "es")
    assert contact.id is not None
    assert contact.phone_number == "+15551112222"
    assert contact.name == "Test User"
    assert contact.preferred_language == "es"


@pytest.mark.asyncio
async def test_get_or_create_contact_returns_existing(db):
    # Create first
    c1 = await get_or_create_contact(db, "+15551112222", "User One")
    await db.commit()

    # Should return same contact
    c2 = await get_or_create_contact(db, "+15551112222", "User Two")
    assert c1.id == c2.id
    # Name should be updated since c1 already had a name
    assert c2.name == "User One"


@pytest.mark.asyncio
async def test_get_available_slots(seeded_db):
    db = seeded_db

    result = await db.execute(select(Department).where(Department.code == "BLDG"))
    dept = result.scalar_one()

    # Get slots for next Monday (weekday)
    today = date.today()
    days_until_monday = (7 - today.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    next_monday = today + timedelta(days=days_until_monday)

    slots = await get_available_slots(db, dept.id, next_monday)
    assert len(slots) > 0
    # 9am to 4pm with 30-min slots = 14 slots
    assert len(slots) == 14


@pytest.mark.asyncio
async def test_get_available_slots_weekend_returns_empty(seeded_db):
    db = seeded_db

    result = await db.execute(select(Department).where(Department.code == "BLDG"))
    dept = result.scalar_one()

    # Get next Saturday
    today = date.today()
    days_until_saturday = (5 - today.weekday()) % 7
    if days_until_saturday == 0:
        days_until_saturday = 7
    next_saturday = today + timedelta(days=days_until_saturday)

    slots = await get_available_slots(db, dept.id, next_saturday)
    assert len(slots) == 0


@pytest.mark.asyncio
async def test_book_appointment(seeded_db):
    db = seeded_db

    result = await db.execute(select(Department).where(Department.code == "BLDG"))
    dept = result.scalar_one()

    contact = await get_or_create_contact(db, "+15553334444")

    start = datetime.utcnow() + timedelta(days=2)
    end = start + timedelta(minutes=30)

    appt = await book_appointment(
        db,
        contact_id=contact.id,
        department_id=dept.id,
        scheduled_start=start,
        scheduled_end=end,
        title="Permit consultation",
        language="es",
    )

    assert appt.id is not None
    assert appt.status == "confirmed"
    assert appt.language == "es"
    assert appt.title == "Permit consultation"


@pytest.mark.asyncio
async def test_cancel_appointment(seeded_db):
    db = seeded_db

    result = await db.execute(select(Department).where(Department.code == "BLDG"))
    dept = result.scalar_one()

    contact = await get_or_create_contact(db, "+15555556666")

    start = datetime.utcnow() + timedelta(days=3)
    appt = await book_appointment(
        db,
        contact_id=contact.id,
        department_id=dept.id,
        scheduled_start=start,
        scheduled_end=start + timedelta(minutes=30),
        title="Test appointment",
    )
    await db.commit()

    cancelled = await cancel_appointment(db, appt.id, "Changed my mind")
    assert cancelled is not None
    assert cancelled.status == "cancelled"


@pytest.mark.asyncio
async def test_cancel_nonexistent_appointment(db):
    result = await cancel_appointment(db, 99999)
    assert result is None


@pytest.mark.asyncio
async def test_lookup_appointments_by_phone(seeded_db):
    db = seeded_db

    result = await db.execute(select(Department).where(Department.code == "BLDG"))
    dept = result.scalar_one()

    contact = await get_or_create_contact(db, "+15557778888")

    start = datetime.utcnow() + timedelta(days=5)
    await book_appointment(
        db,
        contact_id=contact.id,
        department_id=dept.id,
        scheduled_start=start,
        scheduled_end=start + timedelta(minutes=30),
        title="Future appointment",
    )
    await db.commit()

    appointments = await lookup_appointments_by_phone(db, "+15557778888")
    assert len(appointments) == 1
    assert appointments[0].title == "Future appointment"


@pytest.mark.asyncio
async def test_lookup_appointments_unknown_phone(db):
    appointments = await lookup_appointments_by_phone(db, "+10000000000")
    assert appointments == []


# ---------------------------------------------------------------------------
# Conflict detection tests
# ---------------------------------------------------------------------------


def _next_weekday(weekday: int = 0) -> date:
    """Return the next occurrence of the given weekday (0=Mon … 4=Fri)."""
    today = date.today()
    days_ahead = (weekday - today.weekday()) % 7 or 7
    return today + timedelta(days=days_ahead)


def _slot_start(target_date: date, hour: int = 9) -> datetime:
    """Return a datetime at *hour*:00 on *target_date* (within 9-16 window)."""
    return datetime.combine(target_date, time(hour, 0))


# -- happy path: book inside capacity (max_concurrent=2 in seeded_db) -------


@pytest.mark.asyncio
async def test_conflict_check_happy_path_within_capacity(seeded_db):
    """First booking of a slot should succeed when capacity allows it."""
    db = seeded_db
    result = await db.execute(select(Department).where(Department.code == "BLDG"))
    dept = result.scalar_one()
    contact = await get_or_create_contact(db, "+15550001111")

    target = _next_weekday(0)  # Monday
    start = _slot_start(target, 9)
    end = start + timedelta(minutes=30)

    # Should not raise
    appt = await book_appointment(
        db,
        contact_id=contact.id,
        department_id=dept.id,
        scheduled_start=start,
        scheduled_end=end,
        title="Conflict happy path",
    )
    assert appt.id is not None
    assert appt.status == "confirmed"


# -- single slot full (max_concurrent=1 custom dept) ------------------------


@pytest.mark.asyncio
async def test_conflict_check_single_slot_full_raises(seeded_db):
    """BookingConflictError raised when a slot with max_concurrent=1 is full."""
    db = seeded_db

    # Create a department with max_concurrent=1
    restricted_dept = Department(
        name="Restricted Dept",
        code="RST",
        description="One person at a time",
        operating_hours='{"mon-fri": "9:00-16:00"}',
    )
    db.add(restricted_dept)
    await db.flush()

    target = _next_weekday(1)  # Tuesday
    slot = TimeSlot(
        department_id=restricted_dept.id,
        day_of_week=target.weekday(),
        start_time=time(9, 0),
        end_time=time(16, 0),
        slot_duration_minutes=30,
        max_concurrent=1,
    )
    db.add(slot)
    await db.flush()

    contact = await get_or_create_contact(db, "+15550002222")
    start = _slot_start(target, 9)
    end = start + timedelta(minutes=30)

    # First booking should succeed
    appt1 = await book_appointment(
        db,
        contact_id=contact.id,
        department_id=restricted_dept.id,
        scheduled_start=start,
        scheduled_end=end,
        title="Slot taker",
    )
    assert appt1.status == "confirmed"
    await db.commit()

    # Second booking into the same slot must raise BookingConflictError
    contact2 = await get_or_create_contact(db, "+15550003333")
    with pytest.raises(BookingConflictError):
        await book_appointment(
            db,
            contact_id=contact2.id,
            department_id=restricted_dept.id,
            scheduled_start=start,
            scheduled_end=end,
            title="Should conflict",
        )


# -- concurrent limit hit (max_concurrent=2 in seeded BLDG dept) -----------


@pytest.mark.asyncio
async def test_conflict_check_concurrent_limit_hit(seeded_db):
    """BookingConflictError raised after max_concurrent (2) is exhausted."""
    db = seeded_db
    result = await db.execute(select(Department).where(Department.code == "BLDG"))
    dept = result.scalar_one()

    target = _next_weekday(2)  # Wednesday to avoid collision with other tests
    start = _slot_start(target, 10)
    end = start + timedelta(minutes=30)

    c1 = await get_or_create_contact(db, "+15550004444")
    c2 = await get_or_create_contact(db, "+15550005555")
    c3 = await get_or_create_contact(db, "+15550006666")

    # Fill both concurrent slots
    await book_appointment(
        db,
        contact_id=c1.id,
        department_id=dept.id,
        scheduled_start=start,
        scheduled_end=end,
        title="Slot 1",
    )
    await book_appointment(
        db,
        contact_id=c2.id,
        department_id=dept.id,
        scheduled_start=start,
        scheduled_end=end,
        title="Slot 2",
    )
    await db.commit()

    # Third booking must raise
    with pytest.raises(BookingConflictError) as exc_info:
        await book_appointment(
            db,
            contact_id=c3.id,
            department_id=dept.id,
            scheduled_start=start,
            scheduled_end=end,
            title="Slot 3 - should fail",
        )

    assert "fully booked" in str(exc_info.value).lower()


# -- skip_conflict_check bypasses the guard ---------------------------------


@pytest.mark.asyncio
async def test_conflict_check_skip_bypass(seeded_db):
    """skip_conflict_check=True allows booking even when slot is at capacity."""
    db = seeded_db
    result = await db.execute(select(Department).where(Department.code == "BLDG"))
    dept = result.scalar_one()

    target = _next_weekday(3)  # Thursday
    start = _slot_start(target, 11)
    end = start + timedelta(minutes=30)

    c1 = await get_or_create_contact(db, "+15550007777")
    c2 = await get_or_create_contact(db, "+15550008888")
    c3 = await get_or_create_contact(db, "+15550009999")

    # Fill both concurrent slots normally
    await book_appointment(
        db,
        contact_id=c1.id,
        department_id=dept.id,
        scheduled_start=start,
        scheduled_end=end,
        title="Bypass slot 1",
    )
    await book_appointment(
        db,
        contact_id=c2.id,
        department_id=dept.id,
        scheduled_start=start,
        scheduled_end=end,
        title="Bypass slot 2",
    )
    await db.commit()

    # Third booking with bypass should succeed without raising
    appt = await book_appointment(
        db,
        contact_id=c3.id,
        department_id=dept.id,
        scheduled_start=start,
        scheduled_end=end,
        title="Bypass slot 3 - override",
        skip_conflict_check=True,
    )
    assert appt.id is not None
    assert appt.status == "confirmed"


# -- conflict error message content -----------------------------------------


@pytest.mark.asyncio
async def test_conflict_error_message_includes_timestamp(seeded_db):
    """BookingConflictError message should include the ISO timestamp."""
    db = seeded_db

    # Create a max_concurrent=1 department
    tiny_dept = Department(
        name="Tiny Dept",
        code="TINY",
        description="Single slot",
        operating_hours='{"mon-fri": "9:00-16:00"}',
    )
    db.add(tiny_dept)
    await db.flush()

    target = _next_weekday(4)  # Friday
    slot = TimeSlot(
        department_id=tiny_dept.id,
        day_of_week=target.weekday(),
        start_time=time(9, 0),
        end_time=time(16, 0),
        slot_duration_minutes=30,
        max_concurrent=1,
    )
    db.add(slot)
    await db.flush()

    contact = await get_or_create_contact(db, "+15550010101")
    start = _slot_start(target, 13)
    end = start + timedelta(minutes=30)

    await book_appointment(
        db,
        contact_id=contact.id,
        department_id=tiny_dept.id,
        scheduled_start=start,
        scheduled_end=end,
        title="Filler",
    )
    await db.commit()

    contact2 = await get_or_create_contact(db, "+15550011111")
    with pytest.raises(BookingConflictError) as exc_info:
        await book_appointment(
            db,
            contact_id=contact2.id,
            department_id=tiny_dept.id,
            scheduled_start=start,
            scheduled_end=end,
            title="Conflict",
        )

    error_msg = str(exc_info.value)
    # Should include the ISO datetime of the conflicting slot
    assert start.isoformat() in error_msg


# -- adjacent (non-overlapping) slots must not conflict ---------------------


@pytest.mark.asyncio
async def test_conflict_check_adjacent_slots_do_not_conflict(seeded_db):
    """Two back-to-back bookings (non-overlapping) should both succeed."""
    db = seeded_db

    # Create a max_concurrent=1 department so any overlap would fail
    adj_dept = Department(
        name="Adjacent Test Dept",
        code="ADJ",
        description="Single concurrent slot",
        operating_hours='{"mon-fri": "9:00-16:00"}',
    )
    db.add(adj_dept)
    await db.flush()

    target = _next_weekday(0)  # Monday
    slot = TimeSlot(
        department_id=adj_dept.id,
        day_of_week=target.weekday(),
        start_time=time(9, 0),
        end_time=time(16, 0),
        slot_duration_minutes=30,
        max_concurrent=1,
    )
    db.add(slot)
    await db.flush()

    contact = await get_or_create_contact(db, "+15550012222")

    # 9:00-9:30
    start1 = _slot_start(target, 9)
    end1 = start1 + timedelta(minutes=30)
    # 9:30-10:00 (immediately after — no overlap)
    start2 = end1
    end2 = start2 + timedelta(minutes=30)

    appt1 = await book_appointment(
        db,
        contact_id=contact.id,
        department_id=adj_dept.id,
        scheduled_start=start1,
        scheduled_end=end1,
        title="Adjacent slot 1",
    )
    await db.commit()

    # This must NOT raise even though max_concurrent=1
    appt2 = await book_appointment(
        db,
        contact_id=contact.id,
        department_id=adj_dept.id,
        scheduled_start=start2,
        scheduled_end=end2,
        title="Adjacent slot 2",
    )
    assert appt1.id is not None
    assert appt2.id is not None
    assert appt1.id != appt2.id
