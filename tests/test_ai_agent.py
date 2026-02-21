"""Tests for the AI agent service (ConversationSession)."""

from app.services.ai_agent import ConversationSession


def test_conversation_session_initialization():
    session = ConversationSession(
        call_sid="CA_TEST",
        caller_phone="+15551234567",
        caller_language="es",
        departments=[
            {"id": 1, "name": "Building Permits", "description": "Permits"},
        ],
    )
    assert session.call_sid == "CA_TEST"
    assert session.caller_phone == "+15551234567"
    assert session.caller_language == "es"
    assert session.turn_count == 0
    assert "Yojimbo" in session.system_instruction
    assert "Building Permits" in session.system_instruction
    assert "Spanish" in session.system_instruction


def test_conversation_session_fallback():
    session = ConversationSession(
        call_sid="CA_TEST",
        caller_phone="+15551234567",
    )
    response = session._fallback_response("Hello")
    assert "technical difficulties" in response.lower()


def test_conversation_session_summary_prompt():
    session = ConversationSession(
        call_sid="CA_TEST",
        caller_phone="+15551234567",
    )
    prompt = session.get_summary_prompt()
    assert "summary" in prompt.lower()
    assert "sentiment" in prompt.lower()


def test_conversation_session_multiple_departments():
    departments = [
        {"id": 1, "name": "General Info", "description": "General inquiries"},
        {"id": 2, "name": "Building Permits", "description": "Permits"},
        {"id": 3, "name": "Parks & Rec", "description": "Parks and recreation"},
    ]
    session = ConversationSession(
        call_sid="CA_TEST",
        caller_phone="+15551234567",
        departments=departments,
    )
    assert "General Info" in session.system_instruction
    assert "Building Permits" in session.system_instruction
    assert "Parks & Rec" in session.system_instruction
