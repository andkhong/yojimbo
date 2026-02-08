from datetime import datetime

from pydantic import BaseModel


class SMSMessageResponse(BaseModel):
    id: int
    twilio_message_sid: str
    contact_id: int | None = None
    direction: str
    body: str
    translated_body: str | None = None
    detected_language: str | None = None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class SendSMSRequest(BaseModel):
    phone_number: str
    body: str
    language: str = "en"
