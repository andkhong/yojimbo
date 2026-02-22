"""Health check API — database and service status."""

import logging
import time as _time
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("", summary="Basic liveness check")
async def health_check():
    """Quick liveness probe — returns 200 if the process is alive."""
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "yojimbo",
    }


@router.get("/db", summary="Database connectivity check")
async def db_health(db: AsyncSession = Depends(get_db)):
    """Check database connectivity by running a trivial query."""
    start = _time.monotonic()
    try:
        await db.execute(text("SELECT 1"))
        latency_ms = round((_time.monotonic() - start) * 1000, 2)
        return {
            "status": "ok",
            "db_latency_ms": latency_ms,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as exc:
        logger.error("DB health check failed: %s", exc)
        return {
            "status": "error",
            "detail": str(exc),
            "timestamp": datetime.utcnow().isoformat(),
        }


@router.get("/twilio", summary="Twilio connectivity check")
async def twilio_health():
    """Verify Twilio credentials by fetching account details."""
    try:
        from app.config import settings
        from twilio.rest import Client

        start = _time.monotonic()
        client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        account = client.api.accounts(settings.twilio_account_sid).fetch()
        latency_ms = round((_time.monotonic() - start) * 1000, 2)
        return {
            "status": "ok",
            "account_status": account.status,
            "latency_ms": latency_ms,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as exc:
        logger.warning("Twilio health check failed: %s", exc)
        return {
            "status": "unavailable",
            "detail": str(exc),
            "timestamp": datetime.utcnow().isoformat(),
        }


@router.get("/full", summary="Full system health check")
async def full_health(db: AsyncSession = Depends(get_db)):
    """Run all health checks and return a combined status."""
    overall = "ok"
    checks: dict = {}

    # DB check
    start = _time.monotonic()
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = {
            "status": "ok",
            "latency_ms": round((_time.monotonic() - start) * 1000, 2),
        }
    except Exception as exc:
        checks["database"] = {"status": "error", "detail": str(exc)}
        overall = "degraded"

    # Twilio check (non-blocking, catch all)
    try:
        from app.config import settings
        from twilio.rest import Client

        start = _time.monotonic()
        client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        client.api.accounts(settings.twilio_account_sid).fetch()
        checks["twilio"] = {
            "status": "ok",
            "latency_ms": round((_time.monotonic() - start) * 1000, 2),
        }
    except Exception as exc:
        checks["twilio"] = {"status": "unavailable", "detail": str(exc)}
        # Twilio down = degraded, not down

    return {
        "status": overall,
        "checks": checks,
        "timestamp": datetime.utcnow().isoformat(),
    }
