"""SMS message API endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.message import SMSMessage
from app.schemas.message import SendSMSRequest, SMSMessageResponse

router = APIRouter(prefix="/api/messages", tags=["messages"])


@router.get("")
async def list_messages(
    db: AsyncSession = Depends(get_db),
    contact_id: int | None = None,
    department_id: int | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    query = select(SMSMessage).order_by(SMSMessage.created_at.desc())

    if contact_id:
        query = query.where(SMSMessage.contact_id == contact_id)
    if department_id:
        query = query.where(SMSMessage.department_id == department_id)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    messages = result.scalars().all()

    return {
        "messages": [SMSMessageResponse.model_validate(m) for m in messages],
        "total": total,
        "page": page,
    }


@router.post("/send", status_code=201)
async def send_sms(
    data: SendSMSRequest,
    db: AsyncSession = Depends(get_db),
):
    """Send an outbound SMS via Twilio."""
    try:
        from twilio.rest import Client

        client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        message = client.messages.create(
            to=data.phone_number,
            from_=settings.twilio_phone_number,
            body=data.body,
        )

        sms = SMSMessage(
            twilio_message_sid=message.sid,
            direction="outbound",
            body=data.body,
            status="sent",
        )
        db.add(sms)
        await db.flush()

        return {"message": SMSMessageResponse.model_validate(sms)}
    except Exception as e:
        return {"error": f"Failed to send SMS: {e}"}
