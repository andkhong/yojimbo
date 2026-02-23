"""Tests for call recording endpoints and WebSocket monitor.

Covers:
- GET /api/calls/{id}/recording — retrieve recording URL
- PUT /api/calls/{id}/recording — store recording URL
- Recording URL fetch gracefully handles missing recordings
- Monitor WebSocket connection handshake
- Monitor broadcast_call_event helper
"""

import json
from datetime import datetime

import pytest

from app.models.call import Call


# ===========================================================================
# Call recording endpoints
# ===========================================================================


@pytest.mark.asyncio
async def test_get_recording_no_url(client, db):
    """Call with no recording returns has_recording=False."""
    call = Call(
        twilio_call_sid="CA_rec_none",
        direction="inbound",
        status="completed",
        started_at=datetime.utcnow(),
        recording_url=None,
    )
    db.add(call)
    await db.flush()

    resp = await client.get(f"/api/calls/{call.id}/recording")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_recording"] is False
    assert data["recording_url"] is None


@pytest.mark.asyncio
async def test_get_recording_with_url(client, db):
    """Call with existing recording URL returns it."""
    url = "https://api.twilio.com/recordings/RE_abc123.mp3"
    call = Call(
        twilio_call_sid="CA_rec_has",
        direction="inbound",
        status="completed",
        started_at=datetime.utcnow(),
        recording_url=url,
    )
    db.add(call)
    await db.flush()

    resp = await client.get(f"/api/calls/{call.id}/recording")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_recording"] is True
    assert data["recording_url"] == url


@pytest.mark.asyncio
async def test_get_recording_nonexistent_call(client):
    """Recording for nonexistent call returns 404."""
    resp = await client.get("/api/calls/99999/recording")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_set_recording_url(client, db):
    """PUT stores the recording URL on a call."""
    call = Call(
        twilio_call_sid="CA_rec_set",
        direction="inbound",
        status="completed",
        started_at=datetime.utcnow(),
    )
    db.add(call)
    await db.flush()

    url = "https://api.twilio.com/recordings/RE_xyz.mp3"
    resp = await client.put(
        f"/api/calls/{call.id}/recording",
        params={"recording_url": url},
    )
    assert resp.status_code == 200
    assert resp.json()["recording_url"] == url

    # Verify it's retrievable
    get_resp = await client.get(f"/api/calls/{call.id}/recording")
    assert get_resp.json()["has_recording"] is True
    assert get_resp.json()["recording_url"] == url


@pytest.mark.asyncio
async def test_set_recording_url_updates_existing(client, db):
    """PUT overwrites an existing recording URL."""
    old_url = "https://api.twilio.com/recordings/RE_old.mp3"
    new_url = "https://api.twilio.com/recordings/RE_new.mp3"

    call = Call(
        twilio_call_sid="CA_rec_upd",
        direction="inbound",
        status="completed",
        started_at=datetime.utcnow(),
        recording_url=old_url,
    )
    db.add(call)
    await db.flush()

    resp = await client.put(
        f"/api/calls/{call.id}/recording",
        params={"recording_url": new_url},
    )
    assert resp.status_code == 200
    assert resp.json()["recording_url"] == new_url


@pytest.mark.asyncio
async def test_set_recording_nonexistent_call(client):
    """PUT recording for nonexistent call returns 404."""
    resp = await client.put(
        "/api/calls/99999/recording",
        params={"recording_url": "https://example.com/recording.mp3"},
    )
    assert resp.status_code == 404


# ===========================================================================
# WebSocket monitor
# ===========================================================================


@pytest.mark.asyncio
async def test_monitor_broadcast_call_event():
    """broadcast_call_event doesn't crash when no clients are connected."""
    from app.ws.monitor import broadcast_call_event

    # Should not raise even with no connected clients
    await broadcast_call_event(
        "call_started",
        {"call_id": 1, "call_sid": "CA_test", "caller_number": "+15550001111"},
    )
    await broadcast_call_event(
        "call_ended",
        {"call_id": 1, "duration_seconds": 120},
        department_id=3,
    )
    await broadcast_call_event(
        "transcript_turn",
        {"call_id": 1, "caller_text": "Hello", "agent_response": "Hi!", "turn": 1},
    )


@pytest.mark.asyncio
async def test_monitor_replay_buffer_tracks_incrementing_event_ids():
    """Monitor replay buffer stores monotonic event ids for reconnect support."""
    from app.ws import monitor as m

    baseline = m._event_seq

    first = m._record_event({"event": "call_started", "data": {"call_id": 101}})
    second = m._record_event({"event": "call_updated", "data": {"call_id": 101}})

    first_payload = json.loads(first)
    second_payload = json.loads(second)

    assert first_payload["event_id"] == baseline + 1
    assert second_payload["event_id"] == baseline + 2


@pytest.mark.asyncio
async def test_monitor_events_since_returns_only_newer_events():
    """_events_since filters replay events by event id."""
    from app.ws import monitor as m

    msg = m._record_event({"event": "call_ended", "data": {"call_id": 202}})
    payload = json.loads(msg)
    event_id = payload["event_id"]

    newer = m._events_since(event_id - 1)
    assert any(evt["event_id"] == event_id for evt in newer)

    none_newer = m._events_since(event_id)
    assert all(evt["event_id"] > event_id for evt in none_newer)


@pytest.mark.asyncio
async def test_monitor_manager_connect_disconnect():
    """ConnectionManager tracks connections."""
    from unittest.mock import AsyncMock, MagicMock

    from app.ws.manager import ConnectionManager

    manager = ConnectionManager()
    ws = MagicMock()
    ws.accept = AsyncMock()

    await manager.connect(ws)
    assert ws in manager.active_connections

    manager.disconnect(ws)
    assert ws not in manager.active_connections


@pytest.mark.asyncio
async def test_monitor_broadcast_to_multiple_clients():
    """broadcast sends to all connected clients."""
    from unittest.mock import AsyncMock, MagicMock

    from app.ws.manager import ConnectionManager

    manager = ConnectionManager()

    clients = []
    for _ in range(3):
        ws = MagicMock()
        ws.accept = AsyncMock()
        ws.send_text = AsyncMock()
        clients.append(ws)
        await manager.connect(ws)

    await manager.broadcast('{"event":"test"}')

    for ws in clients:
        ws.send_text.assert_called_once_with('{"event":"test"}')


# ===========================================================================
# Contact lookup integration (additional)
# ===========================================================================


@pytest.mark.asyncio
async def test_contact_search_limit_respected(client, db):
    """Search respects the limit parameter."""
    from app.models.contact import Contact

    for i in range(10):
        db.add(Contact(phone_number=f"+1556{i:07d}", name=f"Search Limit {i}"))
    await db.flush()

    resp = await client.get("/api/contacts/search?q=Search+Limit&limit=3")
    assert resp.status_code == 200
    assert len(resp.json()["results"]) <= 3


@pytest.mark.asyncio
async def test_contact_search_deduplicates(client, db):
    """Search doesn't return the same contact twice even if it matches multiple criteria."""
    from app.models.contact import Contact

    c = Contact(
        phone_number="+15561234567",
        name="Dedupe Test",
        email="dedup@city.gov",
        notes="dedupe notes here",
    )
    db.add(c)
    await db.flush()

    resp = await client.get("/api/contacts/search?q=Dedupe")
    assert resp.status_code == 200
    contact_ids = [r["contact"]["id"] for r in resp.json()["results"]]
    assert len(contact_ids) == len(set(contact_ids))  # no duplicates
