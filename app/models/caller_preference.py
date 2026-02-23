"""CallerPreference model — persistent per-caller preferences stored by phone number.

Allows callers to have their language, accessibility needs, and communication
preferences remembered across calls. Updated automatically during calls when
the caller confirms or changes preferences.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CallerPreference(Base):
    __tablename__ = "caller_preferences"
    __table_args__ = (Index("ix_caller_pref_phone", "phone_number"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Caller identifier
    phone_number: Mapped[str] = mapped_column(String(20), unique=True, index=True)

    # Language + communication preferences
    preferred_language: Mapped[str] = mapped_column(String(10), default="en")
    name: Mapped[str | None] = mapped_column(String(255))
    preferred_department_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Accessibility
    hearing_impaired: Mapped[bool] = mapped_column(Boolean, default=False)
    speech_impaired: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_interpreter: Mapped[bool] = mapped_column(Boolean, default=False)

    # Communication channel preferences
    sms_opt_in: Mapped[bool] = mapped_column(Boolean, default=True)
    email_opt_in: Mapped[bool] = mapped_column(Boolean, default=False)
    preferred_reminder_hours: Mapped[int] = mapped_column(Integer, default=24)

    # Extra context (JSON)
    notes: Mapped[str | None] = mapped_column(Text)

    call_count: Mapped[int] = mapped_column(Integer, default=0)
    last_call_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
