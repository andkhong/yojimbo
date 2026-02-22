"""DashboardUser (staff) schemas."""

from datetime import datetime

from pydantic import BaseModel

VALID_ROLES = {"admin", "supervisor", "operator", "readonly"}


class UserCreate(BaseModel):
    username: str
    password: str
    name: str
    role: str = "operator"
    department_id: int | None = None

    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in VALID_ROLES:
            raise ValueError(f"Role must be one of: {VALID_ROLES}")
        return v


class UserUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    department_id: int | None = None
    is_active: bool | None = None
    password: str | None = None


class UserResponse(BaseModel):
    id: int
    username: str
    name: str
    role: str
    department_id: int | None = None
    is_active: bool
    last_login: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
