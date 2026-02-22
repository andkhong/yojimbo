"""Analytics API — call volume, language breakdown, resolution rates, SLA, appointment stats."""

import csv
import io
import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.appointment import Appointment
from app.models.call import Call
from app.models.contact import Contact
from app.models.department import Department

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

# ---------------------------------------------------------------------------
# Call Analytics
# ---------------------------------------------------------------------------


@router.get("/calls", summary="Call volume over time")
async def call_volume(
    db: AsyncSession = Depends(get_db),
    period: str = Query("day", pattern="^(day|week|month)$"),
    days: int = Query(30, ge=1, le=365),
    department_id: int | None = None,
):
    """Return call volume grouped by day/week/month for the past N days."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    query = select(Call).where(Call.started_at >= cutoff)
    if department_id:
        query = query.where(Call.department_id == department_id)

    calls = (await db.execute(query)).scalars().all()

    # Build bucket counts
    buckets: dict[str, int] = {}
    for c in calls:
        if period == "day":
            key = c.started_at.strftime("%Y-%m-%d")
        elif period == "week":
            # ISO week
            key = f"{c.started_at.isocalendar()[0]}-W{c.started_at.isocalendar()[1]:02d}"
        else:
            key = c.started_at.strftime("%Y-%m")
        buckets[key] = buckets.get(key, 0) + 1

    return {
        "period": period,
        "days": days,
        "total": sum(buckets.values()),
        "data": [{"label": k, "count": v} for k, v in sorted(buckets.items())],
    }


@router.get("/languages", summary="Caller language distribution")
async def language_distribution(
    db: AsyncSession = Depends(get_db),
    days: int = Query(30, ge=1, le=365),
    department_id: int | None = None,
):
    """Return call counts grouped by detected language for the past N days."""
    cutoff = datetime.utcnow() - timedelta(days=days)

    query = (
        select(Call.detected_language, func.count().label("count"))
        .where(Call.started_at >= cutoff, Call.detected_language.isnot(None))
        .group_by(Call.detected_language)
        .order_by(func.count().desc())
    )
    if department_id:
        query = query.where(Call.department_id == department_id)

    rows = (await db.execute(query)).all()
    total = sum(r.count for r in rows)

    return {
        "days": days,
        "total_calls_with_language": total,
        "languages": [
            {
                "language": r.detected_language,
                "count": r.count,
                "pct": round(r.count / total * 100, 1) if total else 0.0,
            }
            for r in rows
        ],
    }


@router.get("/resolution", summary="AI-resolved vs escalated vs abandoned")
async def resolution_breakdown(
    db: AsyncSession = Depends(get_db),
    days: int = Query(30, ge=1, le=365),
    department_id: int | None = None,
):
    """Return resolution status breakdown for completed calls."""
    cutoff = datetime.utcnow() - timedelta(days=days)

    base = select(
        Call.resolution_status,
        func.count().label("count"),
    ).where(
        Call.started_at >= cutoff,
        Call.status == "completed",
    )
    if department_id:
        base = base.where(Call.department_id == department_id)

    base = base.group_by(Call.resolution_status)
    rows = (await db.execute(base)).all()
    total = sum(r.count for r in rows)

    breakdown = {r.resolution_status or "unknown": r.count for r in rows}
    return {
        "days": days,
        "total_completed": total,
        "resolved": breakdown.get("resolved", 0),
        "escalated": breakdown.get("escalated", 0),
        "abandoned": breakdown.get("abandoned", 0),
        "unknown": breakdown.get("unknown", 0),
        "resolution_rate": (round(breakdown.get("resolved", 0) / total * 100, 1) if total else 0.0),
    }


@router.get("/departments", summary="Per-department call metrics")
async def department_metrics(
    db: AsyncSession = Depends(get_db),
    days: int = Query(30, ge=1, le=365),
):
    """Return call volume and resolution per active department."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    depts = (
        (await db.execute(select(Department).where(Department.is_active.is_(True)))).scalars().all()
    )

    results = []
    for dept in depts:
        total = (
            await db.execute(
                select(func.count()).where(
                    Call.department_id == dept.id,
                    Call.started_at >= cutoff,
                )
            )
        ).scalar() or 0

        resolved = (
            await db.execute(
                select(func.count()).where(
                    Call.department_id == dept.id,
                    Call.started_at >= cutoff,
                    Call.resolution_status == "resolved",
                )
            )
        ).scalar() or 0

        completed = (
            await db.execute(
                select(func.count()).where(
                    Call.department_id == dept.id,
                    Call.started_at >= cutoff,
                    Call.status == "completed",
                )
            )
        ).scalar() or 0

        resolution_rate = round(resolved / completed * 100, 1) if completed else 0.0
        results.append(
            {
                "department_id": dept.id,
                "department_name": dept.name,
                "total_calls": total,
                "resolved": resolved,
                "resolution_rate": resolution_rate,
            }
        )

    return {"days": days, "departments": results}


@router.get("/peak-hours", summary="Call volume by hour of day")
async def peak_hours(
    db: AsyncSession = Depends(get_db),
    days: int = Query(30, ge=1, le=365),
    department_id: int | None = None,
):
    """Return call volume distribution across hours of day (0-23)."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    query = select(Call).where(Call.started_at >= cutoff)
    if department_id:
        query = query.where(Call.department_id == department_id)

    calls = (await db.execute(query)).scalars().all()
    hourly: dict[int, int] = {h: 0 for h in range(24)}
    for c in calls:
        hourly[c.started_at.hour] = hourly.get(c.started_at.hour, 0) + 1

    return {
        "days": days,
        "hours": [{"hour": h, "count": hourly[h]} for h in range(24)],
        "peak_hour": max(hourly, key=lambda k: hourly[k]),
    }


# ---------------------------------------------------------------------------
# Appointment Analytics
# ---------------------------------------------------------------------------


@router.get("/appointments", summary="Appointment booking/cancellation/no-show rates")
async def appointment_analytics(
    db: AsyncSession = Depends(get_db),
    days: int = Query(30, ge=1, le=365),
    department_id: int | None = None,
):
    """Return appointment status breakdown and reminder effectiveness."""
    cutoff = datetime.utcnow() - timedelta(days=days)

    base = select(Appointment.status, func.count().label("count")).where(
        Appointment.created_at >= cutoff
    )
    if department_id:
        base = base.where(Appointment.department_id == department_id)
    base = base.group_by(Appointment.status)

    rows = (await db.execute(base)).all()
    total = sum(r.count for r in rows)
    status_map = {r.status: r.count for r in rows}

    # Reminder effectiveness
    reminder_query = (
        select(
            Appointment.reminder_sent,
            func.count().label("count"),
        )
        .where(
            Appointment.created_at >= cutoff,
            Appointment.status.in_(["confirmed", "no_show"]),
        )
        .group_by(Appointment.reminder_sent)
    )

    if department_id:
        reminder_query = reminder_query.where(Appointment.department_id == department_id)

    reminder_rows = (await db.execute(reminder_query)).all()
    reminders_sent = sum(r.count for r in reminder_rows if r.reminder_sent)
    no_reminders = sum(r.count for r in reminder_rows if not r.reminder_sent)

    return {
        "days": days,
        "total": total,
        "confirmed": status_map.get("confirmed", 0),
        "cancelled": status_map.get("cancelled", 0),
        "no_show": status_map.get("no_show", 0),
        "completed": status_map.get("completed", 0),
        "no_show_rate": (round(status_map.get("no_show", 0) / total * 100, 1) if total else 0.0),
        "reminders": {
            "sent": reminders_sent,
            "not_sent": no_reminders,
        },
    }


@router.get("/no-shows", summary="Flagged no-show contacts")
async def no_show_contacts(
    db: AsyncSession = Depends(get_db),
    min_no_shows: int = Query(2, ge=1),
    days: int = Query(90, ge=1, le=365),
):
    """Return contacts with multiple no-show appointments in the past N days."""
    cutoff = datetime.utcnow() - timedelta(days=days)

    rows = (
        await db.execute(
            select(Appointment.contact_id, func.count().label("no_shows"))
            .where(
                Appointment.status == "no_show",
                Appointment.created_at >= cutoff,
            )
            .group_by(Appointment.contact_id)
            .having(func.count() >= min_no_shows)
            .order_by(func.count().desc())
        )
    ).all()

    # Enrich with contact info
    contact_ids = [r.contact_id for r in rows]
    contacts = {
        c.id: c
        for c in (await db.execute(select(Contact).where(Contact.id.in_(contact_ids))))
        .scalars()
        .all()
    }

    return {
        "days": days,
        "min_no_shows": min_no_shows,
        "flagged_contacts": [
            {
                "contact_id": r.contact_id,
                "no_shows": r.no_shows,
                "name": contacts.get(r.contact_id, {}) and contacts[r.contact_id].name,
                "phone": contacts.get(r.contact_id, {}) and contacts[r.contact_id].phone_number,
            }
            for r in rows
        ],
    }


# ---------------------------------------------------------------------------
# SLA Reporting (Item 8)
# ---------------------------------------------------------------------------

reports_router = APIRouter(prefix="/api/reports", tags=["reports"])


@reports_router.get("/sla", summary="SLA compliance per department")
async def sla_report(
    db: AsyncSession = Depends(get_db),
    days: int = Query(30, ge=1, le=365),
    target_handle_seconds: int = Query(
        300, ge=1, description="SLA target: max handle time in seconds"
    ),
):
    """Return SLA compliance metrics per department."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    depts = (
        (await db.execute(select(Department).where(Department.is_active.is_(True)))).scalars().all()
    )

    dept_results = []
    for dept in depts:
        calls = (
            (
                await db.execute(
                    select(Call).where(
                        Call.department_id == dept.id,
                        Call.started_at >= cutoff,
                        Call.status == "completed",
                        Call.duration_seconds.isnot(None),
                    )
                )
            )
            .scalars()
            .all()
        )

        if not calls:
            dept_results.append(
                {
                    "department_id": dept.id,
                    "department_name": dept.name,
                    "total_completed": 0,
                    "within_sla": 0,
                    "sla_compliance_pct": None,
                    "avg_handle_seconds": None,
                }
            )
            continue

        within_sla = sum(1 for c in calls if (c.duration_seconds or 0) <= target_handle_seconds)
        avg_handle = round(
            sum(c.duration_seconds for c in calls if c.duration_seconds) / len(calls), 1
        )

        dept_results.append(
            {
                "department_id": dept.id,
                "department_name": dept.name,
                "total_completed": len(calls),
                "within_sla": within_sla,
                "sla_compliance_pct": round(within_sla / len(calls) * 100, 1),
                "avg_handle_seconds": avg_handle,
            }
        )

    overall_completed = sum(r["total_completed"] for r in dept_results)
    overall_within_sla = sum(r["within_sla"] for r in dept_results)

    return {
        "days": days,
        "target_handle_seconds": target_handle_seconds,
        "overall_sla_compliance_pct": (
            round(overall_within_sla / overall_completed * 100, 1) if overall_completed else None
        ),
        "departments": dept_results,
    }


# ---------------------------------------------------------------------------
# Export endpoint
# ---------------------------------------------------------------------------


@router.get("/export", summary="Export analytics snapshot as JSON or CSV")
async def export_analytics(
    db: AsyncSession = Depends(get_db),
    format: str = Query("json", pattern="^(json|csv)$"),
    days: int = Query(30, ge=1, le=365),
):
    """Export a complete analytics snapshot.

    Returns call volume + language breakdown + resolution breakdown + appointment summary.
    format=json (default) or format=csv.
    """
    cutoff = datetime.utcnow() - timedelta(days=days)

    # Call volume by day
    calls = (await db.execute(select(Call).where(Call.started_at >= cutoff))).scalars().all()

    daily: dict[str, int] = {}
    lang_counts: dict[str, int] = {}
    res_counts: dict[str, int] = {}
    for c in calls:
        day = c.started_at.strftime("%Y-%m-%d")
        daily[day] = daily.get(day, 0) + 1
        if c.detected_language:
            lang_counts[c.detected_language] = lang_counts.get(c.detected_language, 0) + 1
        if c.resolution_status:
            res_counts[c.resolution_status] = res_counts.get(c.resolution_status, 0) + 1

    # Appointments
    appts = (
        (await db.execute(select(Appointment).where(Appointment.created_at >= cutoff)))
        .scalars()
        .all()
    )
    appt_status: dict[str, int] = {}
    for a in appts:
        appt_status[a.status] = appt_status.get(a.status, 0) + 1

    payload = {
        "generated_at": datetime.utcnow().isoformat(),
        "days": days,
        "calls": {
            "total": len(calls),
            "by_day": {k: daily[k] for k in sorted(daily)},
            "by_language": lang_counts,
            "by_resolution": res_counts,
        },
        "appointments": {
            "total": len(appts),
            "by_status": appt_status,
        },
    }

    if format == "json":
        return Response(
            content=json.dumps(payload, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="analytics_{days}d.json"'},
        )

    # CSV: flatten into rows
    rows = []
    # Call volume rows
    for day, count in sorted(daily.items()):
        rows.append({"report": "call_volume", "key": day, "value": count})
    for lang, count in sorted(lang_counts.items(), key=lambda x: -x[1]):
        rows.append({"report": "language", "key": lang, "value": count})
    for res, count in sorted(res_counts.items(), key=lambda x: -x[1]):
        rows.append({"report": "resolution", "key": res, "value": count})
    for status, count in sorted(appt_status.items(), key=lambda x: -x[1]):
        rows.append({"report": "appointment_status", "key": status, "value": count})

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["report", "key", "value"])
    writer.writeheader()
    writer.writerows(rows)

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="analytics_{days}d.csv"'},
    )
