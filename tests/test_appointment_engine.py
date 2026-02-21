"""Tests for the appointment booking engine."""

import pytest
from datetime import date, datetime, timedelta
from sqlalchemy import select

from app.models.department import Department
from app.services.appointment_engine import (
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
