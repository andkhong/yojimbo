"""Twilio ConversationRelay WebSocket handler.

This WebSocket is initiated by Twilio after an inbound call hits the
/api/twilio/voice webhook and receives TwiML with <Connect><ConversationRelay>.

Twilio handles STT/TTS on its infrastructure. This handler receives transcribed
caller speech as text and sends back text responses that Twilio converts to speech.
"""

import json
import logging
from datetime import datetime

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.models.call import Call, ConversationTurn
from app.models.department import Department
from app.services.ai_agent import ConversationSession
from app.services import notification, translator

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

                detected_lang = message.get("lang", "en-US").split("-")[0]

                async with async_session_factory() as db:
                    # Translate caller speech to English if needed
                    english_text = caller_text
                    if detected_lang != "en":
                        session.caller_language = detected_lang
                        english_text = await translator.translate_text(
                            caller_text, "en", detected_lang
                        )

                    # Process through Gemini AI agent
                    response_english = await session.process_caller_input(
                        english_text, db
                    )

                    # Translate response back to caller's language
                    response_text = response_english
                    if session.caller_language != "en":
                        response_text = await translator.translate_text(
                            response_english,
                            session.caller_language,
                            "en",
                        )

                    # Store conversation turns in the database
                    if call_id:
                        seq = session.turn_count * 2 - 1
                        db.add(ConversationTurn(
                            call_id=call_id,
                            sequence=seq,
                            role="caller",
                            original_text=caller_text,
                            translated_text=english_text if detected_lang != "en" else None,
                            language=detected_lang,
                        ))
                        db.add(ConversationTurn(
                            call_id=call_id,
                            sequence=seq + 1,
                            role="agent",
                            original_text=response_text,
                            translated_text=response_english if session.caller_language != "en" else None,
                            language=session.caller_language,
                        ))
                        await db.commit()

                    # Broadcast live transcript to dashboard
                    await notification.notify_call_transcript(
                        call_id=call_id or 0,
                        role="caller",
                        original_text=caller_text,
                        translated_text=english_text if detected_lang != "en" else None,
                        language=detected_lang,
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
                result = await db.execute(
                    select(Call).where(Call.id == call_id)
                )
                call = result.scalar_one_or_none()
                if call:
                    call.status = "completed"
                    call.ended_at = datetime.utcnow()
                    if call.started_at:
                        call.duration_seconds = int(
                            (call.ended_at - call.started_at).total_seconds()
                        )
                    await db.commit()

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
        result = await db.execute(
            select(Department).where(Department.is_active.is_(True))
        )
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

        await notification.notify_call_started({
            "call_id": call_id,
            "call_sid": call_sid,
            "caller_number": caller_phone,
            "detected_language": language,
            "direction": "inbound",
        })

    session = ConversationSession(
        call_sid=call_sid,
        caller_phone=caller_phone,
        caller_language=language,
        departments=dept_list,
    )

    return call_sid, call_id, session
