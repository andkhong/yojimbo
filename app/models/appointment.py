from datetime import datetime, time

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    contact_id: Mapped[int] = mapped_column(Integer, ForeignKey("contacts.id"))
    department_id: Mapped[int] = mapped_column(Integer, ForeignKey("departments.id"))
    staff_member_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("staff_members.id"))
    call_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("calls.id"))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="confirmed")
    scheduled_start: Mapped[datetime] = mapped_column(DateTime, index=True)
    scheduled_end: Mapped[datetime] = mapped_column(DateTime)
    language: Mapped[str] = mapped_column(String(10), default="en")
    reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    contact = relationship("Contact", back_populates="appointments")
    department = relationship("Department", back_populates="appointments")


class TimeSlot(Base):
    __tablename__ = "time_slots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    department_id: Mapped[int] = mapped_column(Integer, ForeignKey("departments.id"))
    day_of_week: Mapped[int] = mapped_column(Integer)  # 0=Monday, 6=Sunday
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    slot_duration_minutes: Mapped[int] = mapped_column(Integer, default=30)
    max_concurrent: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    department = relationship("Department", back_populates="time_slots")
