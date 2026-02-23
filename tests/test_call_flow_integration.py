"""Integration tests for end-to-end call flow paths.

Covers:
- Outbound call initiation (Twilio create + DB persist)
- Twilio status callback progression to completion
- Inbound voice TwiML generation for ConversationRelay
"""

from __future__ import annotations

import sys
import types

import pytest
from sqlalchemy import select

from app.models.call import Call


class _FakeCallsApi:
    def create(self, **kwargs):
        return types.SimpleNamespace(sid="CA_int_test_123")


class _FakeTwilioClient:
    def __init__(self, *args, **kwargs):
        self.calls = _FakeCallsApi()


def _install_fake_twilio(monkeypatch: pytest.MonkeyPatch) -> None:
    """Install a minimal fake twilio.rest module for tests."""
    twilio_mod = types.ModuleType("twilio")
    twilio_rest_mod = types.ModuleType("twilio.rest")
    twilio_rest_mod.Client = _FakeTwilioClient

    monkeypatch.setitem(sys.modules, "twilio", twilio_mod)
    monkeypatch.setitem(sys.modules, "twilio.rest", twilio_rest_mod)


@pytest.mark.asyncio
async def test_outbound_call_status_callback_end_to_end(client, db, monkeypatch):
    """Full outbound flow: create call, status update, completion with duration."""
    _install_fake_twilio(monkeypatch)

    create_resp = await client.post(
        "/api/calls/outbound",
        json={"phone_number": "+15551234567", "department_id": 2, "language": "en"},
    )
    assert create_resp.status_code == 201

    created = create_resp.json()["call"]
    call_id = created["id"]
    assert created["twilio_call_sid"] == "CA_int_test_123"
    assert created["status"] == "ringing"

    in_progress = await client.post(
        "/api/twilio/status",
        data={"CallSid": "CA_int_test_123", "CallStatus": "in-progress", "CallDuration": "0"},
    )
    assert in_progress.status_code == 204

    completed = await client.post(
        "/api/twilio/status",
        data={"CallSid": "CA_int_test_123", "CallStatus": "completed", "CallDuration": "87"},
    )
    assert completed.status_code == 204

    fetch_resp = await client.get(f"/api/calls/{call_id}")
    assert fetch_resp.status_code == 200
    call = fetch_resp.json()["call"]
    assert call["status"] == "completed"
    assert call["duration_seconds"] == 87

    # DB assertion for persistence
    row = (await db.execute(select(Call).where(Call.id == call_id))).scalar_one()
    assert row.status == "completed"
    assert row.duration_seconds == 87


@pytest.mark.asyncio
async def test_inbound_voice_twiml_includes_conversation_relay(client):
    """Inbound voice webhook returns TwiML with ConversationRelay and call metadata."""
    resp = await client.post(
        "/api/twilio/voice",
        data={
            "CallSid": "CA_voice_123",
            "From": "+15550001111",
            "To": "+15550002222",
            "CallStatus": "ringing",
        },
    )
    assert resp.status_code == 200
    assert "application/xml" in resp.headers.get("content-type", "")

    body = resp.text
    assert "<ConversationRelay" in body
    assert '<Parameter name="callSid" value="CA_voice_123"' in body
    assert '<Parameter name="callerNumber" value="+15550001111"' in body
    assert "/ws/conversation-relay" in body


@pytest.mark.asyncio
async def test_outbound_voice_twiml_includes_conversation_relay(client):
    """Outbound voice webhook returns TwiML wired to ConversationRelay."""
    resp = await client.post(
        "/api/twilio/voice/outbound",
        data={
            "CallSid": "CA_outbound_123",
        },
    )
    assert resp.status_code == 200
    assert "application/xml" in resp.headers.get("content-type", "")

    body = resp.text
    assert "<ConversationRelay" in body
    assert '<Parameter name="callSid" value="CA_outbound_123"' in body
    assert "Hello, this is Yojimbo calling from" in body


@pytest.mark.asyncio
async def test_status_callback_invalid_completed_duration_defaults_to_zero(client, db, monkeypatch):
    """Invalid completed duration should not 500 and should store a safe default."""
    _install_fake_twilio(monkeypatch)

    create_resp = await client.post(
        "/api/calls/outbound",
        json={"phone_number": "+15551239999", "department_id": 2, "language": "en"},
    )
    assert create_resp.status_code == 201

    call_id = create_resp.json()["call"]["id"]

    completed = await client.post(
        "/api/twilio/status",
        data={"CallSid": "CA_int_test_123", "CallStatus": "completed", "CallDuration": "NaN"},
    )
    assert completed.status_code == 204

    row = (await db.execute(select(Call).where(Call.id == call_id))).scalar_one()
    assert row.status == "completed"
    assert row.duration_seconds == 0


@pytest.mark.asyncio
async def test_status_callback_unknown_callsid_is_noop(client):
    """Unknown Twilio call SID should return 204 and not error."""
    resp = await client.post(
        "/api/twilio/status",
        data={"CallSid": "CA_does_not_exist", "CallStatus": "completed", "CallDuration": "5"},
    )
    assert resp.status_code == 204
