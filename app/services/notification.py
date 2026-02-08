"""Dashboard notification service: broadcasts real-time events to connected staff."""

import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Reference to the WebSocket manager; set during app startup
_ws_manager = None


def set_ws_manager(manager):
    global _ws_manager
    _ws_manager = manager


async def broadcast_event(event: str, data: dict) -> None:
    """Broadcast an event to all connected dashboard clients."""
    if _ws_manager is None:
        return
    payload = json.dumps(
        {
            "event": event,
            "data": data,
            "timestamp": datetime.utcnow().isoformat(),
        }
    )
    await _ws_manager.broadcast(payload)


async def notify_call_started(call_data: dict) -> None:
    await broadcast_event("call.started", call_data)


async def notify_call_status_changed(call_id: int, status: str, **extra) -> None:
    await broadcast_event(
        "call.status_changed",
        {"call_id": call_id, "status": status, **extra},
    )


async def notify_call_transcript(
    call_id: int,
    role: str,
    original_text: str,
    translated_text: str | None = None,
    language: str = "en",
    intent: str | None = None,
) -> None:
    await broadcast_event(
        "call.transcript",
        {
            "call_id": call_id,
            "role": role,
            "original_text": original_text,
            "translated_text": translated_text,
            "language": language,
            "intent": intent,
        },
    )


async def notify_call_ended(
    call_id: int,
    duration_seconds: int | None = None,
    summary: str | None = None,
    sentiment: str | None = None,
) -> None:
    await broadcast_event(
        "call.ended",
        {
            "call_id": call_id,
            "duration_seconds": duration_seconds,
            "summary": summary,
            "sentiment": sentiment,
        },
    )


async def notify_appointment_created(appointment_data: dict) -> None:
    await broadcast_event("appointment.created", appointment_data)


async def notify_appointment_updated(appointment_data: dict) -> None:
    await broadcast_event("appointment.updated", appointment_data)


async def notify_sms_received(message_data: dict) -> None:
    await broadcast_event("sms.received", message_data)
