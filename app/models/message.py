from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SMSMessage(Base):
    __tablename__ = "sms_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    twilio_message_sid: Mapped[str] = mapped_column(String(64), unique=True)
    contact_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("contacts.id"))
    direction: Mapped[str] = mapped_column(String(10))  # inbound / outbound
    body: Mapped[str] = mapped_column(Text)
    translated_body: Mapped[str | None] = mapped_column(Text)
    detected_language: Mapped[str | None] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), default="received")
    department_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("departments.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    contact = relationship("Contact", back_populates="messages")
