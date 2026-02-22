"""Tests for Twilio webhook endpoints."""

import pytest


@pytest.mark.asyncio
async def test_inbound_voice_returns_twiml(client):
    response = await client.post(
        "/api/twilio/voice",
        data={
            "CallSid": "CA_TEST_123",
            "From": "+15551234567",
            "To": "+15559876543",
            "CallStatus": "ringing",
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/xml"
    body = response.text
    assert "<Response>" in body
    assert "ConversationRelay" in body
    assert "ws" in body.lower() or "wss" in body.lower()


@pytest.mark.asyncio
async def test_outbound_voice_returns_twiml(client):
    response = await client.post(
        "/api/twilio/voice/outbound",
        data={"CallSid": "CA_TEST_OUT_456"},
    )
    assert response.status_code == 200
    assert "ConversationRelay" in response.text


@pytest.mark.asyncio
async def test_inbound_sms_returns_twiml(client):
    response = await client.post(
        "/api/twilio/sms",
        data={
            "From": "+15551234567",
            "Body": "Hello, I need to schedule an appointment",
            "MessageSid": "SM_TEST_789",
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/xml"
    assert "<Message>" in response.text


@pytest.mark.asyncio
async def test_status_callback(client):
    response = await client.post(
        "/api/twilio/status",
        data={
            "CallSid": "CA_NONEXISTENT",
            "CallStatus": "completed",
            "CallDuration": "120",
        },
    )
    # Should return 204 even if call not found (idempotent)
    assert response.status_code == 204
