"""Top-level API router aggregating all sub-routers."""

from fastapi import APIRouter

from app.api import (
    agent_config,
    analytics,
    appointments,
    audit_logs,
    calls,
    contacts,
    dashboard,
    departments,
    knowledge,
    messages,
    reminders,
    twilio_webhooks,
    users,
)

api_router = APIRouter()

# Core MVP routes
api_router.include_router(twilio_webhooks.router)
api_router.include_router(calls.router)
api_router.include_router(appointments.router)
api_router.include_router(contacts.router)
api_router.include_router(departments.router)
api_router.include_router(messages.router)
api_router.include_router(dashboard.router)

# Government Platform — Tier 1
api_router.include_router(agent_config.router)
api_router.include_router(audit_logs.router)
api_router.include_router(users.router)

# Government Platform — Tier 2 (Analytics & SLA)
api_router.include_router(analytics.router)
api_router.include_router(analytics.reports_router)

# Government Platform — Tier 3 (Knowledge Base, Reminders)
api_router.include_router(knowledge.router)
api_router.include_router(reminders.router)
