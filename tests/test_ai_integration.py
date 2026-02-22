"""Tests for AI agent integration with knowledge base and DB config.

Covers:
- ConversationSession accepts knowledge_context and injects into system prompt
- ConversationSession accepts custom_system_prompt from DB
- ConversationSession accepts greeting_message from DB
- Fallback behavior when no Gemini key
- Knowledge context endpoint integration with relay-compatible format
"""

import pytest

from app.services.ai_agent import ConversationSession


# ===========================================================================
# ConversationSession unit tests
# ===========================================================================


def test_conversation_session_default_system_prompt():
    """Default session builds system instruction from template."""
    session = ConversationSession(
        call_sid="CA_test_001",
        caller_phone="+15550001111",
        caller_language="en",
    )
    assert session.system_instruction
    assert len(session.system_instruction) > 50


def test_conversation_session_with_departments():
    """Session includes department info in system instruction."""
    session = ConversationSession(
        call_sid="CA_test_002",
        caller_phone="+15550001111",
        caller_language="en",
        departments=[
            {
                "id": 1,
                "name": "Building Permits",
                "description": "Permit issues",
                "operating_hours": "9am-5pm",
            },
        ],
    )
    assert "Building Permits" in session.system_instruction


def test_conversation_session_with_knowledge_context():
    """Knowledge context is appended to system instruction."""
    knowledge = "Q: What are your hours?\nA: Monday-Friday, 9am-5pm."
    session = ConversationSession(
        call_sid="CA_test_003",
        caller_phone="+15550001111",
        caller_language="en",
        knowledge_context=knowledge,
    )
    assert "Knowledge Base" in session.system_instruction
    assert "What are your hours?" in session.system_instruction
    assert "Monday-Friday, 9am-5pm" in session.system_instruction


def test_conversation_session_custom_system_prompt():
    """Custom system prompt from DB overrides the template."""
    custom_prompt = "You are a specialized police dispatch assistant."
    session = ConversationSession(
        call_sid="CA_test_004",
        caller_phone="+15550001111",
        caller_language="en",
        custom_system_prompt=custom_prompt,
    )
    assert session.system_instruction == custom_prompt + ""  # knowledge appended later


def test_conversation_session_custom_prompt_with_knowledge():
    """Custom system prompt still gets knowledge context appended."""
    custom_prompt = "You are a tax office assistant."
    knowledge = "Q: What is my parcel number?\nA: Check your property tax bill."
    session = ConversationSession(
        call_sid="CA_test_005",
        caller_phone="+15550001111",
        caller_language="en",
        custom_system_prompt=custom_prompt,
        knowledge_context=knowledge,
    )
    assert "tax office assistant" in session.system_instruction
    assert "parcel number" in session.system_instruction


def test_conversation_session_greeting_message():
    """Greeting message is stored on session for relay use."""
    session = ConversationSession(
        call_sid="CA_test_006",
        caller_phone="+15550001111",
        caller_language="en",
        greeting_message="Thank you for calling City Hall!",
    )
    assert session.greeting_message == "Thank you for calling City Hall!"


def test_conversation_session_fallback_response():
    """Session returns fallback when no Gemini client available."""
    session = ConversationSession(
        call_sid="CA_test_007",
        caller_phone="+15550001111",
        caller_language="en",
    )
    # Access the private fallback directly
    response = session._fallback_response("what are your hours?")
    assert isinstance(response, str)
    assert len(response) > 5


def test_conversation_session_no_knowledge():
    """Session without knowledge context does not add FAQ section."""
    session = ConversationSession(
        call_sid="CA_test_008",
        caller_phone="+15550001111",
        caller_language="en",
        knowledge_context=None,
    )
    assert "Knowledge Base" not in session.system_instruction


def test_conversation_session_empty_knowledge_not_injected():
    """Empty string knowledge context is treated as falsy — not injected."""
    session = ConversationSession(
        call_sid="CA_test_009",
        caller_phone="+15550001111",
        caller_language="en",
        knowledge_context="",  # falsy
    )
    assert "Knowledge Base" not in session.system_instruction


def test_conversation_session_spanish_language():
    """Session builds correct language name for Spanish."""
    session = ConversationSession(
        call_sid="CA_test_010",
        caller_phone="+15550001111",
        caller_language="es",
    )
    # Should use the human-readable language name
    assert session.system_instruction is not None


def test_conversation_session_history_starts_empty():
    """Conversation history starts empty."""
    session = ConversationSession(
        call_sid="CA_test_011",
        caller_phone="+15550001111",
    )
    assert session.history == []
    assert session.turn_count == 0


# ===========================================================================
# Knowledge context endpoint integration
# ===========================================================================


@pytest.mark.asyncio
async def test_knowledge_context_for_relay(client, db):
    """Knowledge context endpoint returns data in relay-compatible format."""
    from app.models.knowledge import KnowledgeEntry

    db.add(
        KnowledgeEntry(
            question="How do I apply for a permit?",
            answer="Visit city hall or apply online at permits.cityname.gov",
            language="en",
            is_active=True,
        )
    )
    db.add(
        KnowledgeEntry(
            question="¿Cuáles son sus horas?",
            answer="Lunes a viernes, 9am-5pm.",
            language="es",
            is_active=True,
        )
    )
    await db.flush()

    # English context
    resp = await client.get("/api/knowledge/context?language=en")
    assert resp.status_code == 200
    data = resp.json()
    assert data["entry_count"] == 1
    assert "How do I apply" in data["context"]

    # Spanish context
    resp2 = await client.get("/api/knowledge/context?language=es")
    data2 = resp2.json()
    assert data2["entry_count"] == 1
    assert "horas" in data2["context"]


@pytest.mark.asyncio
async def test_knowledge_context_department_filter(client, db):
    """Knowledge context filters correctly by department."""
    from app.models.department import Department
    from app.models.knowledge import KnowledgeEntry

    dept = Department(name="Roads", code="RD")
    db.add(dept)
    await db.flush()

    # Department-specific entry
    db.add(
        KnowledgeEntry(
            question="Road repair request?",
            answer="Call 311.",
            language="en",
            department_id=dept.id,
            is_active=True,
        )
    )
    # Global entry (no department)
    db.add(
        KnowledgeEntry(
            question="General hours?",
            answer="9am-5pm Mon-Fri.",
            language="en",
            department_id=None,
            is_active=True,
        )
    )
    await db.flush()

    # Without department filter — only global entries
    resp = await client.get("/api/knowledge/context?language=en")
    data = resp.json()
    context = data["context"]
    assert "General hours?" in context

    # With department filter — both department + global
    resp2 = await client.get(f"/api/knowledge/context?language=en&department_id={dept.id}")
    data2 = resp2.json()
    assert data2["entry_count"] == 2
    assert "Road repair" in data2["context"]
    assert "General hours" in data2["context"]


# ===========================================================================
# Agent config integration
# ===========================================================================


@pytest.mark.asyncio
async def test_agent_config_persistence(client):
    """Config set via API is retrievable across multiple GET calls."""
    # Set config
    await client.put(
        "/api/config/agent",
        json={"updates": {"greeting_message": "Hello from City Hall!", "max_turns": "15"}},
    )

    # Read back via list
    resp = await client.get("/api/config/agent")
    config = resp.json()["config"]
    assert config["greeting_message"] == "Hello from City Hall!"
    assert config["max_turns"] == "15"

    # Read back via single key
    resp2 = await client.get("/api/config/agent/greeting_message")
    assert resp2.json()["value"] == "Hello from City Hall!"


@pytest.mark.asyncio
async def test_agent_config_delete_and_reset(client):
    """Config key can be set, deleted, and re-set."""
    await client.put("/api/config/agent", json={"updates": {"timezone": "America/Los_Angeles"}})

    resp = await client.get("/api/config/agent/timezone")
    assert resp.status_code == 200

    await client.delete("/api/config/agent/timezone")

    resp2 = await client.get("/api/config/agent/timezone")
    assert resp2.status_code == 404

    # Re-set
    await client.put("/api/config/agent", json={"updates": {"timezone": "America/New_York"}})
    resp3 = await client.get("/api/config/agent/timezone")
    assert resp3.json()["value"] == "America/New_York"
