"""Scheduled Reminder API — manual trigger, pending list, send history."""

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.appointment import Appointment
from app.models.contact import Contact

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/reminders", tags=["reminders"])


@router.get("/pending", summary="List upcoming reminders due in next 24 hours")
async def list_pending_reminders(
    db: AsyncSession = Depends(get_db),
    hours_ahead: int = Query(24, ge=1, le=168),
):
    """Return confirmed appointments in the next N hours that haven't had a reminder sent."""
    now = datetime.utcnow()
    cutoff = now + timedelta(hours=hours_ahead)

    appts = (
        (
            await db.execute(
                select(Appointment)
                .where(
                    Appointment.status == "confirmed",
                    Appointment.reminder_sent.is_(False),
                    Appointment.scheduled_start >= now,
                    Appointment.scheduled_start <= cutoff,
                )
                .order_by(Appointment.scheduled_start)
            )
        )
        .scalars()
        .all()
    )

    # Enrich with contact info
    contact_ids = list({a.contact_id for a in appts})
    contacts = {
        c.id: c
        for c in (await db.execute(select(Contact).where(Contact.id.in_(contact_ids))))
        .scalars()
        .all()
    }

    pending = []
    for a in appts:
        contact = contacts.get(a.contact_id)
        pending.append(
            {
                "appointment_id": a.id,
                "title": a.title,
                "scheduled_start": a.scheduled_start.isoformat(),
                "language": a.language,
                "contact_id": a.contact_id,
                "contact_name": contact.name if contact else None,
                "contact_phone": contact.phone_number if contact else None,
                "hours_until": round((a.scheduled_start - now).total_seconds() / 3600, 1),
            }
        )

    return {
        "hours_ahead": hours_ahead,
        "pending_count": len(pending),
        "pending": pending,
    }


@router.get("/history", summary="Sent/failed reminder history")
async def reminder_history(
    db: AsyncSession = Depends(get_db),
    days: int = Query(30, ge=1, le=365),
    department_id: int | None = None,
):
    """Return appointments where reminders were already sent (last N days)."""
    cutoff = datetime.utcnow() - timedelta(days=days)

    query = (
        select(Appointment)
        .where(
            Appointment.reminder_sent.is_(True),
            Appointment.created_at >= cutoff,
        )
        .order_by(Appointment.scheduled_start.desc())
    )

    if department_id:
        query = query.where(Appointment.department_id == department_id)

    appts = (await db.execute(query)).scalars().all()

    contact_ids = list({a.contact_id for a in appts})
    contacts = {
        c.id: c
        for c in (await db.execute(select(Contact).where(Contact.id.in_(contact_ids))))
        .scalars()
        .all()
    }

    return {
        "days": days,
        "total": len(appts),
        "reminders": [
            {
                "appointment_id": a.id,
                "title": a.title,
                "status": a.status,
                "scheduled_start": a.scheduled_start.isoformat(),
                "contact_id": a.contact_id,
                "contact_name": contacts.get(a.contact_id, None) and contacts[a.contact_id].name,
                "contact_phone": contacts.get(a.contact_id, None)
                and contacts[a.contact_id].phone_number,
            }
            for a in appts
        ],
    }


@router.post("/run", summary="Manually trigger batch reminder processing")
async def run_reminders(
    db: AsyncSession = Depends(get_db),
    hours_ahead: int = Query(24, ge=1, le=168),
    dry_run: bool = Query(False, description="If true, simulate without sending"),
):
    """Trigger batch SMS/voice reminders for upcoming appointments.

    Finds all confirmed, unreminded appointments in the next N hours,
    sends SMS reminders via Twilio, and marks `reminder_sent=True`.
    """
    now = datetime.utcnow()
    cutoff = now + timedelta(hours=hours_ahead)

    appts = (
        (
            await db.execute(
                select(Appointment).where(
                    Appointment.status == "confirmed",
                    Appointment.reminder_sent.is_(False),
                    Appointment.scheduled_start >= now,
                    Appointment.scheduled_start <= cutoff,
                )
            )
        )
        .scalars()
        .all()
    )

    contact_ids = list({a.contact_id for a in appts})
    contacts = {
        c.id: c
        for c in (await db.execute(select(Contact).where(Contact.id.in_(contact_ids))))
        .scalars()
        .all()
    }

    sent = []
    failed = []

    for appt in appts:
        contact = contacts.get(appt.contact_id)
        if not contact:
            failed.append({"appointment_id": appt.id, "reason": "contact not found"})
            continue

        msg_body = (
            f"Reminder: You have an appointment '{appt.title}' scheduled for "
            f"{appt.scheduled_start.strftime('%B %d at %I:%M %p')}. "
            "Reply CANCEL to cancel."
        )

        if not dry_run:
            try:
                from app.config import settings
                from twilio.rest import Client

                client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
                client.messages.create(
                    to=contact.phone_number,
                    from_=settings.twilio_phone_number,
                    body=msg_body,
                )
                appt.reminder_sent = True
                sent.append(
                    {
                        "appointment_id": appt.id,
                        "contact_phone": contact.phone_number,
                        "message": msg_body,
                    }
                )
            except Exception as exc:
                logger.warning("Reminder send failed for appt %d: %s", appt.id, exc)
                failed.append({"appointment_id": appt.id, "reason": str(exc)})
        else:
            sent.append(
                {
                    "appointment_id": appt.id,
                    "contact_phone": contact.phone_number,
                    "message": msg_body,
                    "dry_run": True,
                }
            )

    if not dry_run:
        await db.flush()

    return {
        "dry_run": dry_run,
        "hours_ahead": hours_ahead,
        "total_found": len(appts),
        "sent": len(sent),
        "failed": len(failed),
        "results": sent,
        "errors": failed,
    }
