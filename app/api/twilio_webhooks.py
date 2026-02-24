"""Twilio webhook handlers for voice calls, SMS, and status callbacks."""

import logging

from fastapi import APIRouter, Depends, Form, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.call import Call
from app.services import notification, sms_handler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/twilio", tags=["twilio"])


@router.post("/voice")
async def handle_inbound_voice(
    request: Request,
    CallSid: str = Form(""),
    From: str = Form(""),
    To: str = Form(""),
    CallStatus: str = Form(""),
) -> Response:
    """Handle inbound voice call webhook.

    Returns TwiML that connects the call to ConversationRelay,
    which opens a WebSocket back to our /ws/conversation-relay endpoint.
    """
    logger.info("Inbound call: CallSid=%s From=%s Status=%s", CallSid, From, CallStatus)

    # Build the WebSocket URL for ConversationRelay
    ws_scheme = "wss" if settings.base_url.startswith("https") else "ws"
    ws_host = settings.base_url.replace("https://", "").replace("http://", "")
    ws_url = f"{ws_scheme}://{ws_host}/ws/conversation-relay"

    # TwiML with ConversationRelay
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <ConversationRelay
            url="{ws_url}"
            ttsProvider="{settings.cr_tts_provider}"
            voice="en-US-Neural2-F"
            transcriptionProvider="{settings.cr_stt_provider}"
            welcomeGreeting="{settings.cr_welcome_greeting}"
            dtmfDetection="true"
            interruptible="true"
        >
            <Parameter name="language" value="auto" />
            <Parameter name="callSid" value="{CallSid}" />
            <Parameter name="callerNumber" value="{From}" />
        </ConversationRelay>
    </Connect>
</Response>"""

    return Response(content=twiml, media_type="application/xml")


@router.post("/voice/outbound")
async def handle_outbound_voice(
    request: Request,
    CallSid: str = Form(""),
) -> Response:
    """Handle outbound call webhook (Twilio calls this after connecting)."""
    logger.info("Outbound call connected: CallSid=%s", CallSid)

    ws_scheme = "wss" if settings.base_url.startswith("https") else "ws"
    ws_host = settings.base_url.replace("https://", "").replace("http://", "")
    ws_url = f"{ws_scheme}://{ws_host}/ws/conversation-relay"

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <ConversationRelay
            url="{ws_url}"
            ttsProvider="{settings.cr_tts_provider}"
            voice="en-US-Neural2-F"
            transcriptionProvider="{settings.cr_stt_provider}"
            welcomeGreeting="Hello, this is Yojimbo calling from {settings.office_name}."
            dtmfDetection="true"
            interruptible="true"
        >
            <Parameter name="language" value="en" />
            <Parameter name="callSid" value="{CallSid}" />
        </ConversationRelay>
    </Connect>
</Response>"""

    return Response(content=twiml, media_type="application/xml")


@router.post("/sms")
async def handle_inbound_sms(
    request: Request,
    db: AsyncSession = Depends(get_db),
    From: str = Form(""),
    Body: str = Form(""),
    MessageSid: str = Form(""),
) -> Response:
    """Handle inbound SMS webhook. Returns TwiML with reply."""
    logger.info("Inbound SMS from %s: %s", From, Body[:50])

    reply_text = await sms_handler.handle_inbound_sms(
        db=db,
        from_number=From,
        body=Body,
        message_sid=MessageSid,
    )

    await notification.notify_sms_received(
        {
            "from": From,
            "body": Body[:100],
            "message_sid": MessageSid,
        }
    )

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{reply_text}</Message>
</Response>"""

    return Response(content=twiml, media_type="application/xml")


@router.post("/status")
async def handle_status_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
    CallSid: str = Form(""),
    CallStatus: str = Form(""),
    CallDuration: str = Form("0"),
) -> Response:
    """Handle call status callback from Twilio."""
    logger.info("Call status update: %s -> %s", CallSid, CallStatus)

    result = await db.execute(select(Call).where(Call.twilio_call_sid == CallSid))
    call = result.scalar_one_or_none()

    if call:
        status_map = {
            "initiated": "ringing",
            "ringing": "ringing",
            "in-progress": "in_progress",
            "completed": "completed",
            "busy": "busy",
            "no-answer": "no_answer",
            "canceled": "cancelled",
            "failed": "failed",
        }
        call.status = status_map.get(CallStatus, CallStatus)
        if CallStatus == "completed":
            try:
                call.duration_seconds = int(CallDuration)
            except (TypeError, ValueError):
                logger.warning(
                    "Invalid CallDuration for completed call: CallSid=%s CallDuration=%r",
                    CallSid,
                    CallDuration,
                )
                call.duration_seconds = 0

        await notification.notify_call_status_changed(
            call_id=call.id,
            status=call.status,
        )

    return Response(content="", status_code=204)
