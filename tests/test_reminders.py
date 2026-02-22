"""Tests for the appointment reminder SMS service."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.models.appointment import Appointment
from app.models.contact import Contact
from app.services.appointment_engine import book_appointment, get_or_create_contact
from app.services.reminders import (
    _build_reminder_message,
    get_appointments_needing_reminders,
    process_due_reminders,
    send_appointment_reminder,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_contact(db, phone="+15550020001", name="Test User"):
    return await get_or_create_contact(db, phone, name=name)


async def _make_department(db):
    from app.models.appointment import TimeSlot
    from app.models.department import Department
    from datetime import time

    dept = Department(
        name="Reminder Test Dept",
        code="RMD",
        description="For reminder tests",
        operating_hours='{"mon-fri": "9:00-16:00"}',
    )
    db.add(dept)
    await db.flush()

    # Add time slots for every weekday
    for day in range(5):
        slot = TimeSlot(
            department_id=dept.id,
            day_of_week=day,
            start_time=time(9, 0),
            end_time=time(16, 0),
            slot_duration_minutes=30,
            max_concurrent=2,
        )
        db.add(slot)

    await db.flush()
    return dept


# ---------------------------------------------------------------------------
# _build_reminder_message
# ---------------------------------------------------------------------------


def test_build_reminder_message_includes_name():
    contact = Contact(phone_number="+15550020001", name="Alice")
    appt = Appointment(
        title="Permit Review",
        scheduled_start=datetime(2026, 3, 10, 10, 30),
    )
    msg = _build_reminder_message(appt, contact)
    assert "Alice" in msg
    assert "Permit Review" in msg
    assert "March 10" in msg


def test_build_reminder_message_no_name():
    contact = Contact(phone_number="+15550020002", name=None)
    appt = Appointment(
        title="Tax Consultation",
        scheduled_start=datetime(2026, 4, 15, 14, 0),
    )
    msg = _build_reminder_message(appt, contact)
    assert "Tax Consultation" in msg
    assert "April 15" in msg
    # No double space or awkward prefix
    assert "Hi!" in msg


def test_build_reminder_message_contains_cancel_instruction():
    contact = Contact(phone_number="+15550020003", name="Bob")
    appt = Appointment(
        title="Inspection",
        scheduled_start=datetime(2026, 5, 1, 9, 0),
    )
    msg = _build_reminder_message(appt, contact)
    assert "CANCEL" in msg


# ---------------------------------------------------------------------------
# send_appointment_reminder — missing appointment / contact
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_reminder_appointment_not_found(db):
    """ValueError raised when appointment ID does not exist."""
    with pytest.raises(ValueError, match="not found"):
        await send_appointment_reminder(99999, db)


@pytest.mark.asyncio
async def test_send_reminder_marks_reminder_sent(db):
    """reminder_sent is set to True after a successful SMS send."""
    dept = await _make_department(db)
    contact = await _make_contact(db)
    start = datetime.utcnow() + timedelta(hours=24)
    end = start + timedelta(minutes=30)

    appt = await book_appointment(
        db,
        contact_id=contact.id,
        department_id=dept.id,
        scheduled_start=start,
        scheduled_end=end,
        title="Reminder test appt",
    )
    await db.commit()

    assert appt.reminder_sent is False

    # Patch Twilio so no real HTTP call is made
    with patch("app.services.reminders._send_sms", new=AsyncMock(return_value=True)):
        result = await send_appointment_reminder(appt.id, db)

    assert result is True
    assert appt.reminder_sent is True


@pytest.mark.asyncio
async def test_send_reminder_returns_false_on_sms_failure(db):
    """send_appointment_reminder returns False when _send_sms fails."""
    dept = await _make_department(db)
    contact = await _make_contact(db, phone="+15550020010")
    start = datetime.utcnow() + timedelta(hours=24)
    end = start + timedelta(minutes=30)

    appt = await book_appointment(
        db,
        contact_id=contact.id,
        department_id=dept.id,
        scheduled_start=start,
        scheduled_end=end,
        title="SMS fail test",
    )
    await db.commit()

    with patch("app.services.reminders._send_sms", new=AsyncMock(return_value=False)):
        result = await send_appointment_reminder(appt.id, db)

    assert result is False
    # reminder_sent should remain False when the SMS didn't go through
    assert appt.reminder_sent is False


# ---------------------------------------------------------------------------
# get_appointments_needing_reminders
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_appointments_needing_reminders_finds_eligible(db):
    """Confirmed, unreminded appointments in the 24h window are returned."""
    dept = await _make_department(db)
    contact = await _make_contact(db, phone="+15550020020")

    # Appointment exactly 24h from now (inside window)
    start = datetime.utcnow() + timedelta(hours=24)
    appt = await book_appointment(
        db,
        contact_id=contact.id,
        department_id=dept.id,
        scheduled_start=start,
        scheduled_end=start + timedelta(minutes=30),
        title="Due reminder",
    )
    await db.commit()

    due = await get_appointments_needing_reminders(db)
    assert any(a.id == appt.id for a in due)


@pytest.mark.asyncio
async def test_get_appointments_needing_reminders_skips_already_sent(db):
    """Appointments with reminder_sent=True are excluded."""
    dept = await _make_department(db)
    contact = await _make_contact(db, phone="+15550020021")

    start = datetime.utcnow() + timedelta(hours=24)
    appt = await book_appointment(
        db,
        contact_id=contact.id,
        department_id=dept.id,
        scheduled_start=start,
        scheduled_end=start + timedelta(minutes=30),
        title="Already reminded",
    )
    appt.reminder_sent = True
    await db.commit()

    due = await get_appointments_needing_reminders(db)
    assert all(a.id != appt.id for a in due)


@pytest.mark.asyncio
async def test_get_appointments_needing_reminders_skips_too_far_future(db):
    """Appointments more than 25h away are outside the window."""
    dept = await _make_department(db)
    contact = await _make_contact(db, phone="+15550020022")

    start = datetime.utcnow() + timedelta(hours=48)
    appt = await book_appointment(
        db,
        contact_id=contact.id,
        department_id=dept.id,
        scheduled_start=start,
        scheduled_end=start + timedelta(minutes=30),
        title="Too far out",
    )
    await db.commit()

    due = await get_appointments_needing_reminders(db)
    assert all(a.id != appt.id for a in due)


@pytest.mark.asyncio
async def test_get_appointments_needing_reminders_skips_past(db):
    """Past appointments are not returned."""
    dept = await _make_department(db)
    contact = await _make_contact(db, phone="+15550020023")

    start = datetime.utcnow() - timedelta(hours=2)
    appt = await book_appointment(
        db,
        contact_id=contact.id,
        department_id=dept.id,
        scheduled_start=start,
        scheduled_end=start + timedelta(minutes=30),
        title="Past appointment",
    )
    await db.commit()

    due = await get_appointments_needing_reminders(db)
    assert all(a.id != appt.id for a in due)


# ---------------------------------------------------------------------------
# process_due_reminders
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_due_reminders_returns_summary(db):
    """process_due_reminders returns a dict with sent/failed/total keys."""
    dept = await _make_department(db)
    contact = await _make_contact(db, phone="+15550020030")

    start = datetime.utcnow() + timedelta(hours=24)
    await book_appointment(
        db,
        contact_id=contact.id,
        department_id=dept.id,
        scheduled_start=start,
        scheduled_end=start + timedelta(minutes=30),
        title="Batch reminder",
    )
    await db.commit()

    with patch("app.services.reminders._send_sms", new=AsyncMock(return_value=True)):
        summary = await process_due_reminders(db)

    assert "sent" in summary
    assert "failed" in summary
    assert "total" in summary
    assert summary["total"] >= 1
    assert summary["sent"] >= 1
    assert summary["failed"] == 0


@pytest.mark.asyncio
async def test_process_due_reminders_empty_when_none_due(db):
    """process_due_reminders returns total=0 when no reminders are due."""
    summary = await process_due_reminders(db)
    assert summary["total"] == 0
    assert summary["sent"] == 0
    assert summary["failed"] == 0
