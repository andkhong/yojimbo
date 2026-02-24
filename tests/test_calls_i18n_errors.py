"""Regression tests for i18n-ready error payloads in calls API."""

from __future__ import annotations

from datetime import datetime

import pytest

from app.models.call import Call


@pytest.mark.asyncio
async def test_get_call_not_found_error_is_i18n_ready(client):
    resp = await client.get("/api/calls/99999")

    assert resp.status_code == 404
    detail = resp.json()["detail"]
    assert detail["message_key"] == "calls.not_found"
    assert detail["message"] == "Call not found"
    assert detail["params"]["call_id"] == 99999


@pytest.mark.asyncio
async def test_transfer_invalid_status_error_is_i18n_ready(client, db):
    call = Call(
        twilio_call_sid="CA_xfer_i18n_001",
        direction="inbound",
        status="completed",
        started_at=datetime.utcnow(),
    )
    db.add(call)
    await db.flush()

    resp = await client.post(f"/api/calls/{call.id}/transfer?transfer_to=%2B15551234567")

    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["message_key"] == "calls.transfer.invalid_status"
    assert detail["params"]["status"] == "completed"
    assert detail["params"]["allowed_statuses"] == ["ringing", "in_progress"]


@pytest.mark.asyncio
async def test_terminate_invalid_status_error_is_i18n_ready(client, db):
    call = Call(
        twilio_call_sid="CA_term_i18n_001",
        direction="inbound",
        status="failed",
        started_at=datetime.utcnow(),
    )
    db.add(call)
    await db.flush()

    resp = await client.post(f"/api/calls/{call.id}/terminate")

    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["message_key"] == "calls.terminate.invalid_status"
    assert detail["params"]["status"] == "failed"
    assert detail["params"]["allowed_statuses"] == ["ringing", "in_progress"]
