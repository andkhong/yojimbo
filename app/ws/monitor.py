"""Live-call WebSocket monitor — broadcasts call events to admin dashboards."""

import asyncio
import json
import logging
from datetime import datetime

from fastapi import WebSocket, WebSocketDisconnect

from app.ws.manager import ConnectionManager

logger = logging.getLogger(__name__)

# Separate manager for the monitor channel (decoupled from dashboard)
monitor_manager = ConnectionManager()


async def handle_monitor_ws(websocket: WebSocket) -> None:
    """Handle a live-call monitor WebSocket connection.

    Clients connecting to /ws/monitor receive:
    - call_started events (when a new call begins)
    - call_updated events (status changes, transcript turns)
    - call_ended events (when a call completes)
    - ping events every 30 seconds to keep the connection alive

    Clients can also send:
    - {"action": "subscribe", "department_id": 3} — filter to one department
    - {"action": "ping"} — liveness check
    """
    await monitor_manager.connect(websocket)
    subscribed_dept: int | None = None

    # Send initial state
    await websocket.send_text(json.dumps({
        "event": "connected",
        "data": {
            "message": "Connected to Yojimbo live-call monitor",
            "timestamp": datetime.utcnow().isoformat(),
        },
    }))

    ping_task = asyncio.create_task(_ping_loop(websocket))

    try:
        async for raw in websocket.iter_text():
            try:
                msg = json.loads(raw)
                action = msg.get("action")

                if action == "subscribe":
                    subscribed_dept = msg.get("department_id")
                    await websocket.send_text(json.dumps({
                        "event": "subscribed",
                        "data": {"department_id": subscribed_dept},
                    }))

                elif action == "ping":
                    await websocket.send_text(json.dumps({
                        "event": "pong",
                        "data": {"timestamp": datetime.utcnow().isoformat()},
                    }))

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
            await websocket.send_text(json.dumps({
                "event": "ping",
                "data": {"timestamp": datetime.utcnow().isoformat()},
            }))
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
    payload = json.dumps({
        "event": event,
        "department_id": department_id,
        "data": data,
        "timestamp": datetime.utcnow().isoformat(),
    })
    await monitor_manager.broadcast(payload)
