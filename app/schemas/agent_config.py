"""AgentConfig schemas."""

from datetime import datetime

from pydantic import BaseModel, field_validator

from app.models.agent_config import VALID_CONFIG_KEYS


class AgentConfigEntry(BaseModel):
    id: int
    key: str
    value: str
    description: str | None = None
    updated_by: str | None = None
    updated_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class AgentConfigUpdate(BaseModel):
    """Update one or more config values."""

    updates: dict[str, str]
    updated_by: str | None = None

    @field_validator("updates")
    @classmethod
    def validate_keys(cls, v: dict[str, str]) -> dict[str, str]:
        invalid = set(v.keys()) - VALID_CONFIG_KEYS
        if invalid:
            raise ValueError(f"Invalid config keys: {invalid}. Valid keys: {VALID_CONFIG_KEYS}")
        return v


class AgentConfigResponse(BaseModel):
    config: dict[str, str]
    entries: list[AgentConfigEntry]
