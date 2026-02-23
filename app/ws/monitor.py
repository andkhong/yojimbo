"""Live-call WebSocket monitor — broadcasts call events to admin dashboards."""

import asyncio
import json
import logging
from collections import deque
from datetime import datetime

from fastapi import WebSocket, WebSocketDisconnect

from app.ws.manager import ConnectionManager

logger = logging.getLogger(__name__)

# Separate manager for the monitor channel (decoupled from dashboard)
monitor_manager = ConnectionManager()

# Replay buffer for reconnecting clients (in-memory, process-local)
_EVENT_HISTORY_MAX = 500
_event_seq = 0
_event_history: deque[dict] = deque(maxlen=_EVENT_HISTORY_MAX)


def _next_event_id() -> int:
    global _event_seq
    _event_seq += 1
    return _event_seq


def _record_event(payload: dict) -> str:
    """Attach an incremental event_id and store in replay buffer."""
    event_id = _next_event_id()
    full_payload = {"event_id": event_id, **payload}
    _event_history.append(full_payload)
    return json.dumps(full_payload)


def _events_since(last_event_id: int) -> list[dict]:
    """Return replay events newer than last_event_id."""
    return [event for event in _event_history if event.get("event_id", 0) > last_event_id]


async def handle_monitor_ws(websocket: WebSocket) -> None:
    """Handle a live-call monitor WebSocket connection.

    Clients connecting to /ws/monitor receive:
    - call_started events (when a new call begins)
    - call_updated events (status changes, transcript turns)
    - call_ended events (when a call completes)
    - ping events every 30 seconds to keep the connection alive

    Reconnection support:
    - Clients may provide ?last_event_id=<n> to replay missed events

    Clients can also send:
    - {"action": "subscribe", "department_id": 3} — filter to one department
    - {"action": "ping"} — liveness check
    """
    await monitor_manager.connect(websocket)
    subscribed_dept: int | None = None

    # Send initial state
    await websocket.send_text(
        json.dumps(
            {
                "event": "connected",
                "data": {
                    "message": "Connected to Yojimbo live-call monitor",
                    "timestamp": datetime.utcnow().isoformat(),
                },
            }
        )
    )

    # Best-effort replay of missed events on reconnect
    last_event_raw = websocket.query_params.get("last_event_id")
    try:
        last_event_id = int(last_event_raw) if last_event_raw else 0
    except ValueError:
        last_event_id = 0

    if last_event_id > 0:
        missed = _events_since(last_event_id)
        logger.info("Monitor WS replay: %d events since id=%d", len(missed), last_event_id)
        for evt in missed:
            await websocket.send_text(json.dumps(evt))

    ping_task = asyncio.create_task(_ping_loop(websocket))

    try:
        async for raw in websocket.iter_text():
            try:
                msg = json.loads(raw)
                action = msg.get("action")

                if action == "subscribe":
                    subscribed_dept = msg.get("department_id")
                    await websocket.send_text(
                        json.dumps(
                            {
                                "event": "subscribed",
                                "data": {"department_id": subscribed_dept},
                            }
                        )
                    )

                elif action == "ping":
                    await websocket.send_text(
                        json.dumps(
                            {
                                "event": "pong",
                                "data": {"timestamp": datetime.utcnow().isoformat()},
                            }
                        )
                    )

            except json.JSONDecodeError:
                logger.warning("Monitor WS: invalid JSON from client")

    except WebSocketDisconnect:
        logger.info("Monitor WS client disconnected")
    finally:
        ping_task.cancel()
        monitor_manager.disconnect(websocket)


async def _ping_loop(websocket: WebSocket) -> None:
    """Send periodic ping frames to keep the connection alive."""
    try:
        while True:
            await asyncio.sleep(30)
            await websocket.send_text(
                json.dumps(
                    {
                        "event": "ping",
                        "data": {"timestamp": datetime.utcnow().isoformat()},
                    }
                )
            )
    except Exception:
        pass


async def broadcast_call_event(
    event: str,
    data: dict,
    department_id: int | None = None,
) -> None:
    """Broadcast a call event to all monitor subscribers.

    Called by other services (AI agent, Twilio webhooks) when call state changes.

    Args:
        event: Event name (call_started, call_updated, call_ended, transcript_turn)
        data: Event payload dict
        department_id: If set, include for client-side filtering
    """
    payload = {
        "event": event,
        "department_id": department_id,
        "data": data,
        "timestamp": datetime.utcnow().isoformat(),
    }
    wire_message = _record_event(payload)
    await monitor_manager.broadcast(wire_message)
