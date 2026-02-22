"""Department schemas."""

from datetime import datetime, time

from pydantic import BaseModel


class DepartmentCreate(BaseModel):
    name: str
    code: str
    phone_extension: str | None = None
    twilio_phone_number: str | None = None
    description: str | None = None
    operating_hours: str | None = None
    languages: str | None = None


class DepartmentUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    phone_extension: str | None = None
    twilio_phone_number: str | None = None
    description: str | None = None
    operating_hours: str | None = None
    languages: str | None = None
    is_active: bool | None = None


class DepartmentResponse(BaseModel):
    id: int
    name: str
    code: str
    phone_extension: str | None = None
    twilio_phone_number: str | None = None
    description: str | None = None
    operating_hours: str | None = None
    languages: str | None = None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class DepartmentStatsResponse(BaseModel):
    department_id: int
    department_name: str
    total_calls: int
    active_calls: int
    total_appointments: int
    upcoming_appointments: int
    resolved_calls: int
    escalated_calls: int
    resolution_rate: float  # percentage 0-100


class PhoneNumberAssignRequest(BaseModel):
    phone_number: str


class StaffMemberCreate(BaseModel):
    department_id: int
    name: str
    role: str | None = None
    email: str | None = None
    phone: str | None = None


class StaffMemberResponse(BaseModel):
    id: int
    department_id: int
    name: str
    role: str | None = None
    email: str | None = None
    is_active: bool

    model_config = {"from_attributes": True}


class TimeSlotCreate(BaseModel):
    day_of_week: int  # 0=Monday, 6=Sunday
    start_time: time
    end_time: time
    slot_duration_minutes: int = 30
    max_concurrent: int = 1


class TimeSlotUpdate(BaseModel):
    day_of_week: int | None = None
    start_time: time | None = None
    end_time: time | None = None
    slot_duration_minutes: int | None = None
    max_concurrent: int | None = None
    is_active: bool | None = None


class TimeSlotResponse(BaseModel):
    id: int
    department_id: int
    day_of_week: int
    start_time: time
    end_time: time
    slot_duration_minutes: int
    max_concurrent: int
    is_active: bool

    model_config = {"from_attributes": True}


class BulkSlotGenerateRequest(BaseModel):
    """Bulk-generate slots for specified days within a time window."""

    days_of_week: list[int]  # 0=Mon ... 6=Sun
    start_time: time
    end_time: time
    slot_duration_minutes: int = 30
    max_concurrent: int = 1
    replace_existing: bool = False
