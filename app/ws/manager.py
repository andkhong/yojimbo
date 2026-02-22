"""WebSocket connection manager for the staff dashboard."""

import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages active WebSocket connections for the dashboard."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("Dashboard WebSocket connected (%d total)", len(self.active_connections))

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(
            "Dashboard WebSocket disconnected (%d total)",
            len(self.active_connections),
        )

    async def broadcast(self, message: str) -> None:
        """Send a message to all connected dashboard clients."""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.append(connection)

        for conn in disconnected:
            self.disconnect(conn)

    async def send_personal(self, websocket: WebSocket, message: str) -> None:
        try:
            await websocket.send_text(message)
        except Exception:
            self.disconnect(websocket)
