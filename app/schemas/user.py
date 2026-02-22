"""DashboardUser (staff) schemas."""

import re
from datetime import datetime

from pydantic import BaseModel, field_validator

VALID_ROLES = {"admin", "supervisor", "operator", "readonly"}
_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_\-.]{3,64}$")
_MIN_PASSWORD_LEN = 8


class UserCreate(BaseModel):
    username: str
    password: str
    name: str
    role: str = "operator"
    department_id: int | None = None

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        v = v.strip()
        if not _USERNAME_RE.match(v):
            raise ValueError(
                "Username must be 3-64 characters and contain only letters, "
                "numbers, underscores, hyphens, or dots."
            )
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < _MIN_PASSWORD_LEN:
            raise ValueError(f"Password must be at least {_MIN_PASSWORD_LEN} characters.")
        return v

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in VALID_ROLES:
            raise ValueError(f"Role must be one of: {sorted(VALID_ROLES)}")
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
