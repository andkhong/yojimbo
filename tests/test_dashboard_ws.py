"""Tests for dashboard websocket heartbeat/reconnect support."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import WebSocketDisconnect

from app.ws import dashboard as d
from app.ws.manager import ConnectionManager


class _FakeWebSocket:
    def __init__(self, messages: list[str], disconnect: bool = False):
        self._messages = messages
        self._disconnect = disconnect
        self.sent: list[str] = []

    async def send_text(self, payload: str):
        self.sent.append(payload)

    async def iter_text(self):
        for msg in self._messages:
            yield msg
        if self._disconnect:
            raise WebSocketDisconnect()


@pytest.mark.asyncio
async def test_dashboard_ws_handles_ping_and_invalid_json(monkeypatch):
    """Handler should respond to ping and ignore malformed payloads."""
    ws = _FakeWebSocket([
        json.dumps({"action": "ping"}),
        "{not-json}",
        json.dumps({"action": "subscribe_call", "call_id": 42}),
    ])

    async def _noop_ping_loop(_ws):
        return None

    monkeypatch.setattr(d, "_ping_loop", _noop_ping_loop)

    manager = ConnectionManager()
    manager.connect = AsyncMock()  # type: ignore[method-assign]
    manager.disconnect = MagicMock()  # type: ignore[method-assign]

    await d.handle_dashboard_ws(ws, manager)

    sent = [json.loads(p) for p in ws.sent]
    assert sent[0]["event"] == "connected"
    assert any(p.get("event") == "pong" for p in sent)


@pytest.mark.asyncio
async def test_dashboard_ws_disconnects_manager_on_socket_disconnect(monkeypatch):
    """WebSocketDisconnect should trigger manager.disconnect cleanly."""
    ws = _FakeWebSocket([json.dumps({"action": "pong"})], disconnect=True)

    async def _noop_ping_loop(_ws):
        return None

    monkeypatch.setattr(d, "_ping_loop", _noop_ping_loop)

    manager = ConnectionManager()
    manager.connect = AsyncMock()  # type: ignore[method-assign]
    manager.disconnect = MagicMock()  # type: ignore[method-assign]

    await d.handle_dashboard_ws(ws, manager)

    manager.disconnect.assert_called_once_with(ws)
