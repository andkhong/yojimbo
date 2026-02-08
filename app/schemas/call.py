from datetime import datetime

from pydantic import BaseModel


class CallResponse(BaseModel):
    id: int
    twilio_call_sid: str
    contact_id: int | None = None
    direction: str
    status: str
    detected_language: str | None = None
    department_id: int | None = None
    summary: str | None = None
    sentiment: str | None = None
    duration_seconds: int | None = None
    started_at: datetime
    ended_at: datetime | None = None

    model_config = {"from_attributes": True}


class ConversationTurnResponse(BaseModel):
    id: int
    call_id: int
    sequence: int
    role: str
    original_text: str
    translated_text: str | None = None
    language: str
    intent: str | None = None
    timestamp: datetime

    model_config = {"from_attributes": True}


class OutboundCallRequest(BaseModel):
    phone_number: str
    department_id: int | None = None
    language: str = "en"
    purpose: str | None = None
