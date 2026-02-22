"""Government platform summary dashboard API.

Provides a single aggregated endpoint for city administrators to get
a full operational picture: calls, appointments, SLA, staff, knowledge base.
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.agent_config import AgentConfig
from app.models.appointment import Appointment
from app.models.call import Call
from app.models.contact import Contact
from app.models.department import Department
from app.models.knowledge import KnowledgeEntry
from app.models.user import DashboardUser

router = APIRouter(prefix="/api/gov", tags=["government-dashboard"])


@router.get("/summary", summary="Government platform operational summary")
async def gov_summary(
    db: AsyncSession = Depends(get_db),
    days: int = Query(7, ge=1, le=90),
):
    """Return a comprehensive operational summary for city administrators.

    Includes: call metrics, appointment status, SLA indicators,
    staff counts, knowledge base stats, and agent config status.
    """
    now = datetime.utcnow()
    cutoff = now - timedelta(days=days)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # === CALLS ===
    total_calls = (await db.execute(
        select(func.count()).where(Call.started_at >= cutoff)
    )).scalar() or 0

    active_calls = (await db.execute(
        select(func.count()).where(Call.status.in_(["ringing", "in_progress"]))
    )).scalar() or 0

    today_calls = (await db.execute(
        select(func.count()).where(Call.started_at >= today_start)
    )).scalar() or 0

    resolved_calls = (await db.execute(
        select(func.count()).where(
            Call.started_at >= cutoff,
            Call.resolution_status == "resolved",
        )
    )).scalar() or 0

    escalated_calls = (await db.execute(
        select(func.count()).where(
            Call.started_at >= cutoff,
            Call.resolution_status == "escalated",
        )
    )).scalar() or 0

    # Language distribution
    lang_rows = (await db.execute(
        select(Call.detected_language, func.count().label("cnt"))
        .where(Call.started_at >= cutoff, Call.detected_language.isnot(None))
        .group_by(Call.detected_language)
        .order_by(func.count().desc())
        .limit(5)
    )).all()

    # === APPOINTMENTS ===
    total_appts = (await db.execute(
        select(func.count()).where(Appointment.created_at >= cutoff)
    )).scalar() or 0

    upcoming_appts = (await db.execute(
        select(func.count()).where(
            Appointment.scheduled_start >= now,
            Appointment.status == "confirmed",
        )
    )).scalar() or 0

    no_shows = (await db.execute(
        select(func.count()).where(
            Appointment.created_at >= cutoff,
            Appointment.status == "no_show",
        )
    )).scalar() or 0

    pending_reminders = (await db.execute(
        select(func.count()).where(
            Appointment.status == "confirmed",
            Appointment.reminder_sent.is_(False),
            Appointment.scheduled_start >= now,
            Appointment.scheduled_start <= now + timedelta(hours=24),
        )
    )).scalar() or 0

    # === DEPARTMENTS ===
    total_depts = (await db.execute(
        select(func.count()).where(Department.is_active.is_(True))
    )).scalar() or 0

    # === CONTACTS ===
    total_contacts = (await db.execute(
        select(func.count()).select_from(Contact)
    )).scalar() or 0

    new_contacts = (await db.execute(
        select(func.count()).where(Contact.created_at >= cutoff)
    )).scalar() or 0

    # === STAFF ===
    total_staff = (await db.execute(
        select(func.count()).where(DashboardUser.is_active.is_(True))
    )).scalar() or 0

    staff_by_role = dict((await db.execute(
        select(DashboardUser.role, func.count())
        .where(DashboardUser.is_active.is_(True))
        .group_by(DashboardUser.role)
    )).all())

    # === KNOWLEDGE BASE ===
    total_kb = (await db.execute(
        select(func.count()).where(KnowledgeEntry.is_active.is_(True))
    )).scalar() or 0

    # === AGENT CONFIG ===
    configured_keys = (await db.execute(
        select(func.count()).select_from(AgentConfig)
    )).scalar() or 0

    # Compute resolution rate
    completed = resolved_calls + escalated_calls
    resolution_rate = round(resolved_calls / completed * 100, 1) if completed else None

    return {
        "generated_at": now.isoformat(),
        "period_days": days,
        "calls": {
            "total": total_calls,
            "today": today_calls,
            "active_now": active_calls,
            "resolved": resolved_calls,
            "escalated": escalated_calls,
            "resolution_rate_pct": resolution_rate,
            "top_languages": [
                {"language": r[0], "count": r[1]} for r in lang_rows
            ],
        },
        "appointments": {
            "total": total_appts,
            "upcoming_confirmed": upcoming_appts,
            "no_shows": no_shows,
            "pending_reminders_24h": pending_reminders,
            "no_show_rate_pct": (
                round(no_shows / total_appts * 100, 1) if total_appts else None
            ),
        },
        "departments": {
            "active": total_depts,
        },
        "contacts": {
            "total": total_contacts,
            "new_in_period": new_contacts,
        },
        "staff": {
            "total_active": total_staff,
            "by_role": staff_by_role,
        },
        "knowledge_base": {
            "total_active_entries": total_kb,
        },
        "agent_config": {
            "configured_keys": configured_keys,
        },
    }


@router.get("/compliance", summary="Compliance and audit summary for government reporting")
async def compliance_summary(
    db: AsyncSession = Depends(get_db),
    days: int = Query(30, ge=1, le=365),
):
    """Return compliance-relevant metrics for government audit requirements.

    Includes: total audit log entries, action breakdown,
    SLA compliance estimate, and data governance summary.
    """
    from app.models.audit_log import AuditLog

    cutoff = datetime.utcnow() - timedelta(days=days)

    total_audit = (await db.execute(
        select(func.count()).where(AuditLog.created_at >= cutoff)
    )).scalar() or 0

    action_rows = (await db.execute(
        select(AuditLog.action, func.count().label("cnt"))
        .where(AuditLog.created_at >= cutoff)
        .group_by(AuditLog.action)
    )).all()

    resource_rows = (await db.execute(
        select(AuditLog.resource_type, func.count().label("cnt"))
        .where(AuditLog.created_at >= cutoff)
        .group_by(AuditLog.resource_type)
    )).all()

    # SLA estimate
    completed_calls = (await db.execute(
        select(func.count()).where(
            Call.started_at >= cutoff,
            Call.status == "completed",
            Call.duration_seconds.isnot(None),
        )
    )).scalar() or 0

    within_sla = (await db.execute(
        select(func.count()).where(
            Call.started_at >= cutoff,
            Call.status == "completed",
            Call.duration_seconds <= 300,
            Call.duration_seconds.isnot(None),
        )
    )).scalar() or 0

    return {
        "generated_at": datetime.utcnow().isoformat(),
        "period_days": days,
        "audit_log": {
            "total_entries": total_audit,
            "by_action": {r[0]: r[1] for r in action_rows},
            "by_resource": {r[0]: r[1] for r in resource_rows},
        },
        "sla": {
            "completed_calls": completed_calls,
            "within_sla_300s": within_sla,
            "compliance_pct": (
                round(within_sla / completed_calls * 100, 1) if completed_calls else None
            ),
        },
        "data_governance": {
            "knowledge_entries": (await db.execute(
                select(func.count()).select_from(KnowledgeEntry)
            )).scalar() or 0,
            "agent_config_keys": (await db.execute(
                select(func.count()).select_from(AgentConfig)
            )).scalar() or 0,
        },
    }
