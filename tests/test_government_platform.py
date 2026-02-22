"""Tests for Government Platform — Tiers 1, 2, 3.

Covers:
- Agent Config API (Item 2)
- Audit Log API (Item 3)
- Users/Staff Management API (Item 4)
- Live Call Monitor + Transfer + Terminate (Item 5)
- Call Analytics (Item 6)
- Appointment Analytics (Item 7)
- SLA Reports (Item 8)
- Knowledge Base (Item 9)
- Contact History + Merge + Tags (Item 10)
- Reminders (Item 11)
- Department Time Slots (Item 12)
"""

from datetime import datetime, time, timedelta

import pytest

from app.models.appointment import Appointment, TimeSlot
from app.models.call import Call
from app.models.contact import Contact
from app.models.department import Department
from app.models.knowledge import KnowledgeEntry
from app.models.user import DashboardUser
from app.core.security import hash_password


# ===========================================================================
# Item 2 — Agent Config
# ===========================================================================


@pytest.mark.asyncio
async def test_get_agent_config_empty(client):
    """Config endpoint returns empty when no values set."""
    resp = await client.get("/api/config/agent")
    assert resp.status_code == 200
    data = resp.json()
    assert "config" in data
    assert "entries" in data
    assert isinstance(data["config"], dict)


@pytest.mark.asyncio
async def test_update_agent_config(client):
    """Can set and retrieve config values."""
    resp = await client.put(
        "/api/config/agent",
        json={
            "updates": {
                "system_prompt": "You are a helpful city receptionist.",
                "greeting_message": "Welcome to City Hall!",
            },
            "updated_by": "admin",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["config"]["system_prompt"] == "You are a helpful city receptionist."
    assert data["config"]["greeting_message"] == "Welcome to City Hall!"


@pytest.mark.asyncio
async def test_update_agent_config_invalid_key(client):
    """Updating with invalid key returns 422."""
    resp = await client.put(
        "/api/config/agent",
        json={"updates": {"__invalid_key__": "value"}},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_config_key(client):
    """Can retrieve a single config key after setting it."""
    await client.put(
        "/api/config/agent",
        json={"updates": {"max_turns": "10"}},
    )
    resp = await client.get("/api/config/agent/max_turns")
    assert resp.status_code == 200
    assert resp.json()["value"] == "10"


@pytest.mark.asyncio
async def test_get_config_key_not_found(client):
    """Returns 404 for a valid key that isn't set."""
    resp = await client.get("/api/config/agent/max_turns")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_config_key(client):
    """Can delete a config key."""
    await client.put("/api/config/agent", json={"updates": {"timezone": "UTC"}})
    resp = await client.delete("/api/config/agent/timezone")
    assert resp.status_code == 204
    # Now should be gone
    resp2 = await client.get("/api/config/agent/timezone")
    assert resp2.status_code == 404


@pytest.mark.asyncio
async def test_list_valid_config_keys(client):
    """Keys endpoint returns valid keys."""
    resp = await client.get("/api/config/agent/keys")
    assert resp.status_code == 200
    assert "valid_keys" in resp.json()
    assert "system_prompt" in resp.json()["valid_keys"]


# ===========================================================================
# Item 3 — Audit Logs
# ===========================================================================


@pytest.mark.asyncio
async def test_list_audit_logs_empty(client):
    resp = await client.get("/api/audit-logs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["logs"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_list_audit_logs_with_data(client, db):
    from app.models.audit_log import AuditLog

    log = AuditLog(
        action="CREATE",
        resource_type="department",
        resource_id="1",
        username="admin",
    )
    db.add(log)
    await db.flush()

    resp = await client.get("/api/audit-logs")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


@pytest.mark.asyncio
async def test_audit_log_filters(client, db):
    from app.models.audit_log import AuditLog

    db.add(AuditLog(action="CREATE", resource_type="department", username="alice"))
    db.add(AuditLog(action="DELETE", resource_type="user", username="bob"))
    await db.flush()

    resp = await client.get("/api/audit-logs?action=CREATE")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1

    resp2 = await client.get("/api/audit-logs?resource_type=user")
    assert resp2.status_code == 200
    assert resp2.json()["total"] == 1


@pytest.mark.asyncio
async def test_audit_log_summary(client, db):
    from app.models.audit_log import AuditLog

    db.add(AuditLog(action="CREATE", resource_type="department"))
    db.add(AuditLog(action="CREATE", resource_type="user"))
    db.add(AuditLog(action="DELETE", resource_type="department"))
    await db.flush()

    resp = await client.get("/api/audit-logs/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert data["by_action"]["CREATE"] == 2
    assert data["by_action"]["DELETE"] == 1


# ===========================================================================
# Item 4 — Staff Management
# ===========================================================================


@pytest.mark.asyncio
async def test_list_users_empty(client):
    resp = await client.get("/api/users")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_create_user(client):
    resp = await client.post(
        "/api/users",
        json={
            "username": "jane",
            "password": "secret123",
            "name": "Jane Doe",
            "role": "operator",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["user"]["username"] == "jane"
    assert data["user"]["role"] == "operator"
    assert "password" not in data["user"]


@pytest.mark.asyncio
async def test_create_user_invalid_role(client):
    resp = await client.post(
        "/api/users",
        json={"username": "x", "password": "p", "name": "X", "role": "superuser"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_user_duplicate_username(client):
    payload = {"username": "dup", "password": "p", "name": "Dup", "role": "operator"}
    await client.post("/api/users", json=payload)
    resp = await client.post("/api/users", json=payload)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_get_user(client):
    resp = await client.post(
        "/api/users",
        json={"username": "bob", "password": "p", "name": "Bob", "role": "supervisor"},
    )
    uid = resp.json()["user"]["id"]
    resp2 = await client.get(f"/api/users/{uid}")
    assert resp2.status_code == 200
    assert resp2.json()["user"]["id"] == uid


@pytest.mark.asyncio
async def test_update_user_role(client):
    resp = await client.post(
        "/api/users",
        json={"username": "charlie", "password": "p", "name": "Charlie", "role": "operator"},
    )
    uid = resp.json()["user"]["id"]
    resp2 = await client.patch(f"/api/users/{uid}", json={"role": "supervisor"})
    assert resp2.status_code == 200
    assert resp2.json()["user"]["role"] == "supervisor"


@pytest.mark.asyncio
async def test_deactivate_user(client, db):
    # Create two admins so we can deactivate one
    db.add(
        DashboardUser(
            username="admin1", password_hash=hash_password("p"), name="Admin1", role="admin"
        )
    )
    db.add(
        DashboardUser(
            username="admin2", password_hash=hash_password("p"), name="Admin2", role="admin"
        )
    )
    await db.flush()

    # Get admin1 id
    resp = await client.get("/api/users?role=admin")
    uid = resp.json()["users"][0]["id"]
    resp2 = await client.delete(f"/api/users/{uid}")
    assert resp2.status_code == 204


@pytest.mark.asyncio
async def test_cannot_deactivate_last_admin(client):
    resp = await client.post(
        "/api/users",
        json={"username": "lastadmin", "password": "p", "name": "Last Admin", "role": "admin"},
    )
    uid = resp.json()["user"]["id"]
    resp2 = await client.delete(f"/api/users/{uid}")
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_list_users_by_role(client):
    await client.post(
        "/api/users",
        json={"username": "op1", "password": "p", "name": "Op1", "role": "operator"},
    )
    resp = await client.get("/api/users/by-role/operator")
    assert resp.status_code == 200
    assert len(resp.json()["users"]) >= 1


# ===========================================================================
# Item 5 — Live Call Monitor
# ===========================================================================


@pytest.mark.asyncio
async def test_live_calls_empty(client):
    resp = await client.get("/api/calls/live")
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


@pytest.mark.asyncio
async def test_live_calls_returns_active(client, db):
    c = Call(
        twilio_call_sid="CA_live_001",
        direction="inbound",
        status="in_progress",
        started_at=datetime.utcnow(),
    )
    db.add(c)
    await db.flush()

    resp = await client.get("/api/calls/live")
    assert resp.status_code == 200
    assert resp.json()["count"] == 1
    assert resp.json()["live_calls"][0]["elapsed_seconds"] is not None


@pytest.mark.asyncio
async def test_terminate_call(client, db):
    c = Call(
        twilio_call_sid="CA_term_001",
        direction="inbound",
        status="in_progress",
        started_at=datetime.utcnow(),
    )
    db.add(c)
    await db.flush()

    resp = await client.post(f"/api/calls/{c.id}/terminate")
    assert resp.status_code == 200
    assert resp.json()["terminated"] is True


@pytest.mark.asyncio
async def test_terminate_completed_call_fails(client, db):
    c = Call(
        twilio_call_sid="CA_comp_002",
        direction="inbound",
        status="completed",
        started_at=datetime.utcnow(),
    )
    db.add(c)
    await db.flush()

    resp = await client.post(f"/api/calls/{c.id}/terminate")
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_transfer_call(client, db):
    c = Call(
        twilio_call_sid="CA_xfer_001",
        direction="inbound",
        status="in_progress",
        started_at=datetime.utcnow(),
    )
    db.add(c)
    await db.flush()

    resp = await client.post(f"/api/calls/{c.id}/transfer?transfer_to=%2B15551234567")
    assert resp.status_code == 200
    assert resp.json()["transferred"] is True


# ===========================================================================
# Item 6 — Call Analytics
# ===========================================================================


@pytest.mark.asyncio
async def test_call_volume_empty(client):
    resp = await client.get("/api/analytics/calls")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_call_volume_with_data(client, db):
    now = datetime.utcnow()
    for i in range(3):
        db.add(
            Call(
                twilio_call_sid=f"CA_vol_{i}",
                direction="inbound",
                status="completed",
                started_at=now - timedelta(hours=i),
            )
        )
    await db.flush()

    resp = await client.get("/api/analytics/calls?days=30")
    assert resp.status_code == 200
    assert resp.json()["total"] == 3


@pytest.mark.asyncio
async def test_language_distribution(client, db):
    now = datetime.utcnow()
    db.add(
        Call(
            twilio_call_sid="CA_lang_en",
            direction="inbound",
            status="completed",
            detected_language="en",
            started_at=now,
        )
    )
    db.add(
        Call(
            twilio_call_sid="CA_lang_es1",
            direction="inbound",
            status="completed",
            detected_language="es",
            started_at=now,
        )
    )
    db.add(
        Call(
            twilio_call_sid="CA_lang_es2",
            direction="inbound",
            status="completed",
            detected_language="es",
            started_at=now,
        )
    )
    await db.flush()

    resp = await client.get("/api/analytics/languages?days=30")
    assert resp.status_code == 200
    data = resp.json()
    lang_map = {lg["language"]: lg["count"] for lg in data["languages"]}
    assert lang_map["es"] == 2
    assert lang_map["en"] == 1


@pytest.mark.asyncio
async def test_resolution_breakdown(client, db):
    now = datetime.utcnow()
    db.add(
        Call(
            twilio_call_sid="CA_res1",
            direction="inbound",
            status="completed",
            resolution_status="resolved",
            started_at=now,
        )
    )
    db.add(
        Call(
            twilio_call_sid="CA_res2",
            direction="inbound",
            status="completed",
            resolution_status="escalated",
            started_at=now,
        )
    )
    db.add(
        Call(
            twilio_call_sid="CA_res3",
            direction="inbound",
            status="completed",
            resolution_status="resolved",
            started_at=now,
        )
    )
    await db.flush()

    resp = await client.get("/api/analytics/resolution?days=30")
    assert resp.status_code == 200
    data = resp.json()
    assert data["resolved"] == 2
    assert data["escalated"] == 1
    assert data["total_completed"] == 3


@pytest.mark.asyncio
async def test_peak_hours(client, db):
    now = datetime.utcnow().replace(hour=14, minute=0, second=0)
    for i in range(5):
        db.add(
            Call(
                twilio_call_sid=f"CA_peak_{i}",
                direction="inbound",
                status="completed",
                started_at=now,
            )
        )
    await db.flush()

    resp = await client.get("/api/analytics/peak-hours?days=30")
    assert resp.status_code == 200
    data = resp.json()
    assert data["peak_hour"] == 14


@pytest.mark.asyncio
async def test_department_metrics(client, db):
    dept = Department(name="Public Works", code="PW")
    db.add(dept)
    await db.flush()

    now = datetime.utcnow()
    db.add(
        Call(
            twilio_call_sid="CA_dpt1",
            direction="inbound",
            status="completed",
            department_id=dept.id,
            started_at=now,
            resolution_status="resolved",
        )
    )
    await db.flush()

    resp = await client.get("/api/analytics/departments?days=30")
    assert resp.status_code == 200
    depts = resp.json()["departments"]
    pw = next((d for d in depts if d["department_id"] == dept.id), None)
    assert pw is not None
    assert pw["total_calls"] == 1


# ===========================================================================
# Item 7 — Appointment Analytics
# ===========================================================================


@pytest.mark.asyncio
async def test_appointment_analytics_empty(client):
    resp = await client.get("/api/analytics/appointments")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_appointment_analytics_with_data(client, db):
    contact = Contact(phone_number="+15550001111")
    dept = Department(name="Parks", code="PRK")
    db.add(contact)
    db.add(dept)
    await db.flush()

    now = datetime.utcnow()
    for status in ["confirmed", "cancelled", "no_show"]:
        db.add(
            Appointment(
                contact_id=contact.id,
                department_id=dept.id,
                title="Test Appt",
                status=status,
                scheduled_start=now + timedelta(days=1),
                scheduled_end=now + timedelta(days=1, hours=1),
            )
        )
    await db.flush()

    resp = await client.get("/api/analytics/appointments?days=30")
    assert resp.status_code == 200
    data = resp.json()
    assert data["confirmed"] == 1
    assert data["cancelled"] == 1
    assert data["no_show"] == 1
    assert data["no_show_rate"] == pytest.approx(33.3, abs=0.1)


@pytest.mark.asyncio
async def test_no_show_contacts(client, db):
    contact = Contact(phone_number="+15550002222")
    dept = Department(name="Licensing", code="LIC")
    db.add(contact)
    db.add(dept)
    await db.flush()

    now = datetime.utcnow()
    for i in range(3):
        db.add(
            Appointment(
                contact_id=contact.id,
                department_id=dept.id,
                title="Appt",
                status="no_show",
                scheduled_start=now - timedelta(days=i),
                scheduled_end=now - timedelta(days=i) + timedelta(hours=1),
            )
        )
    await db.flush()

    resp = await client.get("/api/analytics/no-shows?min_no_shows=2&days=90")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["flagged_contacts"]) >= 1
    flagged = next(c for c in data["flagged_contacts"] if c["contact_id"] == contact.id)
    assert flagged["no_shows"] == 3


# ===========================================================================
# Item 8 — SLA Reporting
# ===========================================================================


@pytest.mark.asyncio
async def test_sla_report_empty(client):
    resp = await client.get("/api/reports/sla")
    assert resp.status_code == 200
    assert resp.json()["overall_sla_compliance_pct"] is None


@pytest.mark.asyncio
async def test_sla_report_with_data(client, db):
    dept = Department(name="Water Dept", code="WTR")
    db.add(dept)
    await db.flush()

    now = datetime.utcnow()
    # 3 within SLA (< 300s), 1 over
    durations = [120, 180, 240, 600]
    for i, dur in enumerate(durations):
        db.add(
            Call(
                twilio_call_sid=f"CA_sla_{i}",
                direction="inbound",
                status="completed",
                department_id=dept.id,
                duration_seconds=dur,
                started_at=now,
            )
        )
    await db.flush()

    resp = await client.get("/api/reports/sla?target_handle_seconds=300&days=30")
    assert resp.status_code == 200
    data = resp.json()
    dept_row = next(d for d in data["departments"] if d["department_id"] == dept.id)
    assert dept_row["within_sla"] == 3
    assert dept_row["total_completed"] == 4
    assert dept_row["sla_compliance_pct"] == 75.0


# ===========================================================================
# Item 9 — Knowledge Base
# ===========================================================================


@pytest.mark.asyncio
async def test_list_knowledge_empty(client):
    resp = await client.get("/api/knowledge")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_create_knowledge_entry(client):
    resp = await client.post(
        "/api/knowledge",
        json={
            "question": "What are your office hours?",
            "answer": "Monday-Friday, 9am-5pm.",
            "language": "en",
            "category": "general",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["entry"]["question"] == "What are your office hours?"
    assert data["entry"]["is_active"] is True


@pytest.mark.asyncio
async def test_knowledge_search(client, db):
    db.add(
        KnowledgeEntry(question="How to get a permit?", answer="Visit city hall.", language="en")
    )
    db.add(KnowledgeEntry(question="Park hours?", answer="Dawn to dusk.", language="en"))
    await db.flush()

    resp = await client.get("/api/knowledge?search=permit")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


@pytest.mark.asyncio
async def test_update_knowledge_entry(client):
    resp = await client.post(
        "/api/knowledge",
        json={"question": "Old Q?", "answer": "Old A.", "language": "en"},
    )
    entry_id = resp.json()["entry"]["id"]

    resp2 = await client.patch(f"/api/knowledge/{entry_id}", json={"answer": "New answer!"})
    assert resp2.status_code == 200
    assert resp2.json()["entry"]["answer"] == "New answer!"


@pytest.mark.asyncio
async def test_delete_knowledge_entry(client):
    resp = await client.post(
        "/api/knowledge",
        json={"question": "Delete me?", "answer": "Yes.", "language": "en"},
    )
    entry_id = resp.json()["entry"]["id"]

    resp2 = await client.delete(f"/api/knowledge/{entry_id}")
    assert resp2.status_code == 204

    resp3 = await client.get("/api/knowledge?is_active=true")
    ids = [e["id"] for e in resp3.json()["entries"]]
    assert entry_id not in ids


@pytest.mark.asyncio
async def test_knowledge_agent_context(client, db):
    db.add(KnowledgeEntry(question="Q1?", answer="A1.", language="en", is_active=True))
    db.add(KnowledgeEntry(question="Q2?", answer="A2.", language="es", is_active=True))
    await db.flush()

    resp = await client.get("/api/knowledge/context?language=en")
    assert resp.status_code == 200
    data = resp.json()
    assert data["entry_count"] == 1
    assert "Q1?" in data["context"]


@pytest.mark.asyncio
async def test_knowledge_categories(client, db):
    db.add(KnowledgeEntry(question="Q?", answer="A.", language="en", category="permits"))
    db.add(KnowledgeEntry(question="Q?", answer="A.", language="en", category="parks"))
    await db.flush()

    resp = await client.get("/api/knowledge/categories")
    assert resp.status_code == 200
    cats = resp.json()["categories"]
    assert "permits" in cats
    assert "parks" in cats


# ===========================================================================
# Item 10 — Contact Management Enhancements
# ===========================================================================


@pytest.mark.asyncio
async def test_contact_history_empty(client):
    resp = await client.post("/api/contacts", json={"phone_number": "+15550010001"})
    contact_id = resp.json()["contact"]["id"]

    resp2 = await client.get(f"/api/contacts/{contact_id}/history")
    assert resp2.status_code == 200
    data = resp2.json()
    assert data["total_events"] == 0
    assert data["events"] == []


@pytest.mark.asyncio
async def test_contact_history_with_calls(client, db):
    contact = Contact(phone_number="+15550020002", name="Test Person")
    db.add(contact)
    await db.flush()

    db.add(
        Call(
            twilio_call_sid="CA_hist_001",
            contact_id=contact.id,
            direction="inbound",
            status="completed",
            started_at=datetime.utcnow(),
        )
    )
    await db.flush()

    resp = await client.get(f"/api/contacts/{contact.id}/history")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_events"] == 1
    assert data["events"][0]["type"] == "call"


@pytest.mark.asyncio
async def test_contact_merge(client, db):
    primary = Contact(phone_number="+15550030001", name="Alice Primary")
    duplicate = Contact(phone_number="+15550030002", name="Alice Duplicate")
    db.add(primary)
    db.add(duplicate)
    await db.flush()

    db.add(
        Call(
            twilio_call_sid="CA_merge_001",
            contact_id=duplicate.id,
            direction="inbound",
            status="completed",
            started_at=datetime.utcnow(),
        )
    )
    await db.flush()

    resp = await client.post(
        "/api/contacts/merge",
        json={
            "primary_contact_id": primary.id,
            "duplicate_contact_id": duplicate.id,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["merged"] is True
    assert resp.json()["primary_contact"]["id"] == primary.id


@pytest.mark.asyncio
async def test_contact_merge_self_fails(client, db):
    contact = Contact(phone_number="+15550040001")
    db.add(contact)
    await db.flush()

    resp = await client.post(
        "/api/contacts/merge",
        json={"primary_contact_id": contact.id, "duplicate_contact_id": contact.id},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_contact_tags(client, db):
    contact = Contact(phone_number="+15550050001")
    db.add(contact)
    await db.flush()

    resp = await client.post(
        f"/api/contacts/{contact.id}/tags",
        json={"tags": ["frequent_caller", "spanish_speaker"]},
    )
    assert resp.status_code == 200

    resp2 = await client.get(f"/api/contacts/{contact.id}/tags")
    assert resp2.status_code == 200
    tags = resp2.json()["tags"]
    assert "frequent_caller" in tags
    assert "spanish_speaker" in tags


# ===========================================================================
# Item 11 — Reminders
# ===========================================================================


@pytest.mark.asyncio
async def test_pending_reminders_empty(client):
    resp = await client.get("/api/reminders/pending")
    assert resp.status_code == 200
    assert resp.json()["pending_count"] == 0


@pytest.mark.asyncio
async def test_pending_reminders_with_appt(client, db):
    contact = Contact(phone_number="+15560001111")
    dept = Department(name="Health Dept", code="HLT")
    db.add(contact)
    db.add(dept)
    await db.flush()

    # Appt in 2 hours, no reminder sent
    db.add(
        Appointment(
            contact_id=contact.id,
            department_id=dept.id,
            title="Health Check",
            status="confirmed",
            reminder_sent=False,
            scheduled_start=datetime.utcnow() + timedelta(hours=2),
            scheduled_end=datetime.utcnow() + timedelta(hours=3),
        )
    )
    await db.flush()

    resp = await client.get("/api/reminders/pending?hours_ahead=24")
    assert resp.status_code == 200
    data = resp.json()
    assert data["pending_count"] == 1
    assert data["pending"][0]["contact_phone"] == "+15560001111"


@pytest.mark.asyncio
async def test_run_reminders_dry_run(client, db):
    contact = Contact(phone_number="+15560002222")
    dept = Department(name="Library", code="LIB")
    db.add(contact)
    db.add(dept)
    await db.flush()

    db.add(
        Appointment(
            contact_id=contact.id,
            department_id=dept.id,
            title="Library Tour",
            status="confirmed",
            reminder_sent=False,
            scheduled_start=datetime.utcnow() + timedelta(hours=3),
            scheduled_end=datetime.utcnow() + timedelta(hours=4),
        )
    )
    await db.flush()

    resp = await client.post("/api/reminders/run?hours_ahead=24&dry_run=true")
    assert resp.status_code == 200
    data = resp.json()
    assert data["dry_run"] is True
    assert data["total_found"] == 1
    assert data["sent"] == 1  # dry run still "sends"


@pytest.mark.asyncio
async def test_reminder_history(client, db):
    contact = Contact(phone_number="+15560003333")
    dept = Department(name="Finance", code="FIN")
    db.add(contact)
    db.add(dept)
    await db.flush()

    db.add(
        Appointment(
            contact_id=contact.id,
            department_id=dept.id,
            title="Tax Consult",
            status="confirmed",
            reminder_sent=True,
            scheduled_start=datetime.utcnow() + timedelta(days=1),
            scheduled_end=datetime.utcnow() + timedelta(days=1, hours=1),
        )
    )
    await db.flush()

    resp = await client.get("/api/reminders/history?days=30")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


# ===========================================================================
# Item 12 — Department Time Slots
# ===========================================================================


@pytest.mark.asyncio
async def test_list_slots_empty(client):
    resp = await client.post(
        "/api/departments",
        json={"name": "Slot Dept", "code": "SLT"},
    )
    dept_id = resp.json()["department"]["id"]

    resp2 = await client.get(f"/api/departments/{dept_id}/slots")
    assert resp2.status_code == 200
    assert resp2.json()["slots"] == []


@pytest.mark.asyncio
async def test_create_slot(client):
    resp = await client.post("/api/departments", json={"name": "Slot Dept 2", "code": "SLT2"})
    dept_id = resp.json()["department"]["id"]

    resp2 = await client.post(
        f"/api/departments/{dept_id}/slots",
        json={
            "day_of_week": 0,
            "start_time": "09:00:00",
            "end_time": "09:30:00",
            "slot_duration_minutes": 30,
            "max_concurrent": 2,
        },
    )
    assert resp2.status_code == 201
    data = resp2.json()
    assert data["slot"]["day_of_week"] == 0
    assert data["slot"]["max_concurrent"] == 2


@pytest.mark.asyncio
async def test_update_slot(client):
    resp = await client.post("/api/departments", json={"name": "Slot Dept 3", "code": "SLT3"})
    dept_id = resp.json()["department"]["id"]

    resp2 = await client.post(
        f"/api/departments/{dept_id}/slots",
        json={"day_of_week": 1, "start_time": "10:00:00", "end_time": "10:30:00"},
    )
    slot_id = resp2.json()["slot"]["id"]

    resp3 = await client.put(
        f"/api/departments/{dept_id}/slots/{slot_id}",
        json={"max_concurrent": 5},
    )
    assert resp3.status_code == 200
    assert resp3.json()["slot"]["max_concurrent"] == 5


@pytest.mark.asyncio
async def test_delete_slot(client):
    resp = await client.post("/api/departments", json={"name": "Slot Dept 4", "code": "SLT4"})
    dept_id = resp.json()["department"]["id"]

    resp2 = await client.post(
        f"/api/departments/{dept_id}/slots",
        json={"day_of_week": 2, "start_time": "14:00:00", "end_time": "14:30:00"},
    )
    slot_id = resp2.json()["slot"]["id"]

    resp3 = await client.delete(f"/api/departments/{dept_id}/slots/{slot_id}")
    assert resp3.status_code == 204


@pytest.mark.asyncio
async def test_bulk_generate_slots(client):
    resp = await client.post("/api/departments", json={"name": "Bulk Slot Dept", "code": "BLK"})
    dept_id = resp.json()["department"]["id"]

    resp2 = await client.post(
        f"/api/departments/{dept_id}/slots/bulk",
        json={
            "days_of_week": [0, 1, 2, 3, 4],
            "start_time": "09:00:00",
            "end_time": "17:00:00",
            "slot_duration_minutes": 30,
            "max_concurrent": 1,
        },
    )
    assert resp2.status_code == 201
    data = resp2.json()
    # 9am-5pm = 8 hours = 16 slots per day, 5 days = 80 slots
    assert data["created"] == 80


@pytest.mark.asyncio
async def test_slot_availability(client, db):
    dept = Department(name="Avail Dept", code="AVL")
    db.add(dept)
    await db.flush()

    # Add a Monday slot

    db.add(
        TimeSlot(
            department_id=dept.id,
            day_of_week=0,  # Monday
            start_time=time(9, 0),
            end_time=time(9, 30),
            slot_duration_minutes=30,
            max_concurrent=2,
        )
    )
    await db.flush()

    # Use a known Monday
    next_monday_str = "2026-02-23"  # Monday

    resp = await client.get(f"/api/departments/{dept.id}/slots/availability?date={next_monday_str}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["slots"]) == 1
    assert data["slots"][0]["max_concurrent"] == 2
    assert data["slots"][0]["available"] == 2
