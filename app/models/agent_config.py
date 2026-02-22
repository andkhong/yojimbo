"""AgentConfig model — stores AI agent configuration as key-value pairs."""

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Valid config keys
VALID_CONFIG_KEYS = {
    "system_prompt",
    "greeting_message",
    "max_turns",
    "escalation_phrase",
    "supported_languages",
    "voice_model",
    "language_detection_enabled",
    "transfer_phone_number",
    "after_hours_message",
    "timezone",
}


class AgentConfig(Base):
    __tablename__ = "agent_configs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    value: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    updated_by: Mapped[str | None] = mapped_column(String(100))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
