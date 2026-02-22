"""Audit log middleware — automatically logs mutating API calls to AuditLog table.

Intercepts all POST, PUT, PATCH, DELETE requests to /api/* paths and
creates an AuditLog entry after the response is returned (non-blocking).

Excluded paths (too chatty or read-only):
- /api/twilio/* (high-volume webhooks)
- /api/auth/* (handled separately)
- /api/health (read-only probes)
"""

import logging

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response as StarletteResponse

logger = logging.getLogger(__name__)

_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_EXCLUDED_PREFIXES = ("/api/twilio", "/api/auth", "/api/health")


def _should_audit(method: str, path: str) -> bool:
    if method not in _MUTATING_METHODS:
        return False
    for prefix in _EXCLUDED_PREFIXES:
        if path.startswith(prefix):
            return False
    if not path.startswith("/api/"):
        return False
    return True


def _action_for_method(method: str) -> str:
    return {
        "POST": "CREATE",
        "PUT": "UPDATE",
        "PATCH": "UPDATE",
        "DELETE": "DELETE",
    }.get(method, method)


def _resource_type_from_path(path: str) -> str:
    """Infer resource type from URL path, e.g. /api/departments/3 → department."""
    parts = [p for p in path.split("/") if p]
    # parts[0] == 'api', parts[1] == resource name
    if len(parts) >= 2:
        resource = parts[1].rstrip("s")  # naive depluralization
        return resource
    return "unknown"


def _resource_id_from_path(path: str) -> str | None:
    """Extract the numeric resource ID from the URL if present."""
    parts = [p for p in path.split("/") if p]
    # /api/departments/3 → parts = ['api', 'departments', '3']
    if len(parts) >= 3:
        candidate = parts[2]
        if candidate.isdigit():
            return candidate
    return None


class AuditLogMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that creates audit log entries for mutating API calls."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> StarletteResponse:
        method = request.method
        path = request.url.path

        if not _should_audit(method, path):
            return await call_next(request)

        # Proceed with the request
        response = await call_next(request)

        # Only log successful mutations (2xx)
        if response.status_code < 200 or response.status_code >= 300:
            return response

        # Create audit log entry in the background (best-effort)
        try:
            from app.database import async_session_factory
            from app.models.audit_log import AuditLog

            # Extract session user from cookie-based session (if any)
            user_id: int | None = None
            username: str | None = None
            if hasattr(request, "session"):
                user_id = request.session.get("user_id")

            # Client IP
            forwarded_for = request.headers.get("x-forwarded-for")
            ip = (
                forwarded_for.split(",")[0].strip()
                if forwarded_for
                else (request.client.host if request.client else None)
            )

            async with async_session_factory() as session:
                log = AuditLog(
                    user_id=user_id,
                    username=username,
                    action=_action_for_method(method),
                    resource_type=_resource_type_from_path(path),
                    resource_id=_resource_id_from_path(path),
                    ip_address=ip,
                    endpoint=f"{method} {path}",
                )
                session.add(log)
                await session.commit()

        except Exception as exc:
            # Never crash the response pipeline due to audit log failure
            logger.warning("Audit log middleware error: %s", exc)

        return response
