"""Tests for database models and basic CRUD operations."""

import pytest
from datetime import datetime, timedelta
from sqlalchemy import select

from app.models.contact import Contact
from app.models.call import Call, ConversationTurn
from app.models.department import Department
from app.models.appointment import Appointment


@pytest.mark.asyncio
async def test_create_contact(db):
    contact = Contact(
        phone_number="+15551234567",
        name="Jane Doe",
        preferred_language="es",
    )
    db.add(contact)
    await db.flush()

    result = await db.execute(select(Contact).where(Contact.id == contact.id))
    saved = result.scalar_one()
    assert saved.phone_number == "+15551234567"
    assert saved.name == "Jane Doe"
    assert saved.preferred_language == "es"


@pytest.mark.asyncio
async def test_create_call_with_transcript(db):
    call = Call(
        twilio_call_sid="CA123456",
        direction="inbound",
        status="completed",
        detected_language="es",
        started_at=datetime.utcnow(),
    )
    db.add(call)
    await db.flush()

    turn1 = ConversationTurn(
        call_id=call.id,
        sequence=1,
        role="caller",
        original_text="Necesito una cita",
        translated_text="I need an appointment",
        language="es",
    )
    turn2 = ConversationTurn(
        call_id=call.id,
        sequence=2,
        role="agent",
        original_text="I can help you with that.",
        language="en",
    )
    db.add_all([turn1, turn2])
    await db.flush()

    result = await db.execute(
        select(ConversationTurn)
        .where(ConversationTurn.call_id == call.id)
        .order_by(ConversationTurn.sequence)
    )
    turns = result.scalars().all()
    assert len(turns) == 2
    assert turns[0].role == "caller"
    assert turns[1].role == "agent"


@pytest.mark.asyncio
async def test_create_appointment(seeded_db):
    db = seeded_db

    # Get the seeded department
    result = await db.execute(select(Department).where(Department.code == "BLDG"))
    dept = result.scalar_one()

    contact = Contact(phone_number="+15559876543", preferred_language="en")
    db.add(contact)
    await db.flush()

    now = datetime.utcnow()
    appt = Appointment(
        contact_id=contact.id,
        department_id=dept.id,
        title="Building permit review",
        status="confirmed",
        scheduled_start=now + timedelta(days=1),
        scheduled_end=now + timedelta(days=1, minutes=30),
    )
    db.add(appt)
    await db.flush()

    result = await db.execute(select(Appointment).where(Appointment.id == appt.id))
    saved = result.scalar_one()
    assert saved.title == "Building permit review"
    assert saved.status == "confirmed"
    assert saved.department_id == dept.id
