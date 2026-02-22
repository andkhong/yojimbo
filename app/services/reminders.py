"""Appointment reminder service: sends SMS reminders via Twilio 24h before appointments."""

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.appointment import Appointment
from app.models.contact import Contact
from app.services import notification

logger = logging.getLogger(__name__)

# Window: appointments between 23h and 25h from now are eligible
REMINDER_WINDOW_MIN_HOURS = 23
REMINDER_WINDOW_MAX_HOURS = 25


def _build_reminder_message(appointment: Appointment, contact: Contact) -> str:
    """Compose the SMS reminder body."""
    name_part = f" {contact.name}" if contact.name else ""
    scheduled = appointment.scheduled_start.strftime("%A, %B %d at %I:%M %p")
    return (
        f"Hi{name_part}! This is a reminder from {settings.office_name}. "
        f"You have an appointment — {appointment.title} — on {scheduled}. "
        f"Reply CANCEL to cancel or call us if you need to reschedule."
    )


async def send_appointment_reminder(
    appointment_id: int,
    db: AsyncSession,
) -> bool:
    """Send an SMS reminder for the given appointment.

    Loads the appointment and its contact from the database, sends an SMS via
    Twilio, marks ``reminder_sent=True`` on the appointment, and broadcasts a
    dashboard notification.

    Args:
        appointment_id: Primary key of the Appointment to remind.
        db: Async SQLAlchemy session (caller is responsible for commit).

    Returns:
        True if the SMS was sent successfully, False otherwise.

    Raises:
        ValueError: If the appointment or contact cannot be found.
    """
    # Load appointment
    result = await db.execute(
        select(Appointment).where(Appointment.id == appointment_id)
    )
    appointment = result.scalar_one_or_none()
    if appointment is None:
        raise ValueError(f"Appointment {appointment_id} not found")

    # Load contact
    result = await db.execute(
        select(Contact).where(Contact.id == appointment.contact_id)
    )
    contact = result.scalar_one_or_none()
    if contact is None:
        raise ValueError(
            f"Contact {appointment.contact_id} not found for appointment {appointment_id}"
        )

    message_body = _build_reminder_message(appointment, contact)
    success = await _send_sms(to=contact.phone_number, body=message_body)

    if success:
        appointment.reminder_sent = True
        await db.flush()
        logger.info(
            "Reminder sent for appointment %d to %s", appointment_id, contact.phone_number
        )
        # Notify connected dashboard staff
        await notification.broadcast_event(
            "reminder.sent",
            {
                "appointment_id": appointment_id,
                "contact_phone": contact.phone_number,
                "contact_name": contact.name,
                "scheduled_start": appointment.scheduled_start.isoformat(),
            },
        )
    else:
        logger.warning(
            "Failed to send reminder for appointment %d to %s",
            appointment_id,
            contact.phone_number,
        )

    return success


async def get_appointments_needing_reminders(db: AsyncSession) -> list[Appointment]:
    """Return confirmed appointments that fall in the 24h reminder window and haven't
    been reminded yet.

    The window covers appointments starting between ``REMINDER_WINDOW_MIN_HOURS`` and
    ``REMINDER_WINDOW_MAX_HOURS`` from now, giving a 2-hour scheduling tolerance for
    cron/task runners that don't fire at exact intervals.
    """
    now = datetime.utcnow()
    window_start = now + timedelta(hours=REMINDER_WINDOW_MIN_HOURS)
    window_end = now + timedelta(hours=REMINDER_WINDOW_MAX_HOURS)

    result = await db.execute(
        select(Appointment).where(
            Appointment.status == "confirmed",
            Appointment.reminder_sent.is_(False),
            Appointment.scheduled_start >= window_start,
            Appointment.scheduled_start <= window_end,
        )
    )
    return list(result.scalars().all())


async def process_due_reminders(db: AsyncSession) -> dict:
    """Find and send all reminders due in the next ~24 hours.

    Intended to be called from a scheduled task or management endpoint.

    Returns:
        A summary dict with keys ``sent``, ``failed``, and ``total``.
    """
    appointments = await get_appointments_needing_reminders(db)
    sent = 0
    failed = 0

    for appt in appointments:
        try:
            success = await send_appointment_reminder(appt.id, db)
            if success:
                sent += 1
            else:
                failed += 1
        except Exception:
            logger.exception("Error processing reminder for appointment %d", appt.id)
            failed += 1

    logger.info(
        "Reminder batch complete: %d sent, %d failed out of %d total",
        sent,
        failed,
        len(appointments),
    )
    return {"sent": sent, "failed": failed, "total": len(appointments)}


async def _send_sms(to: str, body: str) -> bool:
    """Send an SMS via Twilio. Returns True on success, False on failure.

    Uses ``settings.twilio_account_sid``, ``settings.twilio_auth_token``, and
    ``settings.twilio_phone_number``.  All credentials come from environment
    variables — never hardcoded.
    """
    if not all(
        [settings.twilio_account_sid, settings.twilio_auth_token, settings.twilio_phone_number]
    ):
        logger.warning(
            "Twilio credentials not configured — SMS not sent to %s", to
        )
        return False

    try:
        from twilio.rest import Client  # type: ignore[import]

        client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        message = client.messages.create(
            body=body,
            from_=settings.twilio_phone_number,
            to=to,
        )
        logger.debug("Twilio message SID: %s", message.sid)
        return True
    except Exception:
        logger.exception("Twilio SMS send failed to %s", to)
        return False
