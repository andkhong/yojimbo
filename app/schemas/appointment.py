from datetime import datetime

from pydantic import BaseModel


class AppointmentCreate(BaseModel):
    contact_id: int
    department_id: int
    staff_member_id: int | None = None
    title: str
    description: str | None = None
    scheduled_start: datetime
    scheduled_end: datetime
    language: str = "en"


class AppointmentUpdate(BaseModel):
    status: str | None = None
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    title: str | None = None
    description: str | None = None


class AppointmentResponse(BaseModel):
    id: int
    contact_id: int
    department_id: int
    staff_member_id: int | None = None
    call_id: int | None = None
    title: str
    description: str | None = None
    status: str
    scheduled_start: datetime
    scheduled_end: datetime
    language: str
    reminder_sent: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AvailabilitySlot(BaseModel):
    start: datetime
    end: datetime


class AvailabilityResponse(BaseModel):
    department_id: int
    date: str
    slots: list[AvailabilitySlot]
