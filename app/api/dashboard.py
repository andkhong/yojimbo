"""Dashboard data and authentication API endpoints."""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import authenticate_user, get_current_user, hash_password
from app.database import get_db
from app.models.appointment import Appointment
from app.models.call import Call
from app.models.contact import Contact
from app.models.message import SMSMessage
from app.models.user import DashboardUser
from app.schemas.auth import LoginRequest, UserResponse
from app.schemas.dashboard import ActivityItem, DashboardStats

router = APIRouter(tags=["dashboard"])


@router.post("/api/auth/login")
async def login(
    data: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user = await authenticate_user(db, data.username, data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    request.session["user_id"] = user.id
    return {"user": UserResponse.model_validate(user)}


@router.post("/api/auth/logout")
async def logout(request: Request):
    request.session.clear()
    return {"message": "Logged out"}


@router.get("/api/auth/me")
async def get_me(user: DashboardUser = Depends(get_current_user)):
    return {"user": UserResponse.model_validate(user)}


@router.get("/api/dashboard/stats")
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)):
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    # Today's calls
    today_calls = (
        await db.execute(
            select(func.count()).where(Call.started_at >= today_start)
        )
    ).scalar() or 0

    # Active calls
    active_calls = (
        await db.execute(
            select(func.count()).where(Call.status.in_(["ringing", "in_progress"]))
        )
    ).scalar() or 0

    # Today's appointments
    today_appts = (
        await db.execute(
            select(func.count()).where(
                Appointment.scheduled_start >= today_start,
                Appointment.scheduled_start < today_start + timedelta(days=1),
                Appointment.status == "confirmed",
            )
        )
    ).scalar() or 0

    # Total contacts
    total_contacts = (
        await db.execute(select(func.count()).select_from(Contact))
    ).scalar() or 0

    # Language breakdown from today's calls
    lang_rows = (
        await db.execute(
            select(Call.detected_language, func.count())
            .where(Call.started_at >= today_start, Call.detected_language.isnot(None))
            .group_by(Call.detected_language)
        )
    ).all()
    language_breakdown = {row[0]: row[1] for row in lang_rows}

    # Average call duration
    avg_duration = (
        await db.execute(
            select(func.avg(Call.duration_seconds)).where(
                Call.duration_seconds.isnot(None),
                Call.started_at >= today_start,
            )
        )
    ).scalar() or 0.0

    return DashboardStats(
        today_calls=today_calls,
        active_calls=active_calls,
        today_appointments=today_appts,
        total_contacts=total_contacts,
        language_breakdown=language_breakdown,
        avg_call_duration=round(float(avg_duration), 1),
    )


@router.get("/api/dashboard/activity")
async def get_activity_feed(
    db: AsyncSession = Depends(get_db),
    limit: int = 20,
):
    activities: list[ActivityItem] = []

    # Recent calls
    calls = (
        await db.execute(
            select(Call).order_by(Call.started_at.desc()).limit(limit)
        )
    ).scalars().all()
    for c in calls:
        activities.append(
            ActivityItem(
                type="call",
                description=f"{'Inbound' if c.direction == 'inbound' else 'Outbound'} call ({c.status})",
                timestamp=c.started_at.isoformat(),
                language=c.detected_language,
                status=c.status,
            )
        )

    # Recent appointments
    appts = (
        await db.execute(
            select(Appointment).order_by(Appointment.created_at.desc()).limit(limit)
        )
    ).scalars().all()
    for a in appts:
        activities.append(
            ActivityItem(
                type="appointment",
                description=f"Appointment: {a.title} ({a.status})",
                timestamp=a.created_at.isoformat(),
                language=a.language,
                status=a.status,
            )
        )

    # Recent SMS
    messages = (
        await db.execute(
            select(SMSMessage).order_by(SMSMessage.created_at.desc()).limit(limit)
        )
    ).scalars().all()
    for m in messages:
        direction = "Received" if m.direction == "inbound" else "Sent"
        activities.append(
            ActivityItem(
                type="sms",
                description=f"SMS {direction}: {m.body[:60]}...",
                timestamp=m.created_at.isoformat(),
                language=m.detected_language,
                status=m.status,
            )
        )

    activities.sort(key=lambda a: a.timestamp, reverse=True)
    return {"activities": activities[:limit]}
