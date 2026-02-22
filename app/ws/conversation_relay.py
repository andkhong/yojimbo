"""Twilio ConversationRelay WebSocket handler.

This WebSocket is initiated by Twilio after an inbound call hits the
/api/twilio/voice webhook and receives TwiML with <Connect><ConversationRelay>.

Twilio handles STT/TTS on its infrastructure. This handler receives transcribed
caller speech as text and sends back text responses that Twilio converts to speech.
"""

import asyncio
import json
import logging
from datetime import datetime

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.database import async_session_factory
from app.models.call import Call, ConversationTurn
from app.models.agent_config import AgentConfig
from app.models.department import Department
from app.models.knowledge import KnowledgeEntry
from app.services.ai_agent import ConversationSession
from app.services import notification

logger = logging.getLogger(__name__)

# Active conversation sessions keyed by CallSid
active_sessions: dict[str, ConversationSession] = {}


async def handle_conversation_relay(websocket: WebSocket) -> None:
    """Handle a Twilio ConversationRelay WebSocket connection."""
    await websocket.accept()
    session: ConversationSession | None = None
    call_sid: str | None = None
    call_id: int | None = None

    try:
        async for raw_message in websocket.iter_text():
            try:
                message = json.loads(raw_message)
            except json.JSONDecodeError:
                logger.warning("Invalid JSON from ConversationRelay: %s", raw_message)
                continue

            msg_type = message.get("type")

            if msg_type == "setup":
                call_sid, call_id, session = await _handle_setup(message)
                if session:
                    active_sessions[call_sid] = session

            elif msg_type == "prompt" and session:
                caller_text = message.get("voicePrompt", "")
                if not caller_text.strip():
                    continue

                # Twilio provides the detected BCP-47 tag; strip region suffix
                detected_lang = message.get("lang", "en-US").split("-")[0]

                # Sync session language if Twilio confirmed a different language.
                # This rebuilds the Gemini system prompt so it responds natively.
                if detected_lang != session.caller_language:
                    session.update_language(detected_lang)

                async with async_session_factory() as db:
                    # Pass caller speech directly to Gemini — no translation needed.
                    # Gemini 2.0 Flash understands 40+ languages natively and will
                    # respond in the caller's language per the system prompt.
                    response_text = await session.process_caller_input(caller_text, db)

                    # Store conversation turns in the database
                    if call_id:
                        seq = session.turn_count * 2 - 1
                        db.add(
                            ConversationTurn(
                                call_id=call_id,
                                sequence=seq,
                                role="caller",
                                original_text=caller_text,
                                translated_text=None,  # no translation — stored as-is
                                language=session.caller_language,
                            )
                        )
                        db.add(
                            ConversationTurn(
                                call_id=call_id,
                                sequence=seq + 1,
                                role="agent",
                                original_text=response_text,
                                translated_text=None,  # response already in caller's language
                                language=session.caller_language,
                            )
                        )
                        await db.commit()

                    # Broadcast live transcript to dashboard
                    await notification.notify_call_transcript(
                        call_id=call_id or 0,
                        role="caller",
                        original_text=caller_text,
                        translated_text=None,
                        language=session.caller_language,
                    )

                    # Broadcast transcript turn to live-call monitor WebSocket
                    if call_id:
                        from app.ws.monitor import broadcast_call_event

                        asyncio.create_task(
                            broadcast_call_event(
                                "transcript_turn",
                                {
                                    "call_id": call_id,
                                    "caller_text": caller_text,
                                    "agent_response": response_text,
                                    "language": session.caller_language,
                                    "turn": session.turn_count,
                                },
                            )
                        )

                # Send response back via ConversationRelay
                await websocket.send_text(
                    json.dumps({"type": "text", "token": response_text, "last": True})
                )

            elif msg_type == "interrupt":
                logger.info(
                    "Call %s interrupted at: %s",
                    call_sid,
                    message.get("utteranceUntilInterrupt", ""),
                )

            elif msg_type == "error":
                logger.error(
                    "ConversationRelay error for %s: %s",
                    call_sid,
                    message.get("description", "Unknown error"),
                )

    except WebSocketDisconnect:
        logger.info("ConversationRelay WebSocket disconnected for %s", call_sid)
    except Exception:
        logger.exception("Error in ConversationRelay handler for %s", call_sid)
    finally:
        if call_sid and call_sid in active_sessions:
            del active_sessions[call_sid]
        # Mark call as completed
        if call_id:
            async with async_session_factory() as db:
                result = await db.execute(select(Call).where(Call.id == call_id))
                call = result.scalar_one_or_none()
                if call:
                    call.status = "completed"
                    call.ended_at = datetime.utcnow()
                    if call.started_at:
                        call.duration_seconds = int(
                            (call.ended_at - call.started_at).total_seconds()
                        )
                    # Store full transcript summary from conversation history
                    if session and session.history:
                        lines = []
                        for entry in session.history:
                            role = entry.get("role", "?")
                            content = entry.get("content", "")
                            if isinstance(content, list):
                                content = " ".join(
                                    p.get("text", "") for p in content if isinstance(p, dict)
                                )
                            lines.append(f"[{role.upper()}] {content}")
                        call.summary = "\n".join(lines)[:4000]  # DB safe truncation
                    await db.commit()

                    # Broadcast via monitor WebSocket
                    from app.ws.monitor import broadcast_call_event

                    asyncio.create_task(
                        broadcast_call_event(
                            "call_ended",
                            {
                                "call_id": call.id,
                                "duration_seconds": call.duration_seconds,
                                "resolution_status": call.resolution_status,
                            },
                            department_id=call.department_id,
                        )
                    )

                    await notification.notify_call_ended(
                        call_id=call.id,
                        duration_seconds=call.duration_seconds,
                    )


async def _handle_setup(message: dict) -> tuple[str | None, int | None, ConversationSession | None]:
    """Handle the initial setup event from ConversationRelay."""
    call_sid = message.get("callSid", "")
    caller_phone = message.get("from", "")
    custom_params = message.get("customParameters", {})
    language = custom_params.get("language", "en")

    logger.info("ConversationRelay setup: CallSid=%s, From=%s", call_sid, caller_phone)

    async with async_session_factory() as db:
        # Load department info for the AI agent context
        result = await db.execute(select(Department).where(Department.is_active.is_(True)))
        departments = result.scalars().all()
        dept_list = [
            {
                "id": d.id,
                "name": d.name,
                "description": d.description,
                "operating_hours": d.operating_hours,
            }
            for d in departments
        ]

        # Load knowledge base entries for the caller's language
        knowledge_entries = (
            (
                await db.execute(
                    select(KnowledgeEntry)
                    .where(KnowledgeEntry.is_active.is_(True), KnowledgeEntry.language == language)
                    .limit(30)
                )
            )
            .scalars()
            .all()
        )

        knowledge_context: str | None = None
        if knowledge_entries:
            knowledge_context = "\n\n".join(
                f"Q: {e.question}\nA: {e.answer}" for e in knowledge_entries
            )
            logger.info(
                "Loaded %d knowledge entries for language '%s'",
                len(knowledge_entries),
                language,
            )

        # Load DB-backed agent configuration overrides
        db_configs = (
            (
                await db.execute(
                    select(AgentConfig).where(
                        AgentConfig.key.in_(["system_prompt", "greeting_message"])
                    )
                )
            )
            .scalars()
            .all()
        )
        config_map = {cfg.key: cfg.value for cfg in db_configs}
        custom_system_prompt = config_map.get("system_prompt")
        greeting_message = config_map.get("greeting_message")

        if custom_system_prompt:
            logger.info("Using DB-configured system prompt for call %s", call_sid)

        # Create or update the call record
        call = Call(
            twilio_call_sid=call_sid,
            direction="inbound",
            status="in_progress",
            detected_language=language,
            started_at=datetime.utcnow(),
        )
        db.add(call)
        await db.flush()
        call_id = call.id
        await db.commit()

        await notification.notify_call_started(
            {
                "call_id": call_id,
                "call_sid": call_sid,
                "caller_number": caller_phone,
                "detected_language": language,
                "direction": "inbound",
            }
        )

        # Broadcast to live-call monitor
        from app.ws.monitor import broadcast_call_event

        asyncio.create_task(
            broadcast_call_event(
                "call_started",
                {
                    "call_id": call_id,
                    "call_sid": call_sid,
                    "caller_number": caller_phone,
                    "language": language,
                },
            )
        )

    session = ConversationSession(
        call_sid=call_sid,
        caller_phone=caller_phone,
        caller_language=language,
        departments=dept_list,
        knowledge_context=knowledge_context,
        custom_system_prompt=custom_system_prompt,
        greeting_message=greeting_message,
    )

    return call_sid, call_id, session
