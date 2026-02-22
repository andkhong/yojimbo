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


# ---------------------------------------------------------------------------
# update_language — latency-optimisation path
# ---------------------------------------------------------------------------


def test_update_language_changes_caller_language():
    """update_language() must update caller_language attribute."""
    session = ConversationSession(
        call_sid="CA_LANG",
        caller_phone="+15551234567",
        caller_language="en",
    )
    assert session.caller_language == "en"
    session.update_language("es")
    assert session.caller_language == "es"


def test_update_language_rebuilds_system_instruction():
    """After update_language(), system_instruction must name Spanish as the caller's language."""
    session = ConversationSession(
        call_sid="CA_LANG",
        caller_phone="+15551234567",
        caller_language="en",
    )
    # Before update: caller-specific language slots say "English"
    assert "detected language: English" in session.system_instruction
    assert "ENTIRELY in English" in session.system_instruction

    session.update_language("es")

    # After update: caller-specific language slots now say "Spanish"
    assert "detected language: Spanish" in session.system_instruction
    assert "ENTIRELY in Spanish" in session.system_instruction


def test_update_language_noop_same_language():
    """update_language() with the same code must not change system_instruction."""
    session = ConversationSession(
        call_sid="CA_LANG",
        caller_phone="+15551234567",
        caller_language="es",
    )
    original_instruction = session.system_instruction
    session.update_language("es")  # same language — should be a no-op
    assert session.system_instruction is original_instruction  # same object


def test_update_language_supported_immigrant_languages():
    """Verify update_language works for the top US immigrant languages."""
    targets = {
        "es": "Spanish",
        "zh": "Chinese",
        "vi": "Vietnamese",
        "tl": "Tagalog",
        "ko": "Korean",
    }
    for code, expected_name in targets.items():
        session = ConversationSession(
            call_sid=f"CA_{code.upper()}",
            caller_phone="+15551234567",
            caller_language="en",
        )
        session.update_language(code)
        assert session.caller_language == code, f"caller_language not set for {code}"
        assert expected_name in session.system_instruction, (
            f"Expected '{expected_name}' in system_instruction for lang={code}"
        )


def test_system_prompt_contains_native_language_instruction():
    """System prompt must explicitly instruct Gemini to respond natively."""
    session = ConversationSession(
        call_sid="CA_NATIVE",
        caller_phone="+15551234567",
        caller_language="vi",
    )
    # Key guard: no translate-to-English intermediate step in the prompt
    instr = session.system_instruction
    assert "MUST respond" in instr or "natively" in instr  # strong language directive
    assert "Vietnamese" in instr
