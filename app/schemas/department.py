from datetime import datetime

from pydantic import BaseModel


class DepartmentCreate(BaseModel):
    name: str
    code: str
    phone_extension: str | None = None
    description: str | None = None
    operating_hours: str | None = None


class DepartmentResponse(BaseModel):
    id: int
    name: str
    code: str
    phone_extension: str | None = None
    description: str | None = None
    operating_hours: str | None = None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class StaffMemberResponse(BaseModel):
    id: int
    department_id: int
    name: str
    role: str | None = None
    email: str | None = None
    is_active: bool

    model_config = {"from_attributes": True}
