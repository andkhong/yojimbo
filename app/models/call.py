from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Call(Base):
    __tablename__ = "calls"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    twilio_call_sid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    contact_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("contacts.id"))
    direction: Mapped[str] = mapped_column(String(10))  # inbound / outbound
    status: Mapped[str] = mapped_column(String(20), default="ringing")
    detected_language: Mapped[str | None] = mapped_column(String(10))
    department_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("departments.id"))
    summary: Mapped[str | None] = mapped_column(Text)
    sentiment: Mapped[str | None] = mapped_column(String(20))
    resolution_status: Mapped[str | None] = mapped_column(String(20))  # resolved, escalated, abandoned
    partial_transcript: Mapped[str | None] = mapped_column(Text)  # live partial transcript
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    recording_url: Mapped[str | None] = mapped_column(String(512))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    contact = relationship("Contact", back_populates="calls")
    department = relationship("Department", back_populates="calls")
    events = relationship("CallEvent", back_populates="call", cascade="all, delete-orphan")
    conversation_turns = relationship(
        "ConversationTurn", back_populates="call", cascade="all, delete-orphan"
    )


class CallEvent(Base):
    __tablename__ = "call_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    call_id: Mapped[int] = mapped_column(Integer, ForeignKey("calls.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(50))
    detail: Mapped[str | None] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    call = relationship("Call", back_populates="events")


class ConversationTurn(Base):
    __tablename__ = "conversation_turns"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    call_id: Mapped[int] = mapped_column(Integer, ForeignKey("calls.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(10))  # caller / agent
    original_text: Mapped[str] = mapped_column(Text)
    translated_text: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(10))
    intent: Mapped[str | None] = mapped_column(String(50))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    call = relationship("Call", back_populates="conversation_turns")
