"""Call management API endpoints — list, live monitor, transfer, terminate."""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.call import Call, ConversationTurn
from app.schemas.call import CallResponse, ConversationTurnResponse, OutboundCallRequest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/calls", tags=["calls"])


@router.get("")
async def list_calls(
    db: AsyncSession = Depends(get_db),
    status: str | None = None,
    department_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    query = select(Call).order_by(Call.started_at.desc())

    if status:
        query = query.where(Call.status == status)
    if department_id:
        query = query.where(Call.department_id == department_id)
    if date_from:
        query = query.where(Call.started_at >= datetime.fromisoformat(date_from))
    if date_to:
        query = query.where(Call.started_at <= datetime.fromisoformat(date_to))

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    calls = result.scalars().all()

    return {
        "calls": [CallResponse.model_validate(c) for c in calls],
        "total": total,
        "page": page,
    }


# --- Static-path endpoints MUST come before /{call_id} ---


@router.get("/active", summary="Get all currently active calls")
async def get_active_calls(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Call)
        .where(Call.status.in_(["ringing", "in_progress"]))
        .order_by(Call.started_at.desc())
    )
    calls = result.scalars().all()
    return {"calls": [CallResponse.model_validate(c) for c in calls]}


@router.get("/live", summary="Currently active calls with live transcript")
async def get_live_calls(db: AsyncSession = Depends(get_db)):
    """Return all currently active calls with their partial transcripts and metadata."""
    result = await db.execute(
        select(Call).where(Call.status.in_(["ringing", "in_progress"])).order_by(Call.started_at)
    )
    calls = result.scalars().all()

    live_calls = []
    for c in calls:
        turns = (
            (
                await db.execute(
                    select(ConversationTurn)
                    .where(ConversationTurn.call_id == c.id)
                    .order_by(ConversationTurn.sequence.desc())
                    .limit(10)
                )
            )
            .scalars()
            .all()
        )

        elapsed = None
        if c.started_at:
            elapsed = int((datetime.utcnow() - c.started_at).total_seconds())

        live_calls.append(
            {
                "call": CallResponse.model_validate(c),
                "elapsed_seconds": elapsed,
                "partial_transcript": c.partial_transcript,
                "recent_turns": [
                    ConversationTurnResponse.model_validate(t) for t in reversed(turns)
                ],
            }
        )

    return {"live_calls": live_calls, "count": len(live_calls)}


@router.post("/outbound", status_code=201, summary="Initiate an outbound call")
async def initiate_outbound_call(
    request: OutboundCallRequest,
    db: AsyncSession = Depends(get_db),
):
    """Initiate an outbound call via Twilio."""
    from app.config import settings

    try:
        from twilio.rest import Client

        client = Client(settings.twilio_account_sid, settings.twilio_auth_token)

        call = client.calls.create(
            to=request.phone_number,
            from_=settings.twilio_phone_number,
            url=f"{settings.base_url}/api/twilio/voice/outbound",
            status_callback=f"{settings.base_url}/api/twilio/status",
            status_callback_event=["initiated", "ringing", "answered", "completed"],
        )

        db_call = Call(
            twilio_call_sid=call.sid,
            direction="outbound",
            status="ringing",
            department_id=request.department_id,
            detected_language=request.language,
            started_at=datetime.utcnow(),
        )
        db.add(db_call)
        await db.flush()

        return {"call": CallResponse.model_validate(db_call)}

    except Exception as e:
        return {"error": f"Failed to initiate call: {e}"}


# --- Parameterised endpoints last ---


@router.get("/{call_id}", summary="Get a call by ID with transcript")
async def get_call(call_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Call).where(Call.id == call_id))
    call = result.scalar_one_or_none()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    result = await db.execute(
        select(ConversationTurn)
        .where(ConversationTurn.call_id == call_id)
        .order_by(ConversationTurn.sequence)
    )
    turns = result.scalars().all()

    return {
        "call": CallResponse.model_validate(call),
        "transcript": [ConversationTurnResponse.model_validate(t) for t in turns],
    }


@router.get("/{call_id}/transcript", summary="Get conversation transcript for a call")
async def get_call_transcript(call_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ConversationTurn)
        .where(ConversationTurn.call_id == call_id)
        .order_by(ConversationTurn.sequence)
    )
    turns = result.scalars().all()
    return {"turns": [ConversationTurnResponse.model_validate(t) for t in turns]}


@router.post("/{call_id}/transfer", summary="Transfer call to a human agent")
async def transfer_call(
    call_id: int,
    transfer_to: str,
    db: AsyncSession = Depends(get_db),
):
    """Transfer an active call to a human agent phone number."""
    call = (await db.execute(select(Call).where(Call.id == call_id))).scalar_one_or_none()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")
    if call.status not in ("ringing", "in_progress"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot transfer call in status '{call.status}'",
        )

    try:
        from app.config import settings
        from twilio.rest import Client

        client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        twiml = f"<Response><Dial>{transfer_to}</Dial></Response>"
        client.calls(call.twilio_call_sid).update(twiml=twiml)
        call.resolution_status = "escalated"
        logger.info("Transferred call %s to %s", call_id, transfer_to)
    except Exception as exc:
        logger.warning("Twilio transfer failed (non-prod?): %s", exc)
        call.resolution_status = "escalated"

    return {"transferred": True, "call_id": call_id, "transferred_to": transfer_to}


@router.get("/{call_id}/recording", summary="Get the recording URL for a completed call")
async def get_call_recording(call_id: int, db: AsyncSession = Depends(get_db)):
    """Return the Twilio recording URL for a completed call (if recording was enabled)."""
    call = (await db.execute(
        select(Call).where(Call.id == call_id)
    )).scalar_one_or_none()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    if not call.recording_url:
        # Try to fetch from Twilio if we have a SID
        if call.twilio_call_sid:
            try:
                from app.config import settings
                from twilio.rest import Client

                client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
                recordings = client.recordings.list(call_sid=call.twilio_call_sid, limit=1)
                if recordings:
                    call.recording_url = (
                        f"https://api.twilio.com{recordings[0].uri.replace('.json', '.mp3')}"
                    )
            except Exception as exc:
                logger.debug("Could not fetch recording from Twilio: %s", exc)

    return {
        "call_id": call_id,
        "recording_url": call.recording_url,
        "has_recording": call.recording_url is not None,
    }


@router.put("/{call_id}/recording", summary="Store the recording URL for a call")
async def set_call_recording(
    call_id: int,
    recording_url: str,
    db: AsyncSession = Depends(get_db),
):
    """Store or update the recording URL for a call.

    Called by the Twilio recording status callback webhook.
    """
    call = (await db.execute(
        select(Call).where(Call.id == call_id)
    )).scalar_one_or_none()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    call.recording_url = recording_url
    return {
        "call_id": call_id,
        "recording_url": recording_url,
    }


@router.post("/{call_id}/terminate", summary="Terminate an active call from the dashboard")
async def terminate_call(
    call_id: int,
    db: AsyncSession = Depends(get_db),
):
    """End an active call from the dashboard (hangs up via Twilio)."""
    call = (await db.execute(select(Call).where(Call.id == call_id))).scalar_one_or_none()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")
    if call.status not in ("ringing", "in_progress"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot terminate call in status '{call.status}'",
        )

    try:
        from app.config import settings
        from twilio.rest import Client

        client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        client.calls(call.twilio_call_sid).update(status="completed")
    except Exception as exc:
        logger.warning("Twilio terminate failed (non-prod?): %s", exc)

    call.status = "completed"
    call.ended_at = datetime.utcnow()
    if call.started_at:
        call.duration_seconds = int((call.ended_at - call.started_at).total_seconds())
    return {"terminated": True, "call_id": call_id}
