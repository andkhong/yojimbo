"""Yojimbo - Real-Time Multi-Lingual AI Agent Receptionist for Local Government."""

import logging
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta

from fastapi import Depends, FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.sessions import SessionMiddleware

from app.api.router import api_router
from app.config import settings
from app.database import get_db, init_db
from app.middleware.audit import AuditLogMiddleware
from app.models.appointment import Appointment
from app.models.call import Call
from app.models.contact import Contact
from app.models.department import Department
from app.services import notification
from app.ws.conversation_relay import handle_conversation_relay
from app.ws.dashboard import handle_dashboard_ws
from app.ws.manager import ConnectionManager
from app.ws.monitor import handle_monitor_ws

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Dashboard WebSocket manager
ws_manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    logger.info("Starting Yojimbo - %s", settings.office_name)
    await init_db()
    notification.set_ws_manager(ws_manager)
    logger.info("Database initialized")
    yield
    logger.info("Shutting down Yojimbo")


app = FastAPI(
    title="Yojimbo",
    description="Real-Time Multi-Lingual AI Agent Receptionist for Local Government",
    version="0.1.0",
    lifespan=lifespan,
)

# Middleware
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)
app.add_middleware(AuditLogMiddleware)

# Static files and templates
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# API routes
app.include_router(api_router)


# --- WebSocket endpoints ---


@app.websocket("/ws/conversation-relay")
async def ws_conversation_relay(websocket: WebSocket):
    await handle_conversation_relay(websocket)


@app.websocket("/ws/dashboard")
async def ws_dashboard(websocket: WebSocket):
    await handle_dashboard_ws(websocket, ws_manager)


@app.websocket("/ws/monitor")
async def ws_monitor(websocket: WebSocket):
    """Live-call monitor WebSocket. Broadcasts call events to admin dashboards."""
    await handle_monitor_ws(websocket)


# --- Server-rendered page routes ---


@app.get("/", response_class=HTMLResponse)
async def root():
    return RedirectResponse(url="/dashboard")


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request, db: AsyncSession = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login")

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    # Stats
    today_calls = (
        await db.execute(select(func.count()).where(Call.started_at >= today_start))
    ).scalar() or 0

    active_calls = (
        await db.execute(select(func.count()).where(Call.status.in_(["ringing", "in_progress"])))
    ).scalar() or 0

    today_appts = (
        await db.execute(
            select(func.count()).where(
                Appointment.scheduled_start >= today_start,
                Appointment.scheduled_start < today_start + timedelta(days=1),
                Appointment.status == "confirmed",
            )
        )
    ).scalar() or 0

    total_contacts = (await db.execute(select(func.count()).select_from(Contact))).scalar() or 0

    lang_rows = (
        await db.execute(
            select(Call.detected_language, func.count())
            .where(Call.started_at >= today_start, Call.detected_language.isnot(None))
            .group_by(Call.detected_language)
        )
    ).all()
    language_breakdown = {row[0]: row[1] for row in lang_rows}

    # Recent activity
    activities = []
    recent_calls = (
        (await db.execute(select(Call).order_by(Call.started_at.desc()).limit(10))).scalars().all()
    )
    for c in recent_calls:
        activities.append(
            {
                "type": "call",
                "description": f"{'Inbound' if c.direction == 'inbound' else 'Outbound'} call ({c.status})",
                "timestamp": c.started_at.isoformat(),
                "language": c.detected_language,
            }
        )

    recent_appts = (
        (await db.execute(select(Appointment).order_by(Appointment.created_at.desc()).limit(10)))
        .scalars()
        .all()
    )
    for a in recent_appts:
        activities.append(
            {
                "type": "appointment",
                "description": f"Appointment: {a.title} ({a.status})",
                "timestamp": a.created_at.isoformat(),
                "language": a.language,
            }
        )

    activities.sort(key=lambda x: x["timestamp"], reverse=True)

    return templates.TemplateResponse(
        "dashboard/index.html",
        {
            "request": request,
            "active_page": "dashboard",
            "office_name": settings.office_name,
            "stats": {
                "today_calls": today_calls,
                "active_calls": active_calls,
                "today_appointments": today_appts,
                "total_contacts": total_contacts,
            },
            "language_breakdown": language_breakdown,
            "activities": activities[:20],
        },
    )


@app.get("/dashboard/calls", response_class=HTMLResponse)
async def calls_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    status: str | None = None,
    page: int = 1,
    per_page: int = 20,
):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login")

    query = select(Call).order_by(Call.started_at.desc())
    if status:
        query = query.where(Call.status == status)

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0

    calls = (await db.execute(query.offset((page - 1) * per_page).limit(per_page))).scalars().all()

    calls_data = []
    for c in calls:
        calls_data.append(
            {
                "id": c.id,
                "direction": c.direction,
                "status": c.status,
                "detected_language": c.detected_language,
                "duration_seconds": c.duration_seconds,
                "summary": c.summary,
                "started_at": c.started_at.isoformat() if c.started_at else "",
            }
        )

    return templates.TemplateResponse(
        "dashboard/calls.html",
        {
            "request": request,
            "active_page": "calls",
            "office_name": settings.office_name,
            "calls": calls_data,
            "total": total,
            "page": page,
            "per_page": per_page,
        },
    )


@app.get("/dashboard/appointments", response_class=HTMLResponse)
async def appointments_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    target_date: str | None = None,
    department_id: int | None = None,
):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login")

    if not target_date:
        target_date = date.today().isoformat()

    query = select(Appointment).order_by(Appointment.scheduled_start)
    d = date.fromisoformat(target_date)
    query = query.where(
        Appointment.scheduled_start >= datetime.combine(d, datetime.min.time()),
        Appointment.scheduled_start < datetime.combine(d, datetime.max.time()),
    )
    if department_id:
        query = query.where(Appointment.department_id == department_id)

    appointments = (await db.execute(query)).scalars().all()
    departments = (
        (
            await db.execute(
                select(Department).where(Department.is_active.is_(True)).order_by(Department.name)
            )
        )
        .scalars()
        .all()
    )

    appts_data = []
    for a in appointments:
        appts_data.append(
            {
                "id": a.id,
                "title": a.title,
                "description": a.description,
                "status": a.status,
                "scheduled_start": a.scheduled_start.isoformat(),
                "scheduled_end": a.scheduled_end.isoformat(),
                "language": a.language,
            }
        )

    return templates.TemplateResponse(
        "dashboard/appointments.html",
        {
            "request": request,
            "active_page": "appointments",
            "office_name": settings.office_name,
            "appointments": appts_data,
            "departments": [{"id": d.id, "name": d.name} for d in departments],
            "target_date": target_date,
            "selected_dept": department_id,
        },
    )


@app.get("/dashboard/contacts", response_class=HTMLResponse)
async def contacts_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    search: str | None = None,
    page: int = 1,
    per_page: int = 20,
):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login")

    query = select(Contact).order_by(Contact.created_at.desc())
    if search:
        query = query.where(
            or_(
                Contact.name.ilike(f"%{search}%"),
                Contact.phone_number.ilike(f"%{search}%"),
                Contact.email.ilike(f"%{search}%"),
            )
        )

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0

    contacts = (
        (await db.execute(query.offset((page - 1) * per_page).limit(per_page))).scalars().all()
    )

    contacts_data = []
    for c in contacts:
        contacts_data.append(
            {
                "name": c.name,
                "phone_number": c.phone_number,
                "preferred_language": c.preferred_language,
                "email": c.email,
                "created_at": c.created_at.isoformat(),
            }
        )

    return templates.TemplateResponse(
        "dashboard/contacts.html",
        {
            "request": request,
            "active_page": "contacts",
            "office_name": settings.office_name,
            "contacts": contacts_data,
            "total": total,
            "page": page,
            "per_page": per_page,
            "search": search,
        },
    )
