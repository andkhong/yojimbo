"""Dashboard WebSocket handler for real-time staff updates."""

import asyncio
import contextlib
import json
import logging

from fastapi import WebSocket, WebSocketDisconnect

from app.ws.manager import ConnectionManager

logger = logging.getLogger(__name__)


async def _ping_loop(websocket: WebSocket) -> None:
    """Send periodic ping frames so browser clients can detect stale sockets."""
    while True:
        await asyncio.sleep(20)
        await websocket.send_text(json.dumps({"event": "ping", "data": {}}))


async def handle_dashboard_ws(
    websocket: WebSocket,
    manager: ConnectionManager,
) -> None:
    """Handle a staff dashboard WebSocket connection."""
    await manager.connect(websocket)
    ping_task = asyncio.create_task(_ping_loop(websocket))

    try:
        # Send initial connection confirmation
        await websocket.send_text(
            json.dumps({"event": "connected", "data": {"message": "Dashboard connected"}})
        )

        # Keep connection alive; listen for client messages
        async for raw_message in websocket.iter_text():
            try:
                message = json.loads(raw_message)
                action = message.get("action")

                if action == "ping":
                    await websocket.send_text(json.dumps({"event": "pong", "data": {}}))
                elif action == "pong":
                    # Browser acknowledged our server-side ping. No-op for now.
                    continue
                elif action == "subscribe_call":
                    # Future: per-call subscription filtering
                    logger.info("Client subscribed to call %s", message.get("call_id"))

            except json.JSONDecodeError:
                continue

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        logger.exception("Dashboard WebSocket error")
        manager.disconnect(websocket)
    finally:
        ping_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await ping_task
