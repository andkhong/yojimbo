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

from app.config import settings
from app.models.call import Call
from app.models.caller_preference import CallerPreference


class _FakeCallsApi:
    def create(self, **kwargs):
        return types.SimpleNamespace(sid="CA_int_test_123")


class _FailingCallsApi:
    def create(self, **kwargs):
        raise RuntimeError("twilio outage")


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


def _install_failing_twilio(monkeypatch: pytest.MonkeyPatch) -> None:
    """Install fake twilio.rest module whose call creation always fails."""

    class _FailingTwilioClient:
        def __init__(self, *args, **kwargs):
            self.calls = _FailingCallsApi()

    twilio_mod = types.ModuleType("twilio")
    twilio_rest_mod = types.ModuleType("twilio.rest")
    twilio_rest_mod.Client = _FailingTwilioClient

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
async def test_outbound_call_create_failure_is_i18n_ready(client, monkeypatch):
    """Twilio failures during outbound create return structured i18n error payloads."""
    _install_failing_twilio(monkeypatch)

    resp = await client.post(
        "/api/calls/outbound",
        json={"phone_number": "+15551230000", "department_id": 2, "language": "en"},
    )

    assert resp.status_code == 502
    detail = resp.json()["detail"]
    assert detail["message_key"] == "calls.outbound.failed"
    assert detail["message"] == "Failed to initiate outbound call"
    assert detail["params"]["reason"] == "twilio outage"


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


@pytest.mark.asyncio
async def test_status_callback_unknown_status_is_stored_raw(client, db, monkeypatch):
    """Unmapped status values should persist as-is for forward compatibility."""
    _install_fake_twilio(monkeypatch)

    create_resp = await client.post(
        "/api/calls/outbound",
        json={"phone_number": "+15557770000", "department_id": 2, "language": "en"},
    )
    assert create_resp.status_code == 201
    call_id = create_resp.json()["call"]["id"]

    resp = await client.post(
        "/api/twilio/status",
        data={
            "CallSid": "CA_int_test_123",
            "CallStatus": "queued-custom",
            "CallDuration": "not-an-int",
        },
    )
    assert resp.status_code == 204

    row = (await db.execute(select(Call).where(Call.id == call_id))).scalar_one()
    assert row.status == "queued-custom"
    # Duration parsing only happens for completed calls; invalid value should be ignored.
    assert row.duration_seconds in (None, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("twilio_status", "expected_status"),
    [
        ("busy", "busy"),
        ("no-answer", "no_answer"),
        ("canceled", "cancelled"),
        ("failed", "failed"),
        ("in-progress", "in_progress"),
    ],
)
async def test_status_callback_known_twilio_statuses_are_normalized(
    client, db, monkeypatch, twilio_status, expected_status
):
    """Known Twilio statuses should be normalized to API status values."""
    _install_fake_twilio(monkeypatch)

    create_resp = await client.post(
        "/api/calls/outbound",
        json={"phone_number": "+15558880000", "department_id": 2, "language": "en"},
    )
    assert create_resp.status_code == 201
    call_id = create_resp.json()["call"]["id"]

    resp = await client.post(
        "/api/twilio/status",
        data={"CallSid": "CA_int_test_123", "CallStatus": twilio_status, "CallDuration": "7"},
    )
    assert resp.status_code == 204

    row = (await db.execute(select(Call).where(Call.id == call_id))).scalar_one()
    assert row.status == expected_status


@pytest.mark.asyncio
async def test_inbound_voice_uses_wss_when_base_url_is_https(client, monkeypatch):
    """Inbound voice TwiML should use secure WebSocket when base URL is HTTPS."""
    monkeypatch.setattr(settings, "base_url", "https://example.gov")

    resp = await client.post(
        "/api/twilio/voice",
        data={"CallSid": "CA_https_123", "From": "+15550111111"},
    )
    assert resp.status_code == 200
    assert 'url="wss://example.gov/ws/conversation-relay"' in resp.text


@pytest.mark.asyncio
async def test_outbound_voice_uses_wss_when_base_url_is_https(client, monkeypatch):
    """Outbound voice TwiML should use secure WebSocket when base URL is HTTPS."""
    monkeypatch.setattr(settings, "base_url", "https://example.gov")

    resp = await client.post(
        "/api/twilio/voice/outbound",
        data={"CallSid": "CA_https_out_123"},
    )
    assert resp.status_code == 200
    assert 'url="wss://example.gov/ws/conversation-relay"' in resp.text


@pytest.mark.asyncio
async def test_inbound_voice_webhook_is_stateless_until_relay_setup(client, db):
    """Inbound voice TwiML generation should not persist calls by itself."""
    voice_resp = await client.post(
        "/api/twilio/voice",
        data={
            "CallSid": "CA_inbound_full_001",
            "From": "+15553334444",
            "To": "+15550002222",
            "CallStatus": "ringing",
        },
    )
    assert voice_resp.status_code == 200

    rows = (
        (await db.execute(select(Call).where(Call.twilio_call_sid == "CA_inbound_full_001")))
        .scalars()
        .all()
    )
    assert rows == []

    complete_resp = await client.post(
        "/api/twilio/status",
        data={"CallSid": "CA_inbound_full_001", "CallStatus": "completed", "CallDuration": "42"},
    )
    assert complete_resp.status_code == 204


@pytest.mark.asyncio
async def test_outbound_call_flow_can_track_returning_caller_preference(client, db, monkeypatch):
    """Cross-endpoint flow: call lifecycle + per-caller preference persistence."""
    _install_fake_twilio(monkeypatch)

    phone = "+15554443333"

    # Seed caller preferences before call
    pref_seed = await client.put(
        "/api/preferences/%2B15554443333",
        json={
            "preferred_language": "es",
            "name": "María García",
            "sms_opt_in": True,
            "preferred_reminder_hours": 48,
        },
    )
    assert pref_seed.status_code == 200

    # Place outbound call and complete it
    create_resp = await client.post(
        "/api/calls/outbound",
        json={"phone_number": phone, "department_id": 2, "language": "es"},
    )
    assert create_resp.status_code == 201

    call_id = create_resp.json()["call"]["id"]

    status_resp = await client.post(
        "/api/twilio/status",
        data={"CallSid": "CA_int_test_123", "CallStatus": "completed", "CallDuration": "31"},
    )
    assert status_resp.status_code == 204

    # Track the same caller as a returning caller
    inc_resp = await client.post("/api/preferences/%2B15554443333/increment-call")
    assert inc_resp.status_code == 200
    assert inc_resp.json()["call_count"] == 1

    # Caller profile fields should remain intact after call-count update
    fetch_pref = await client.get("/api/preferences/%2B15554443333")
    assert fetch_pref.status_code == 200
    pref = fetch_pref.json()["preference"]
    assert pref["name"] == "María García"
    assert pref["preferred_language"] == "es"
    assert pref["preferred_reminder_hours"] == 48
    assert pref["call_count"] == 1

    # Ensure call persisted as completed in DB
    row = (await db.execute(select(Call).where(Call.id == call_id))).scalar_one()
    assert row.status == "completed"
    assert row.duration_seconds == 31

    # Ensure preference row persisted in DB for same phone
    pref_row = (
        await db.execute(select(CallerPreference).where(CallerPreference.phone_number == phone))
    ).scalar_one()
    assert pref_row.call_count == 1
    assert pref_row.preferred_language == "es"
