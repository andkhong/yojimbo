"""Public status page — no authentication required.

Provides a machine-readable and human-readable system status page suitable
for embedding in public-facing government portals.

Returns:
  - Overall system status (operational / degraded / outage)
  - Active calls count
  - Today's appointment count
  - Department availability (open/closed based on time + operating hours)
  - Service uptime indicator
"""

import json
import time as _time
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.appointment import Appointment
from app.models.call import Call
from app.models.department import Department

router = APIRouter(prefix="/api/status", tags=["status"])

# Server start time for uptime calculation
_SERVER_START = _time.monotonic()
_SERVER_START_DT = datetime.utcnow()


def _parse_hours(hours_str: str | None) -> dict | None:
    """Parse operating_hours JSON. Returns None if unparseable."""
    if not hours_str:
        return None
    try:
        return json.loads(hours_str)
    except (json.JSONDecodeError, TypeError):
        return None


def _dept_is_open(dept: Department, now: datetime) -> bool | None:
    """Return True/False if department is open now, or None if unknown.

    Supports same-day windows (09:00-17:00) and overnight windows
    (22:00-02:00) by checking current and previous day windows.
    """
    hours = _parse_hours(dept.operating_hours)
    if not hours:
        return None  # No hours configured — unknown

    day_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

    def _parse_window(day_key: str) -> tuple[int, int] | None:
        day_hours = hours.get(day_key)
        if not day_hours:
            return None
        try:
            open_h, open_m = map(int, day_hours.get("open", "09:00").split(":"))
            close_h, close_m = map(int, day_hours.get("close", "17:00").split(":"))
            return open_h * 60 + open_m, close_h * 60 + close_m
        except (ValueError, AttributeError):
            return None

    current_mins = now.hour * 60 + now.minute
    day_idx = now.weekday()

    # 1) Current day window.
    current_window = _parse_window(day_names[day_idx])
    if current_window:
        open_mins, close_mins = current_window
        if close_mins > open_mins:
            if open_mins <= current_mins < close_mins:
                return True
        else:
            # Overnight window starting today, e.g. 22:00 -> 02:00.
            if current_mins >= open_mins:
                return True

    # 2) Previous day overnight spillover into today.
    prev_window = _parse_window(day_names[(day_idx - 1) % 7])
    if prev_window:
        prev_open, prev_close = prev_window
        if prev_close <= prev_open and current_mins < prev_close:
            return True

    # If schedule exists but no window matched, department is closed.
    return False


@router.get(
    "",
    summary="Public system status page (no auth required)",
    description="Returns real-time operational status for the government receptionist system.",
)
async def public_status(db: AsyncSession = Depends(get_db)):
    """Public status endpoint — safe for embedding in city portal with no authentication."""
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # System metrics
    active_calls = (
        await db.execute(select(func.count()).where(Call.status.in_(["ringing", "in_progress"])))
    ).scalar() or 0

    today_calls = (
        await db.execute(select(func.count()).where(Call.started_at >= today_start))
    ).scalar() or 0

    today_appointments = (
        await db.execute(
            select(func.count()).where(
                Appointment.scheduled_start >= today_start,
                Appointment.scheduled_start < today_start + timedelta(days=1),
                Appointment.status == "confirmed",
            )
        )
    ).scalar() or 0

    # DB health check
    db_ok = True
    try:
        from sqlalchemy import text

        await db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    # Department availability
    depts = (
        (
            await db.execute(
                select(Department).where(Department.is_active.is_(True)).order_by(Department.name)
            )
        )
        .scalars()
        .all()
    )

    dept_status = []
    for dept in depts:
        is_open = _dept_is_open(dept, now)
        dept_status.append(
            {
                "id": dept.id,
                "name": dept.name,
                "code": dept.code,
                "status": "open" if is_open else ("closed" if is_open is False else "unknown"),
                "has_phone": dept.twilio_phone_number is not None,
            }
        )

    # Overall status
    if not db_ok:
        overall = "outage"
    elif active_calls > 50:
        overall = "high_load"
    else:
        overall = "operational"

    uptime_seconds = int(_time.monotonic() - _SERVER_START)

    return {
        "status": overall,
        "timestamp": now.isoformat(),
        "uptime_seconds": uptime_seconds,
        "uptime_since": _SERVER_START_DT.isoformat(),
        "services": {
            "database": "ok" if db_ok else "degraded",
            "ai_receptionist": "operational",
        },
        "metrics": {
            "active_calls": active_calls,
            "calls_today": today_calls,
            "appointments_today": today_appointments,
        },
        "departments": dept_status,
    }


@router.get("/ping", summary="Minimal liveness ping (no auth, no DB)")
async def ping():
    """Ultra-lightweight liveness probe — no database, no auth, instant response."""
    return {"status": "ok", "ts": datetime.utcnow().isoformat()}
