"""Top-level API router aggregating all sub-routers."""

from fastapi import APIRouter

from app.api import appointments, calls, contacts, dashboard, departments, messages, twilio_webhooks

api_router = APIRouter()

api_router.include_router(twilio_webhooks.router)
api_router.include_router(calls.router)
api_router.include_router(appointments.router)
api_router.include_router(contacts.router)
api_router.include_router(departments.router)
api_router.include_router(messages.router)
api_router.include_router(dashboard.router)
