"""Tier 3 tests — health checks, export, edge cases, and additional coverage.

Covers:
- Health check endpoints (Item: infrastructure)
- Analytics export (JSON + CSV)
- Edge cases: pagination, 404s, duplicate prevention
- Audit log entries created by middleware
- Knowledge base restore endpoint
- Contact tag edge cases
- Reminder edge cases (past appointments not returned)
- Department slot availability
- User activation/deactivation lifecycle
"""

from datetime import datetime, timedelta

import pytest

from app.models.appointment import Appointment
from app.models.call import Call
from app.models.contact import Contact
from app.models.department import Department
from app.models.knowledge import KnowledgeEntry
from app.models.user import DashboardUser
from app.core.security import hash_password


# ===========================================================================
# Health Checks
# ===========================================================================


@pytest.mark.asyncio
async def test_health_basic(client):
    """Basic health endpoint returns ok."""
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "timestamp" in data
    assert data["service"] == "yojimbo"


@pytest.mark.asyncio
async def test_health_db(client):
    """DB health returns ok with latency."""
    resp = await client.get("/api/health/db")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "db_latency_ms" in data
    assert data["db_latency_ms"] >= 0


@pytest.mark.asyncio
async def test_health_full(client):
    """Full health returns ok status dict."""
    resp = await client.get("/api/health/full")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "checks" in data
    assert "database" in data["checks"]
    assert data["checks"]["database"]["status"] == "ok"


@pytest.mark.asyncio
async def test_health_twilio_does_not_crash(client):
    """Twilio health endpoint returns without crashing (may be unavailable)."""
    resp = await client.get("/api/health/twilio")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("ok", "unavailable")


# ===========================================================================
# Analytics Export
# ===========================================================================


@pytest.mark.asyncio
async def test_export_json_empty(client):
    """Export endpoint returns valid JSON structure with no data."""
    resp = await client.get("/api/analytics/export?format=json&days=30")
    assert resp.status_code == 200
    assert "application/json" in resp.headers["content-type"]
    data = resp.json()
    assert "calls" in data
    assert "appointments" in data
    assert data["calls"]["total"] == 0


@pytest.mark.asyncio
async def test_export_csv_empty(client):
    """Export endpoint returns valid CSV with no data."""
    resp = await client.get("/api/analytics/export?format=csv&days=30")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "report,key,value" in resp.text


@pytest.mark.asyncio
async def test_export_json_with_data(client, db):
    """Export includes call data correctly."""
    now = datetime.utcnow()
    db.add(Call(twilio_call_sid="CA_exp1", direction="inbound", status="completed",
                detected_language="en", resolution_status="resolved", started_at=now))
    db.add(Call(twilio_call_sid="CA_exp2", direction="inbound", status="completed",
                detected_language="es", resolution_status="escalated", started_at=now))
    await db.flush()

    resp = await client.get("/api/analytics/export?format=json&days=30")
    assert resp.status_code == 200
    data = resp.json()
    assert data["calls"]["total"] == 2
    assert data["calls"]["by_language"]["en"] == 1
    assert data["calls"]["by_language"]["es"] == 1
    assert data["calls"]["by_resolution"]["resolved"] == 1


@pytest.mark.asyncio
async def test_export_csv_with_data(client, db):
    """Export CSV contains all rows for data."""
    now = datetime.utcnow()
    db.add(Call(twilio_call_sid="CA_csv1", direction="inbound", status="completed",
                detected_language="en", started_at=now))
    await db.flush()

    resp = await client.get("/api/analytics/export?format=csv&days=30")
    assert resp.status_code == 200
    # Should contain at least the language row
    assert "language,en,1" in resp.text


@pytest.mark.asyncio
async def test_export_invalid_format(client):
    """Export with invalid format returns 422."""
    resp = await client.get("/api/analytics/export?format=xml&days=30")
    assert resp.status_code == 422


# ===========================================================================
# Edge cases: pagination + filtering
# ===========================================================================


@pytest.mark.asyncio
async def test_calls_pagination(client, db):
    """Calls list respects per_page limit."""
    now = datetime.utcnow()
    for i in range(10):
        db.add(Call(
            twilio_call_sid=f"CA_page_{i:03d}",
            direction="inbound",
            status="completed",
            started_at=now - timedelta(minutes=i),
        ))
    await db.flush()

    resp = await client.get("/api/calls?per_page=3&page=1")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["calls"]) == 3
    assert data["total"] == 10

    resp2 = await client.get("/api/calls?per_page=3&page=2")
    assert len(resp2.json()["calls"]) == 3


@pytest.mark.asyncio
async def test_contacts_pagination(client, db):
    """Contacts list respects per_page."""
    for i in range(5):
        db.add(Contact(phone_number=f"+1555{i:07d}"))
    await db.flush()

    resp = await client.get("/api/contacts?per_page=2&page=1")
    assert resp.status_code == 200
    assert len(resp.json()["contacts"]) == 2


@pytest.mark.asyncio
async def test_users_pagination(client, db):
    """Users list respects per_page and page params."""
    for i in range(6):
        db.add(DashboardUser(
            username=f"page_user_{i}",
            password_hash=hash_password("pw"),
            name=f"User {i}",
            role="operator",
        ))
    await db.flush()

    resp = await client.get("/api/users?per_page=3&page=1")
    assert resp.status_code == 200
    assert len(resp.json()["users"]) == 3
    assert resp.json()["total"] == 6


@pytest.mark.asyncio
async def test_knowledge_pagination(client, db):
    """Knowledge list respects per_page."""
    for i in range(5):
        db.add(KnowledgeEntry(question=f"Q{i}?", answer=f"A{i}.", language="en"))
    await db.flush()

    resp = await client.get("/api/knowledge?per_page=2&page=1")
    assert resp.status_code == 200
    assert len(resp.json()["entries"]) == 2


@pytest.mark.asyncio
async def test_audit_logs_pagination(client, db):
    """Audit logs respect per_page."""
    from app.models.audit_log import AuditLog
    for i in range(10):
        db.add(AuditLog(action="CREATE", resource_type="department", resource_id=str(i)))
    await db.flush()

    resp = await client.get("/api/audit-logs?per_page=4&page=1")
    assert resp.status_code == 200
    assert len(resp.json()["logs"]) == 4
    assert resp.json()["total"] == 10


# ===========================================================================
# Edge cases: 404s and not-found scenarios
# ===========================================================================


@pytest.mark.asyncio
async def test_get_nonexistent_user(client):
    resp = await client.get("/api/users/99999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_nonexistent_user(client):
    resp = await client.patch("/api/users/99999", json={"name": "Nobody"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_deactivate_nonexistent_user(client):
    resp = await client.delete("/api/users/99999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_nonexistent_knowledge(client):
    resp = await client.get("/api/knowledge/99999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_nonexistent_config_key(client):
    resp = await client.get("/api/config/agent/__bad_key__")
    assert resp.status_code == 400  # invalid key, not 404


@pytest.mark.asyncio
async def test_terminate_nonexistent_call(client):
    resp = await client.post("/api/calls/99999/terminate")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_merge_nonexistent_primary(client, db):
    c = Contact(phone_number="+15590001111")
    db.add(c)
    await db.flush()
    resp = await client.post(
        "/api/contacts/merge",
        json={"primary_contact_id": 99999, "duplicate_contact_id": c.id},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_nonexistent_audit_log(client):
    resp = await client.get("/api/audit-logs/99999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_slots_for_nonexistent_department(client):
    resp = await client.get("/api/departments/99999/slots")
    assert resp.status_code == 404


# ===========================================================================
# Agent Config edge cases
# ===========================================================================


@pytest.mark.asyncio
async def test_agent_config_update_is_idempotent(client):
    """Updating the same key twice keeps the latest value."""
    await client.put("/api/config/agent", json={"updates": {"max_turns": "5"}})
    resp = await client.put("/api/config/agent", json={"updates": {"max_turns": "10"}})
    assert resp.status_code == 200
    assert resp.json()["config"]["max_turns"] == "10"


@pytest.mark.asyncio
async def test_language_config_endpoints(client):
    """Language config GET/PUT work correctly."""
    resp = await client.get("/api/config/languages")
    assert resp.status_code == 200

    resp2 = await client.put(
        "/api/config/languages?supported_languages=en,es,zh&language_detection_enabled=true"
    )
    assert resp2.status_code == 200
    assert "supported_languages" in resp2.json()["updated"]


@pytest.mark.asyncio
async def test_twilio_config_endpoint(client):
    """Twilio config GET works."""
    resp = await client.get("/api/config/twilio")
    assert resp.status_code == 200


# ===========================================================================
# Knowledge restore
# ===========================================================================


@pytest.mark.asyncio
async def test_restore_knowledge_entry(client):
    """Deleted entry can be restored."""
    resp = await client.post(
        "/api/knowledge",
        json={"question": "Restore me?", "answer": "Yes!", "language": "en"},
    )
    entry_id = resp.json()["entry"]["id"]

    await client.delete(f"/api/knowledge/{entry_id}")
    resp2 = await client.post(f"/api/knowledge/{entry_id}/restore")
    assert resp2.status_code == 200
    assert resp2.json()["entry"]["is_active"] is True


# ===========================================================================
# Reminder edge cases
# ===========================================================================


@pytest.mark.asyncio
async def test_past_appointments_not_in_pending(client, db):
    """Past confirmed appointments don't show in pending reminders."""
    contact = Contact(phone_number="+15590010001")
    dept = Department(name="Archives", code="ARC")
    db.add(contact)
    db.add(dept)
    await db.flush()

    # Appointment in the past (2 days ago)
    db.add(Appointment(
        contact_id=contact.id,
        department_id=dept.id,
        title="Past Appt",
        status="confirmed",
        reminder_sent=False,
        scheduled_start=datetime.utcnow() - timedelta(days=2),
        scheduled_end=datetime.utcnow() - timedelta(days=2) + timedelta(hours=1),
    ))
    await db.flush()

    resp = await client.get("/api/reminders/pending?hours_ahead=24")
    assert resp.status_code == 200
    # Past appointments should NOT appear
    assert resp.json()["pending_count"] == 0


@pytest.mark.asyncio
async def test_already_reminded_not_in_pending(client, db):
    """Appointments that already had reminders sent don't show in pending."""
    contact = Contact(phone_number="+15590020001")
    dept = Department(name="Courts", code="CRT")
    db.add(contact)
    db.add(dept)
    await db.flush()

    db.add(Appointment(
        contact_id=contact.id,
        department_id=dept.id,
        title="Already Reminded",
        status="confirmed",
        reminder_sent=True,  # Already sent!
        scheduled_start=datetime.utcnow() + timedelta(hours=2),
        scheduled_end=datetime.utcnow() + timedelta(hours=3),
    ))
    await db.flush()

    resp = await client.get("/api/reminders/pending?hours_ahead=24")
    assert resp.json()["pending_count"] == 0


# ===========================================================================
# Contact history edge cases
# ===========================================================================


@pytest.mark.asyncio
async def test_contact_history_pagination(client, db):
    """Contact history respects pagination."""
    contact = Contact(phone_number="+15590030001", name="Paging Test")
    db.add(contact)
    await db.flush()

    # Add 5 calls
    now = datetime.utcnow()
    for i in range(5):
        db.add(Call(
            twilio_call_sid=f"CA_hpg_{i}",
            contact_id=contact.id,
            direction="inbound",
            status="completed",
            started_at=now - timedelta(minutes=i),
        ))
    await db.flush()

    resp = await client.get(f"/api/contacts/{contact.id}/history?per_page=2&page=1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_events"] == 5
    assert len(data["events"]) == 2
    assert data["page"] == 1


# ===========================================================================
# Department CRUD edge cases
# ===========================================================================


@pytest.mark.asyncio
async def test_department_duplicate_code_fails(client):
    """Creating two departments with same code fails."""
    await client.post("/api/departments", json={"name": "Dept Alpha", "code": "ALPHA"})
    resp = await client.post("/api/departments", json={"name": "Dept Beta", "code": "ALPHA"})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_department_stats_404(client):
    """Stats for nonexistent department returns 404."""
    resp = await client.get("/api/departments/99999/stats")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_department_phone_number_conflict(client):
    """Same phone number can't be assigned to two departments."""
    resp1 = await client.post("/api/departments", json={"name": "D One", "code": "D1"})
    resp2 = await client.post("/api/departments", json={"name": "D Two", "code": "D2"})
    d1_id = resp1.json()["department"]["id"]
    d2_id = resp2.json()["department"]["id"]

    await client.post(f"/api/departments/{d1_id}/phone-number", json={"phone_number": "+15555000001"})
    resp = await client.post(f"/api/departments/{d2_id}/phone-number", json={"phone_number": "+15555000001"})
    assert resp.status_code == 409


# ===========================================================================
# Live call edge cases
# ===========================================================================


@pytest.mark.asyncio
async def test_transfer_nonexistent_call(client):
    resp = await client.post("/api/calls/99999/transfer?transfer_to=%2B15551234567")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_transfer_completed_call_fails(client, db):
    c = Call(
        twilio_call_sid="CA_comp_xfer",
        direction="inbound",
        status="completed",
        started_at=datetime.utcnow(),
    )
    db.add(c)
    await db.flush()

    resp = await client.post(f"/api/calls/{c.id}/transfer?transfer_to=%2B15551234567")
    assert resp.status_code == 409


# ===========================================================================
# Analytics edge cases
# ===========================================================================


@pytest.mark.asyncio
async def test_analytics_by_week_period(client, db):
    """Call volume endpoint supports 'week' period grouping."""
    now = datetime.utcnow()
    db.add(Call(twilio_call_sid="CA_wk1", direction="inbound", status="completed", started_at=now))
    await db.flush()

    resp = await client.get("/api/analytics/calls?period=week&days=30")
    assert resp.status_code == 200
    assert resp.json()["period"] == "week"


@pytest.mark.asyncio
async def test_analytics_by_month_period(client, db):
    """Call volume endpoint supports 'month' period grouping."""
    now = datetime.utcnow()
    db.add(Call(twilio_call_sid="CA_mo1", direction="inbound", status="completed", started_at=now))
    await db.flush()

    resp = await client.get("/api/analytics/calls?period=month&days=90")
    assert resp.status_code == 200
    assert resp.json()["period"] == "month"


@pytest.mark.asyncio
async def test_analytics_invalid_period(client):
    """Invalid period value returns 422."""
    resp = await client.get("/api/analytics/calls?period=quarterly")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_analytics_department_filter(client, db):
    """Analytics endpoints accept department_id filter."""
    dept = Department(name="Roads", code="RDS")
    db.add(dept)
    await db.flush()

    now = datetime.utcnow()
    db.add(Call(twilio_call_sid="CA_dept_flt", direction="inbound", status="completed",
                department_id=dept.id, started_at=now))
    db.add(Call(twilio_call_sid="CA_other_flt", direction="inbound", status="completed",
                department_id=None, started_at=now))
    await db.flush()

    resp = await client.get(f"/api/analytics/calls?department_id={dept.id}&days=30")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


# ===========================================================================
# SLA edge cases
# ===========================================================================


@pytest.mark.asyncio
async def test_sla_excludes_in_progress_calls(client, db):
    """SLA only counts 'completed' calls, not in-progress."""
    dept = Department(name="Permits", code="PRM")
    db.add(dept)
    await db.flush()

    now = datetime.utcnow()
    # In-progress should NOT count
    db.add(Call(twilio_call_sid="CA_sla_ip", direction="inbound", status="in_progress",
                department_id=dept.id, duration_seconds=120, started_at=now))
    await db.flush()

    resp = await client.get("/api/reports/sla?days=30")
    assert resp.status_code == 200
    dept_row = next(
        (d for d in resp.json()["departments"] if d["department_id"] == dept.id), None
    )
    assert dept_row is not None
    assert dept_row["total_completed"] == 0


# ===========================================================================
# User role filtering
# ===========================================================================


@pytest.mark.asyncio
async def test_user_filter_by_role(client, db):
    """Users can be filtered by role parameter."""
    db.add(DashboardUser(username="sup1", password_hash=hash_password("p"), name="Sup 1", role="supervisor"))
    db.add(DashboardUser(username="op1b", password_hash=hash_password("p"), name="Op 1b", role="operator"))
    await db.flush()

    resp = await client.get("/api/users?role=supervisor")
    assert resp.status_code == 200
    users = resp.json()["users"]
    assert all(u["role"] == "supervisor" for u in users)


@pytest.mark.asyncio
async def test_user_activate_already_active(client, db):
    """Activating an already-active user is idempotent."""
    db.add(DashboardUser(username="active_u", password_hash=hash_password("p"), name="Active", role="operator", is_active=True))
    await db.flush()
    resp = await client.get("/api/users?role=operator")
    uid = resp.json()["users"][-1]["id"]

    resp2 = await client.post(f"/api/users/{uid}/activate")
    assert resp2.status_code == 200
    assert resp2.json()["user"]["is_active"] is True


# ===========================================================================
# Bulk slot edge cases
# ===========================================================================


@pytest.mark.asyncio
async def test_bulk_slots_replace_existing(client, db):
    """Bulk generation with replace_existing=True deactivates old slots."""
    dept = Department(name="Sanitation", code="SAN")
    db.add(dept)
    await db.flush()

    # First generation
    await client.post(
        f"/api/departments/{dept.id}/slots/bulk",
        json={
            "days_of_week": [0],
            "start_time": "09:00:00",
            "end_time": "10:00:00",
            "slot_duration_minutes": 30,
        },
    )

    # Second generation with replace
    resp = await client.post(
        f"/api/departments/{dept.id}/slots/bulk",
        json={
            "days_of_week": [0],
            "start_time": "09:00:00",
            "end_time": "10:00:00",
            "slot_duration_minutes": 60,
            "replace_existing": True,
        },
    )
    assert resp.status_code == 201
    # Should have 1 new slot (60-min slots in 1-hour window)
    assert resp.json()["created"] == 1

    # Active slots should only be the new ones
    resp2 = await client.get(f"/api/departments/{dept.id}/slots")
    assert resp2.status_code == 200
    slots = resp2.json()["slots"]
    assert all(s["slot_duration_minutes"] == 60 for s in slots)


@pytest.mark.asyncio
async def test_bulk_slots_invalid_day(client, db):
    """Bulk generation with day_of_week > 6 fails."""
    dept = Department(name="Transit", code="TRN")
    db.add(dept)
    await db.flush()

    resp = await client.post(
        f"/api/departments/{dept.id}/slots/bulk",
        json={
            "days_of_week": [7],  # invalid
            "start_time": "09:00:00",
            "end_time": "10:00:00",
            "slot_duration_minutes": 30,
        },
    )
    assert resp.status_code == 422
