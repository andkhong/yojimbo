"""Comprehensive tests for Appointment CRUD, messages endpoint, and lifecycle.

Covers:
- Appointment create, read, update, cancel
- Appointment filtering (date, department, status)
- Availability check
- Messages list and filtering
- Full call lifecycle: start → transcript turn → end → summary stored
- Contact history reflects all event types
"""

from datetime import datetime, timedelta
import sys
import types

import pytest

from app.models.appointment import Appointment
from app.models.call import Call, ConversationTurn
from app.models.contact import Contact
from app.models.department import Department
from app.models.message import SMSMessage


# ===========================================================================
# Appointment CRUD
# ===========================================================================


@pytest.mark.asyncio
async def test_create_appointment(client, seeded_db):
    """Can create an appointment for a contact+department."""
    # First create a contact
    contact_resp = await client.post("/api/contacts", json={"phone_number": "+15551110001"})
    contact_id = contact_resp.json()["contact"]["id"]

    # Get the seeded department
    depts = (await client.get("/api/departments")).json()["departments"]
    dept_id = depts[0]["id"]

    now = datetime.utcnow()
    resp = await client.post(
        "/api/appointments",
        json={
            "contact_id": contact_id,
            "department_id": dept_id,
            "title": "Permit Review",
            "description": "Annual inspection",
            "scheduled_start": (now + timedelta(days=1, hours=9)).isoformat(),
            "scheduled_end": (now + timedelta(days=1, hours=9, minutes=30)).isoformat(),
            "language": "en",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["appointment"]["title"] == "Permit Review"
    assert data["appointment"]["status"] == "confirmed"
    assert data["appointment"]["contact_id"] == contact_id


@pytest.mark.asyncio
async def test_get_appointment(client, seeded_db):
    """Can retrieve a created appointment by ID."""
    contact_resp = await client.post("/api/contacts", json={"phone_number": "+15551110002"})
    contact_id = contact_resp.json()["contact"]["id"]
    depts = (await client.get("/api/departments")).json()["departments"]
    dept_id = depts[0]["id"]

    now = datetime.utcnow()
    create_resp = await client.post(
        "/api/appointments",
        json={
            "contact_id": contact_id,
            "department_id": dept_id,
            "title": "Road Inquiry",
            "scheduled_start": (now + timedelta(days=2)).isoformat(),
            "scheduled_end": (now + timedelta(days=2, hours=1)).isoformat(),
        },
    )
    appt_id = create_resp.json()["appointment"]["id"]

    resp = await client.get(f"/api/appointments/{appt_id}")
    assert resp.status_code == 200
    assert resp.json()["appointment"]["id"] == appt_id


@pytest.mark.asyncio
async def test_get_nonexistent_appointment_returns_404(client):
    resp = await client.get("/api/appointments/99999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_appointment_status(client, seeded_db):
    """Can update appointment status to cancelled."""
    contact_resp = await client.post("/api/contacts", json={"phone_number": "+15551110003"})
    contact_id = contact_resp.json()["contact"]["id"]
    depts = (await client.get("/api/departments")).json()["departments"]
    dept_id = depts[0]["id"]

    now = datetime.utcnow()
    create_resp = await client.post(
        "/api/appointments",
        json={
            "contact_id": contact_id,
            "department_id": dept_id,
            "title": "Tax Query",
            "scheduled_start": (now + timedelta(days=3)).isoformat(),
            "scheduled_end": (now + timedelta(days=3, hours=1)).isoformat(),
        },
    )
    appt_id = create_resp.json()["appointment"]["id"]

    resp = await client.patch(
        f"/api/appointments/{appt_id}",
        json={"status": "cancelled"},
    )
    assert resp.status_code == 200
    assert resp.json()["appointment"]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_appointment(client, seeded_db):
    """DELETE endpoint cancels the appointment."""
    contact_resp = await client.post("/api/contacts", json={"phone_number": "+15551110004"})
    contact_id = contact_resp.json()["contact"]["id"]
    depts = (await client.get("/api/departments")).json()["departments"]
    dept_id = depts[0]["id"]

    now = datetime.utcnow()
    create_resp = await client.post(
        "/api/appointments",
        json={
            "contact_id": contact_id,
            "department_id": dept_id,
            "title": "Park Permit",
            "scheduled_start": (now + timedelta(days=4)).isoformat(),
            "scheduled_end": (now + timedelta(days=4, hours=1)).isoformat(),
        },
    )
    appt_id = create_resp.json()["appointment"]["id"]

    resp = await client.delete(f"/api/appointments/{appt_id}")
    assert resp.status_code == 200
    assert resp.json()["appointment"]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_list_appointments_filter_by_status(client, db):
    """Can filter appointments by status."""
    contact = Contact(phone_number="+15551120001")
    dept = Department(name="Sewer Dept", code="SWR")
    db.add(contact)
    db.add(dept)
    await db.flush()

    now = datetime.utcnow()
    db.add(
        Appointment(
            contact_id=contact.id,
            department_id=dept.id,
            title="A",
            status="confirmed",
            scheduled_start=now + timedelta(days=1),
            scheduled_end=now + timedelta(days=1, hours=1),
        )
    )
    db.add(
        Appointment(
            contact_id=contact.id,
            department_id=dept.id,
            title="B",
            status="cancelled",
            scheduled_start=now + timedelta(days=2),
            scheduled_end=now + timedelta(days=2, hours=1),
        )
    )
    await db.flush()

    resp = await client.get("/api/appointments?status=confirmed")
    assert resp.status_code == 200
    data = resp.json()
    assert all(a["status"] == "confirmed" for a in data["appointments"])


@pytest.mark.asyncio
async def test_list_appointments_filter_by_department(client, db):
    """Can filter appointments by department_id."""
    contact = Contact(phone_number="+15551120002")
    dept_a = Department(name="Dept A filter", code="DAF")
    dept_b = Department(name="Dept B filter", code="DBF")
    db.add(contact)
    db.add(dept_a)
    db.add(dept_b)
    await db.flush()

    now = datetime.utcnow()
    db.add(
        Appointment(
            contact_id=contact.id,
            department_id=dept_a.id,
            title="A",
            status="confirmed",
            scheduled_start=now + timedelta(days=1),
            scheduled_end=now + timedelta(days=1, hours=1),
        )
    )
    db.add(
        Appointment(
            contact_id=contact.id,
            department_id=dept_b.id,
            title="B",
            status="confirmed",
            scheduled_start=now + timedelta(days=2),
            scheduled_end=now + timedelta(days=2, hours=1),
        )
    )
    await db.flush()

    resp = await client.get(f"/api/appointments?department_id={dept_a.id}")
    assert resp.status_code == 200
    appts = resp.json()["appointments"]
    assert all(a["department_id"] == dept_a.id for a in appts)
    assert len(appts) == 1


@pytest.mark.asyncio
async def test_list_appointments_filter_by_date(client, db):
    """Can filter appointments by target_date."""
    contact = Contact(phone_number="+15551120003")
    dept = Department(name="Clerk Dept", code="CLK")
    db.add(contact)
    db.add(dept)
    await db.flush()

    now = datetime.utcnow()
    # Tomorrow
    tomorrow = (now + timedelta(days=1)).date()
    db.add(
        Appointment(
            contact_id=contact.id,
            department_id=dept.id,
            title="Tomorrow",
            status="confirmed",
            scheduled_start=datetime.combine(tomorrow, datetime.min.time().replace(hour=9)),
            scheduled_end=datetime.combine(tomorrow, datetime.min.time().replace(hour=10)),
        )
    )
    # Day after
    db.add(
        Appointment(
            contact_id=contact.id,
            department_id=dept.id,
            title="Day After",
            status="confirmed",
            scheduled_start=now + timedelta(days=2),
            scheduled_end=now + timedelta(days=2, hours=1),
        )
    )
    await db.flush()

    resp = await client.get(f"/api/appointments?target_date={tomorrow.isoformat()}")
    assert resp.status_code == 200
    appts = resp.json()["appointments"]
    assert len(appts) == 1
    assert appts[0]["title"] == "Tomorrow"


@pytest.mark.asyncio
async def test_appointments_pagination(client, db):
    """Appointments list respects per_page."""
    contact = Contact(phone_number="+15551120004")
    dept = Department(name="DMV Dept", code="DMV")
    db.add(contact)
    db.add(dept)
    await db.flush()

    now = datetime.utcnow()
    for i in range(5):
        db.add(
            Appointment(
                contact_id=contact.id,
                department_id=dept.id,
                title=f"Appt {i}",
                status="confirmed",
                scheduled_start=now + timedelta(days=i + 1),
                scheduled_end=now + timedelta(days=i + 1, hours=1),
            )
        )
    await db.flush()

    resp = await client.get("/api/appointments?per_page=2&page=1")
    assert resp.status_code == 200
    assert len(resp.json()["appointments"]) == 2
    assert resp.json()["total"] == 5


@pytest.mark.asyncio
async def test_list_appointments_invalid_target_date_returns_i18n_error(client):
    resp = await client.get("/api/appointments?target_date=2026-02-30")
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["message_key"] == "appointments.invalid_date"
    assert detail["params"]["field"] == "target_date"


@pytest.mark.asyncio
async def test_availability_invalid_target_date_returns_i18n_error(client):
    resp = await client.get("/api/appointments/availability?department_id=1&target_date=not-a-date")
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["message_key"] == "appointments.invalid_date"
    assert detail["params"]["value"] == "not-a-date"


# ===========================================================================
# Messages endpoint
# ===========================================================================


@pytest.mark.asyncio
async def test_list_messages_empty(client):
    resp = await client.get("/api/messages")
    assert resp.status_code == 200
    data = resp.json()
    assert data["messages"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_list_messages_with_data(client, db):
    """Can list SMS messages."""
    db.add(
        SMSMessage(
            twilio_message_sid="SM_list_001",
            direction="inbound",
            body="Hello",
            status="received",
        )
    )
    db.add(
        SMSMessage(
            twilio_message_sid="SM_list_002",
            direction="outbound",
            body="Hi back",
            status="sent",
        )
    )
    await db.flush()

    resp = await client.get("/api/messages")
    assert resp.status_code == 200
    assert resp.json()["total"] == 2


@pytest.mark.asyncio
async def test_list_messages_filter_by_contact(client, db):
    """Can filter messages by contact_id."""
    contact = Contact(phone_number="+15551130001")
    db.add(contact)
    await db.flush()

    db.add(
        SMSMessage(
            twilio_message_sid="SM_flt_001",
            contact_id=contact.id,
            direction="inbound",
            body="My message",
            status="received",
        )
    )
    db.add(
        SMSMessage(
            twilio_message_sid="SM_flt_002",
            contact_id=None,
            direction="inbound",
            body="Unlinked",
            status="received",
        )
    )
    await db.flush()

    resp = await client.get(f"/api/messages?contact_id={contact.id}")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    assert resp.json()["messages"][0]["contact_id"] == contact.id


@pytest.mark.asyncio
async def test_messages_pagination(client, db):
    """Messages respect per_page."""
    for i in range(5):
        db.add(
            SMSMessage(
                twilio_message_sid=f"SM_page_{i:03d}",
                direction="inbound",
                body=f"Message {i}",
                status="received",
            )
        )
    await db.flush()

    resp = await client.get("/api/messages?per_page=3&page=1")
    assert resp.status_code == 200
    assert len(resp.json()["messages"]) == 3


class _FakeTwilioMessagesAPI:
    def create(self, **kwargs):
        return types.SimpleNamespace(sid="SM_int_out_001")


class _FakeTwilioClient:
    def __init__(self, *args, **kwargs):
        self.messages = _FakeTwilioMessagesAPI()


def _install_fake_twilio(monkeypatch: pytest.MonkeyPatch, client_cls=_FakeTwilioClient) -> None:
    twilio_mod = types.ModuleType("twilio")
    twilio_rest_mod = types.ModuleType("twilio.rest")
    twilio_rest_mod.Client = client_cls

    monkeypatch.setitem(sys.modules, "twilio", twilio_mod)
    monkeypatch.setitem(sys.modules, "twilio.rest", twilio_rest_mod)


@pytest.mark.asyncio
async def test_send_sms_success(client, monkeypatch):
    _install_fake_twilio(monkeypatch)

    resp = await client.post(
        "/api/messages/send",
        json={"phone_number": "+15556667777", "body": "Test outbound"},
    )
    assert resp.status_code == 201
    payload = resp.json()["message"]
    assert payload["twilio_message_sid"] == "SM_int_out_001"
    assert payload["direction"] == "outbound"
    assert payload["status"] == "sent"


@pytest.mark.asyncio
async def test_send_sms_failure_is_i18n_ready(client, monkeypatch):
    class _RaisingTwilioClient:
        def __init__(self, *args, **kwargs):
            self.messages = self

        def create(self, **kwargs):
            raise RuntimeError("twilio unavailable")

    _install_fake_twilio(monkeypatch, _RaisingTwilioClient)

    resp = await client.post(
        "/api/messages/send",
        json={"phone_number": "+15556667777", "body": "Test outbound"},
    )
    assert resp.status_code == 502
    detail = resp.json()["detail"]
    assert detail["message_key"] == "messages.send.failed"
    assert detail["message"] == "Failed to send SMS"
    assert "twilio unavailable" in detail["params"]["reason"]


# ===========================================================================
# Full call lifecycle
# ===========================================================================


@pytest.mark.asyncio
async def test_full_call_lifecycle(client, db):
    """Test the full lifecycle: create call → add transcript turns → terminate → check summary.

    This simulates what happens during a real AI conversation:
    1. Call starts (Twilio status webhook)
    2. Transcript turns get recorded
    3. Call gets terminated (dashboard action)
    4. Call summary is accessible via GET /api/calls/{id}
    """
    # 1. Create an active call
    call = Call(
        twilio_call_sid="CA_lifecycle_001",
        direction="inbound",
        status="in_progress",
        detected_language="en",
        started_at=datetime.utcnow() - timedelta(minutes=5),
    )
    db.add(call)
    await db.flush()

    # 2. Add transcript turns
    for i, (role, text) in enumerate(
        [
            ("caller", "I need a parking permit"),
            ("agent", "I can help you with that. What type of vehicle?"),
            ("caller", "It's a 2020 Honda Civic"),
            ("agent", "Your permit will be ready in 3 business days."),
        ]
    ):
        db.add(
            ConversationTurn(
                call_id=call.id,
                sequence=i,
                role=role,
                original_text=text,
                language="en",
            )
        )
    await db.flush()

    # 3. Verify call shows in live feed
    live_resp = await client.get("/api/calls/live")
    assert live_resp.status_code == 200
    assert live_resp.json()["count"] == 1
    live_call = live_resp.json()["live_calls"][0]
    assert len(live_call["recent_turns"]) == 4

    # 4. Terminate the call
    term_resp = await client.post(f"/api/calls/{call.id}/terminate")
    assert term_resp.status_code == 200
    assert term_resp.json()["terminated"] is True

    # 5. Verify call no longer in live feed
    live_resp2 = await client.get("/api/calls/live")
    assert live_resp2.json()["count"] == 0

    # 6. Retrieve full call record with transcript
    detail_resp = await client.get(f"/api/calls/{call.id}")
    assert detail_resp.status_code == 200
    call_data = detail_resp.json()
    assert call_data["call"]["status"] == "completed"
    assert call_data["call"]["ended_at"] is not None
    assert len(call_data["transcript"]) == 4

    # 7. Transcript includes all turns
    transcript = call_data["transcript"]
    assert transcript[0]["role"] == "caller"
    assert "parking permit" in transcript[0]["original_text"]
    assert transcript[3]["role"] == "agent"


@pytest.mark.asyncio
async def test_call_transcript_endpoint(client, db):
    """GET /api/calls/{id}/transcript returns all conversation turns."""
    call = Call(
        twilio_call_sid="CA_trans_001",
        direction="inbound",
        status="completed",
        started_at=datetime.utcnow(),
    )
    db.add(call)
    await db.flush()

    for i in range(3):
        db.add(
            ConversationTurn(
                call_id=call.id,
                sequence=i,
                role="caller" if i % 2 == 0 else "agent",
                original_text=f"Turn {i}",
                language="en",
            )
        )
    await db.flush()

    resp = await client.get(f"/api/calls/{call.id}/transcript")
    assert resp.status_code == 200
    assert len(resp.json()["turns"]) == 3


@pytest.mark.asyncio
async def test_call_filter_by_date_range(client, db):
    """Calls can be filtered by date_from and date_to."""
    now = datetime.utcnow()
    db.add(
        Call(
            twilio_call_sid="CA_date_old",
            direction="inbound",
            status="completed",
            started_at=now - timedelta(days=10),
        )
    )
    db.add(
        Call(
            twilio_call_sid="CA_date_new",
            direction="inbound",
            status="completed",
            started_at=now - timedelta(days=1),
        )
    )
    await db.flush()

    from_date = (now - timedelta(days=5)).isoformat()
    resp = await client.get(f"/api/calls?date_from={from_date}")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    assert "CA_date_new" in resp.json()["calls"][0]["twilio_call_sid"]


@pytest.mark.asyncio
async def test_call_filter_by_status(client, db):
    """Calls can be filtered by status."""
    now = datetime.utcnow()
    db.add(
        Call(
            twilio_call_sid="CA_stat_comp", direction="inbound", status="completed", started_at=now
        )
    )
    db.add(
        Call(twilio_call_sid="CA_stat_ring", direction="inbound", status="ringing", started_at=now)
    )
    await db.flush()

    resp = await client.get("/api/calls?status=completed")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    assert resp.json()["calls"][0]["status"] == "completed"


# ===========================================================================
# Department stats integration
# ===========================================================================


@pytest.mark.asyncio
async def test_department_stats_with_calls_and_appointments(client, db):
    """Department stats reflects actual call and appointment data."""
    dept = Department(name="Stats Test Dept", code="STD")
    contact = Contact(phone_number="+15551140001")
    db.add(dept)
    db.add(contact)
    await db.flush()

    now = datetime.utcnow()
    # Add calls
    db.add(
        Call(
            twilio_call_sid="CA_st1",
            direction="inbound",
            status="completed",
            resolution_status="resolved",
            department_id=dept.id,
            started_at=now,
        )
    )
    db.add(
        Call(
            twilio_call_sid="CA_st2",
            direction="inbound",
            status="in_progress",
            department_id=dept.id,
            started_at=now,
        )
    )
    # Add appointment
    db.add(
        Appointment(
            contact_id=contact.id,
            department_id=dept.id,
            title="Stats Appt",
            status="confirmed",
            scheduled_start=now + timedelta(days=1),
            scheduled_end=now + timedelta(days=1, hours=1),
        )
    )
    await db.flush()

    resp = await client.get(f"/api/departments/{dept.id}/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_calls"] == 2
    assert data["active_calls"] == 1
    assert data["total_appointments"] == 1
    assert data["upcoming_appointments"] == 1


# ===========================================================================
# Knowledge base — language filtering
# ===========================================================================


@pytest.mark.asyncio
async def test_knowledge_language_filter(client, db):
    """Knowledge list can be filtered by language."""
    from app.models.knowledge import KnowledgeEntry

    db.add(KnowledgeEntry(question="Q en?", answer="A en.", language="en"))
    db.add(KnowledgeEntry(question="Q es?", answer="A es.", language="es"))
    db.add(KnowledgeEntry(question="Q zh?", answer="A zh.", language="zh"))
    await db.flush()

    resp = await client.get("/api/knowledge?language=es")
    assert resp.status_code == 200
    entries = resp.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["language"] == "es"


@pytest.mark.asyncio
async def test_knowledge_department_filter_includes_global(client, db):
    """Knowledge filter for a department includes global (null dept) entries."""
    from app.models.knowledge import KnowledgeEntry

    dept = Department(name="Rec Dept", code="REC")
    db.add(dept)
    await db.flush()

    db.add(KnowledgeEntry(question="Global?", answer="Yes.", language="en", department_id=None))
    db.add(
        KnowledgeEntry(
            question="Dept specific?", answer="Yes.", language="en", department_id=dept.id
        )
    )
    db.add(
        KnowledgeEntry(
            question="Other dept?", answer="No.", language="en", department_id=dept.id + 999
        )
    )
    await db.flush()

    resp = await client.get(f"/api/knowledge?department_id={dept.id}")
    assert resp.status_code == 200
    # Should return dept-specific + global (2), not the other dept's entry
    assert resp.json()["total"] == 2
