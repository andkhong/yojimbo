"""Tests for Government Platform Dashboard and Compliance endpoints."""

from datetime import datetime, timedelta

import pytest

from app.models.appointment import Appointment
from app.models.audit_log import AuditLog
from app.models.call import Call
from app.models.contact import Contact
from app.models.department import Department
from app.models.knowledge import KnowledgeEntry
from app.models.user import DashboardUser
from app.core.security import hash_password


@pytest.mark.asyncio
async def test_gov_summary_empty(client):
    """Government summary works with no data."""
    resp = await client.get("/api/gov/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert "calls" in data
    assert "appointments" in data
    assert "departments" in data
    assert "contacts" in data
    assert "staff" in data
    assert "knowledge_base" in data
    assert "agent_config" in data
    assert data["calls"]["total"] == 0
    assert data["calls"]["active_now"] == 0


@pytest.mark.asyncio
async def test_gov_summary_with_calls(client, db):
    """Summary includes call metrics."""
    now = datetime.utcnow()
    for i in range(3):
        db.add(
            Call(
                twilio_call_sid=f"CA_gov_{i}",
                direction="inbound",
                status="completed",
                detected_language=["en", "es", "en"][i],
                resolution_status=["resolved", "resolved", "escalated"][i],
                started_at=now - timedelta(hours=i),
            )
        )
    await db.flush()

    resp = await client.get("/api/gov/summary?days=7")
    assert resp.status_code == 200
    data = resp.json()
    assert data["calls"]["total"] == 3
    assert data["calls"]["resolved"] == 2
    assert data["calls"]["escalated"] == 1
    assert data["calls"]["resolution_rate_pct"] == pytest.approx(66.7, abs=0.1)
    # Top languages should be there
    assert len(data["calls"]["top_languages"]) >= 2


@pytest.mark.asyncio
async def test_gov_summary_with_appointments(client, db):
    """Summary includes appointment metrics."""
    contact = Contact(phone_number="+15580001111")
    dept = Department(name="Tax Office", code="TAX")
    db.add(contact)
    db.add(dept)
    await db.flush()

    now = datetime.utcnow()
    # Upcoming confirmed
    db.add(
        Appointment(
            contact_id=contact.id,
            department_id=dept.id,
            title="Tax Consult",
            status="confirmed",
            reminder_sent=False,
            scheduled_start=now + timedelta(hours=2),
            scheduled_end=now + timedelta(hours=3),
        )
    )
    # Past no-show
    db.add(
        Appointment(
            contact_id=contact.id,
            department_id=dept.id,
            title="Old Appt",
            status="no_show",
            scheduled_start=now - timedelta(days=1),
            scheduled_end=now - timedelta(days=1) + timedelta(hours=1),
        )
    )
    await db.flush()

    resp = await client.get("/api/gov/summary?days=7")
    data = resp.json()
    assert data["appointments"]["total"] == 2
    assert data["appointments"]["upcoming_confirmed"] == 1
    assert data["appointments"]["no_shows"] == 1
    assert data["appointments"]["pending_reminders_24h"] == 1


@pytest.mark.asyncio
async def test_gov_summary_staff_counts(client, db):
    """Summary includes staff breakdown by role."""
    db.add(DashboardUser(username="adm1", password_hash=hash_password("p"), name="A", role="admin"))
    db.add(
        DashboardUser(username="op1g", password_hash=hash_password("p"), name="B", role="operator")
    )
    db.add(
        DashboardUser(username="op2g", password_hash=hash_password("p"), name="C", role="operator")
    )
    await db.flush()

    resp = await client.get("/api/gov/summary")
    data = resp.json()
    assert data["staff"]["total_active"] == 3
    assert data["staff"]["by_role"]["admin"] == 1
    assert data["staff"]["by_role"]["operator"] == 2


@pytest.mark.asyncio
async def test_gov_summary_knowledge_count(client, db):
    """Summary includes knowledge base entry count."""
    db.add(KnowledgeEntry(question="Q1?", answer="A1.", language="en"))
    db.add(KnowledgeEntry(question="Q2?", answer="A2.", language="en"))
    await db.flush()

    resp = await client.get("/api/gov/summary")
    data = resp.json()
    assert data["knowledge_base"]["total_active_entries"] == 2


@pytest.mark.asyncio
async def test_gov_summary_period_filter(client, db):
    """Summary respects the days period parameter."""
    now = datetime.utcnow()
    # Old call (31 days ago)
    db.add(
        Call(
            twilio_call_sid="CA_old_gov",
            direction="inbound",
            status="completed",
            started_at=now - timedelta(days=31),
        )
    )
    # Recent call
    db.add(
        Call(
            twilio_call_sid="CA_new_gov",
            direction="inbound",
            status="completed",
            started_at=now - timedelta(days=1),
        )
    )
    await db.flush()

    resp = await client.get("/api/gov/summary?days=7")
    assert resp.json()["calls"]["total"] == 1  # Only recent

    resp2 = await client.get("/api/gov/summary?days=60")
    assert resp2.json()["calls"]["total"] == 2  # Both


# ===========================================================================
# Compliance endpoint
# ===========================================================================


@pytest.mark.asyncio
async def test_compliance_summary_empty(client):
    """Compliance summary works with no data."""
    resp = await client.get("/api/gov/compliance")
    assert resp.status_code == 200
    data = resp.json()
    assert "audit_log" in data
    assert "sla" in data
    assert "data_governance" in data
    assert data["audit_log"]["total_entries"] == 0
    assert data["sla"]["completed_calls"] == 0
    assert data["sla"]["compliance_pct"] is None


@pytest.mark.asyncio
async def test_compliance_audit_summary(client, db):
    """Compliance includes audit log breakdown."""
    db.add(AuditLog(action="CREATE", resource_type="department"))
    db.add(AuditLog(action="UPDATE", resource_type="user"))
    db.add(AuditLog(action="DELETE", resource_type="knowledge"))
    db.add(AuditLog(action="CREATE", resource_type="user"))
    await db.flush()

    resp = await client.get("/api/gov/compliance?days=30")
    data = resp.json()
    assert data["audit_log"]["total_entries"] == 4
    assert data["audit_log"]["by_action"]["CREATE"] == 2
    assert data["audit_log"]["by_action"]["DELETE"] == 1
    assert data["audit_log"]["by_resource"]["user"] == 2


@pytest.mark.asyncio
async def test_compliance_sla_metrics(client, db):
    """Compliance includes SLA compliance metrics."""
    now = datetime.utcnow()
    # 2 within SLA (< 300s), 1 over
    for dur in [100, 200, 500]:
        db.add(
            Call(
                twilio_call_sid=f"CA_comp_{dur}",
                direction="inbound",
                status="completed",
                duration_seconds=dur,
                started_at=now,
            )
        )
    await db.flush()

    resp = await client.get("/api/gov/compliance?days=30")
    data = resp.json()
    assert data["sla"]["completed_calls"] == 3
    assert data["sla"]["within_sla_300s"] == 2
    assert data["sla"]["compliance_pct"] == pytest.approx(66.7, abs=0.1)


@pytest.mark.asyncio
async def test_compliance_data_governance(client, db):
    """Compliance shows knowledge base and config counts."""
    from app.models.agent_config import AgentConfig

    db.add(KnowledgeEntry(question="Q?", answer="A.", language="en"))
    db.add(AgentConfig(key="system_prompt", value="Custom prompt"))
    await db.flush()

    resp = await client.get("/api/gov/compliance")
    data = resp.json()
    assert data["data_governance"]["knowledge_entries"] == 1
    assert data["data_governance"]["agent_config_keys"] == 1
