"""Integration tests for ConversationRelay websocket setup/reconnect behavior."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app.models.call import Call
from app.models.caller_preference import CallerPreference
from app.ws import conversation_relay as relay
from tests.conftest import TestSessionFactory


@pytest.mark.asyncio
async def test_handle_setup_reconnect_reuses_call_and_does_not_double_count(db, monkeypatch):
    """Repeated setup for same CallSid should reuse call row and avoid double-counting."""

    async def _noop_notify(*args, **kwargs):
        return None

    monkeypatch.setattr(relay, "async_session_factory", TestSessionFactory)
    monkeypatch.setattr(relay.notification, "notify_call_started", _noop_notify)

    first_sid, first_call_id, _ = await relay._handle_setup(
        {
            "type": "setup",
            "callSid": "CA_reconnect_001",
            "from": "+15550000001",
            "customParameters": {"language": "en"},
        }
    )
    second_sid, second_call_id, _ = await relay._handle_setup(
        {
            "type": "setup",
            "callSid": "CA_reconnect_001",
            "from": "+15550000001",
            "customParameters": {"language": "en"},
        }
    )

    assert first_sid == second_sid == "CA_reconnect_001"
    assert first_call_id == second_call_id

    calls = (await db.execute(select(Call).where(Call.twilio_call_sid == "CA_reconnect_001"))).scalars().all()
    assert len(calls) == 1

    pref = (
        await db.execute(
            select(CallerPreference).where(CallerPreference.phone_number == "+15550000001")
        )
    ).scalar_one()
    assert pref.call_count == 1


class _FakeWebSocket:
    def __init__(self, messages: list[dict]):
        self._messages = [json.dumps(m) for m in messages]
        self.sent: list[str] = []

    async def accept(self):
        return None

    async def iter_text(self):
        for msg in self._messages:
            yield msg

    async def send_text(self, payload: str):
        self.sent.append(payload)


@pytest.mark.asyncio
async def test_conversation_relay_flow_completes_call_and_tracks_preferences(db, monkeypatch):
    """Setup + prompt flow should persist call transcript and mark completed on disconnect."""

    async def _noop_notify(*args, **kwargs):
        return None

    async def _fake_process(self, caller_text, db_session):
        self.history.append({"role": "caller", "content": caller_text})
        self.history.append({"role": "agent", "content": "Hello! How can I help?"})
        self.turn_count += 1
        return "Hello! How can I help?"

    monkeypatch.setattr(relay, "async_session_factory", TestSessionFactory)
    monkeypatch.setattr(relay.notification, "notify_call_started", _noop_notify)
    monkeypatch.setattr(relay.notification, "notify_call_ended", _noop_notify)
    monkeypatch.setattr(relay.notification, "notify_call_transcript", _noop_notify)
    monkeypatch.setattr(relay.ConversationSession, "process_caller_input", _fake_process)

    ws = _FakeWebSocket(
        [
            {
                "type": "setup",
                "callSid": "CA_flow_001",
                "from": "+15550000002",
                "customParameters": {"language": "en"},
            },
            {"type": "prompt", "voicePrompt": "I need permit help", "lang": "en-US"},
        ]
    )

    await relay.handle_conversation_relay(ws)

    # Response token sent back to Twilio relay
    sent = [json.loads(payload) for payload in ws.sent if payload]
    assert any(m.get("type") == "text" for m in sent)

    call = (await db.execute(select(Call).where(Call.twilio_call_sid == "CA_flow_001"))).scalar_one()
    assert call.status == "completed"
    assert call.summary and "permit help" in call.summary

    pref = (
        await db.execute(
            select(CallerPreference).where(CallerPreference.phone_number == "+15550000002")
        )
    ).scalar_one()
    assert pref.call_count == 1


@pytest.mark.asyncio
async def test_handle_setup_without_caller_phone_skips_preference_row(db, monkeypatch):
    """Anonymous/missing phone setup should still create call but not preference row."""

    async def _noop_notify(*args, **kwargs):
        return None

    monkeypatch.setattr(relay, "async_session_factory", TestSessionFactory)
    monkeypatch.setattr(relay.notification, "notify_call_started", _noop_notify)

    sid, call_id, _ = await relay._handle_setup(
        {
            "type": "setup",
            "callSid": "CA_no_phone_001",
            "customParameters": {"language": "en"},
        }
    )

    assert sid == "CA_no_phone_001"
    assert call_id is not None

    call = (await db.execute(select(Call).where(Call.twilio_call_sid == "CA_no_phone_001"))).scalar_one()
    assert call.status == "in_progress"

    prefs = (await db.execute(select(CallerPreference))).scalars().all()
    assert prefs == []


@pytest.mark.asyncio
async def test_reconnect_with_late_phone_backfills_preference_once(db, monkeypatch):
    """If initial setup has no phone, later reconnect should create one preference row."""

    async def _noop_notify(*args, **kwargs):
        return None

    monkeypatch.setattr(relay, "async_session_factory", TestSessionFactory)
    monkeypatch.setattr(relay.notification, "notify_call_started", _noop_notify)

    await relay._handle_setup(
        {
            "type": "setup",
            "callSid": "CA_late_phone_001",
            "customParameters": {"language": "en"},
        }
    )
    await relay._handle_setup(
        {
            "type": "setup",
            "callSid": "CA_late_phone_001",
            "from": "+15550000009",
            "customParameters": {"language": "es"},
        }
    )

    pref = (
        await db.execute(
            select(CallerPreference).where(CallerPreference.phone_number == "+15550000009")
        )
    ).scalar_one()
    assert pref.call_count == 1
    assert pref.preferred_language == "es"


@pytest.mark.asyncio
async def test_handle_setup_reconnect_updates_detected_language_without_increment(db, monkeypatch):
    """Reconnect may carry new language hint; call should update language without new count."""

    async def _noop_notify(*args, **kwargs):
        return None

    monkeypatch.setattr(relay, "async_session_factory", TestSessionFactory)
    monkeypatch.setattr(relay.notification, "notify_call_started", _noop_notify)

    await relay._handle_setup(
        {
            "type": "setup",
            "callSid": "CA_reconnect_lang_001",
            "from": "+15550000003",
            "customParameters": {"language": "en"},
        }
    )
    await relay._handle_setup(
        {
            "type": "setup",
            "callSid": "CA_reconnect_lang_001",
            "from": "+15550000003",
            "customParameters": {"language": "es"},
        }
    )

    call = (
        await db.execute(select(Call).where(Call.twilio_call_sid == "CA_reconnect_lang_001"))
    ).scalar_one()
    assert call.detected_language == "es"

    pref = (
        await db.execute(
            select(CallerPreference).where(CallerPreference.phone_number == "+15550000003")
        )
    ).scalar_one()
    assert pref.call_count == 1


@pytest.mark.asyncio
async def test_reconnect_with_existing_pref_updates_language_without_count_bump(db, monkeypatch):
    """Late phone reconnect should not increment pre-existing caller preference counts."""

    async def _noop_notify(*args, **kwargs):
        return None

    monkeypatch.setattr(relay, "async_session_factory", TestSessionFactory)
    monkeypatch.setattr(relay.notification, "notify_call_started", _noop_notify)

    db.add(CallerPreference(phone_number="+15550000010", preferred_language="en", call_count=4))
    await db.commit()

    await relay._handle_setup(
        {
            "type": "setup",
            "callSid": "CA_late_phone_002",
            "customParameters": {"language": "en"},
        }
    )
    await relay._handle_setup(
        {
            "type": "setup",
            "callSid": "CA_late_phone_002",
            "from": "+15550000010",
            "customParameters": {"language": "fr"},
        }
    )

    pref = (
        await db.execute(
            select(CallerPreference).where(CallerPreference.phone_number == "+15550000010")
        )
    ).scalar_one()
    assert pref.call_count == 4
    assert pref.preferred_language == "fr"


@pytest.mark.asyncio
async def test_handle_setup_new_call_updates_caller_preferred_language(db, monkeypatch):
    """New inbound calls should update stored caller preferred language per phone."""

    async def _noop_notify(*args, **kwargs):
        return None

    monkeypatch.setattr(relay, "async_session_factory", TestSessionFactory)
    monkeypatch.setattr(relay.notification, "notify_call_started", _noop_notify)

    existing_pref = CallerPreference(
        phone_number="+15550000004",
        preferred_language="en",
        call_count=2,
    )
    db.add(existing_pref)
    await db.commit()

    await relay._handle_setup(
        {
            "type": "setup",
            "callSid": "CA_pref_lang_001",
            "from": "+15550000004",
            "customParameters": {"language": "es"},
        }
    )

    async with TestSessionFactory() as check_db:
        pref = (
            await check_db.execute(
                select(CallerPreference).where(CallerPreference.phone_number == "+15550000004")
            )
        ).scalar_one()
        assert pref.preferred_language == "es"
        assert pref.call_count == 3
