"""Call management API endpoints."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.call import Call, ConversationTurn
from app.schemas.call import CallResponse, ConversationTurnResponse, OutboundCallRequest

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

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Paginate
    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    calls = result.scalars().all()

    return {
        "calls": [CallResponse.model_validate(c) for c in calls],
        "total": total,
        "page": page,
    }


@router.get("/active")
async def get_active_calls(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Call)
        .where(Call.status.in_(["ringing", "in_progress"]))
        .order_by(Call.started_at.desc())
    )
    calls = result.scalars().all()
    return {"calls": [CallResponse.model_validate(c) for c in calls]}


@router.get("/{call_id}")
async def get_call(call_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Call).where(Call.id == call_id))
    call = result.scalar_one_or_none()
    if not call:
        return {"error": "Call not found"}, 404

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


@router.get("/{call_id}/transcript")
async def get_call_transcript(call_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ConversationTurn)
        .where(ConversationTurn.call_id == call_id)
        .order_by(ConversationTurn.sequence)
    )
    turns = result.scalars().all()
    return {"turns": [ConversationTurnResponse.model_validate(t) for t in turns]}


@router.post("/outbound", status_code=201)
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
