"""Audit Log API — government compliance trail with auto-logging middleware."""

import json
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.audit_log import AuditLog
from app.schemas.audit_log import AuditLogListResponse, AuditLogResponse

router = APIRouter(prefix="/api/audit-logs", tags=["audit-logs"])


@router.get("", summary="List audit logs (paginated, filterable)")
async def list_audit_logs(
    db: AsyncSession = Depends(get_db),
    user_id: int | None = None,
    username: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
) -> AuditLogListResponse:
    """Return paginated audit logs with optional filters."""
    query = select(AuditLog).order_by(AuditLog.created_at.desc())

    if user_id is not None:
        query = query.where(AuditLog.user_id == user_id)
    if username:
        query = query.where(AuditLog.username.ilike(f"%{username}%"))
    if action:
        query = query.where(AuditLog.action == action.upper())
    if resource_type:
        query = query.where(AuditLog.resource_type == resource_type)
    if resource_id:
        query = query.where(AuditLog.resource_id == resource_id)
    if date_from:
        query = query.where(AuditLog.created_at >= datetime.fromisoformat(date_from))
    if date_to:
        query = query.where(AuditLog.created_at <= datetime.fromisoformat(date_to))

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = query.offset((page - 1) * per_page).limit(per_page)
    logs = (await db.execute(query)).scalars().all()

    return AuditLogListResponse(
        logs=[AuditLogResponse.model_validate(log) for log in logs],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/summary", summary="Audit log summary statistics")
async def audit_log_summary(db: AsyncSession = Depends(get_db)):
    """Return counts of actions grouped by type."""
    rows = (await db.execute(
        select(AuditLog.action, func.count()).group_by(AuditLog.action)
    )).all()
    resource_rows = (await db.execute(
        select(AuditLog.resource_type, func.count()).group_by(AuditLog.resource_type)
    )).all()
    total = (await db.execute(select(func.count()).select_from(AuditLog))).scalar() or 0
    return {
        "total": total,
        "by_action": {row[0]: row[1] for row in rows},
        "by_resource": {row[0]: row[1] for row in resource_rows},
    }


@router.get("/{log_id}", summary="Get a single audit log entry")
async def get_audit_log(log_id: int, db: AsyncSession = Depends(get_db)) -> AuditLogResponse:
    """Return a single audit log entry by ID."""
    log = (await db.execute(
        select(AuditLog).where(AuditLog.id == log_id)
    )).scalar_one_or_none()
    if not log:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Audit log entry not found")
    return AuditLogResponse.model_validate(log)


# ---------------------------------------------------------------------------
# Helper used by other modules to create audit log entries
# ---------------------------------------------------------------------------

async def create_audit_entry(
    db: AsyncSession,
    *,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    old_value: dict | None = None,
    new_value: dict | None = None,
    user_id: int | None = None,
    username: str | None = None,
    ip_address: str | None = None,
    endpoint: str | None = None,
) -> AuditLog:
    """Create and persist an AuditLog entry. Returns the unsaved ORM object (caller must flush)."""
    log = AuditLog(
        user_id=user_id,
        username=username,
        action=action.upper(),
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        old_value=json.dumps(old_value) if old_value is not None else None,
        new_value=json.dumps(new_value) if new_value is not None else None,
        ip_address=ip_address,
        endpoint=endpoint,
    )
    db.add(log)
    return log
