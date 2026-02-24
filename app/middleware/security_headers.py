"""Security headers middleware — CORS preflight + Content Security Policy.

Adds government-appropriate security headers to all responses:
  - Content-Security-Policy (strict; allows Twilio + Google APIs)
  - Strict-Transport-Security (HSTS, 1 year)
  - X-Content-Type-Options
  - X-Frame-Options
  - Referrer-Policy
  - Permissions-Policy

CORS is handled for /api/* endpoints to support:
  - The admin dashboard SPA (same-origin or configured origin)
  - External government integrations that use the REST API

Configure allowed origins via the CORS_ALLOWED_ORIGINS env var (comma-separated).
Defaults to '*' in debug mode, locked to explicit origins in production.
"""

import logging
import os
from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "  # allow inline scripts for dashboard
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: https:; "
    "connect-src 'self' https://api.twilio.com wss: ws:; "
    "object-src 'none'; "
    "form-action 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self';"
)

_HSTS = "max-age=31536000; includeSubDomains"
_FRAME = "DENY"
_CONTENT_TYPE = "nosniff"
_REFERRER = "strict-origin-when-cross-origin"
_PERMISSIONS = "geolocation=(), microphone=(), camera=(), payment=()"


def _normalize_origin(origin: str) -> str:
    """Normalize origin values for robust CORS allowlist matching.

    - trims whitespace
    - lowercases scheme/host
    - strips default ports (:80 for http, :443 for https)
    - strips trailing slash
    """
    candidate = origin.strip().rstrip("/")
    if not candidate:
        return ""

    parsed = urlparse(candidate)
    scheme = (parsed.scheme or "").lower()
    host = (parsed.hostname or "").lower()
    if not scheme or not host:
        return ""

    port = parsed.port
    is_default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)

    if port and not is_default_port:
        return f"{scheme}://{host}:{port}"
    return f"{scheme}://{host}"


def _get_allowed_origins() -> list[str]:
    raw = os.getenv("CORS_ALLOWED_ORIGINS", "")
    if not raw:
        return []

    normalized: list[str] = []
    for origin in raw.split(","):
        candidate = _normalize_origin(origin)
        if candidate and candidate not in normalized:
            normalized.append(candidate)
    return normalized


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers and handle CORS preflight for all responses."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        is_debug = os.getenv("DEBUG", "false").lower() in ("1", "true", "yes")
        allowed_origins = _get_allowed_origins()
        origin = request.headers.get("origin", "")

        # Handle CORS preflight (OPTIONS)
        if request.method == "OPTIONS" and origin:
            response = Response(status_code=204)
            self._add_cors_headers(response, origin, is_debug, allowed_origins)
            self._add_security_headers(response, is_debug)
            return response

        response = await call_next(request)

        # CORS headers for actual requests
        if origin:
            self._add_cors_headers(response, origin, is_debug, allowed_origins)

        # Security headers on all responses
        self._add_security_headers(response, is_debug)
        return response

    @staticmethod
    def _add_cors_headers(
        response: Response,
        origin: str,
        is_debug: bool,
        allowed_origins: list[str],
    ) -> None:
        """Add CORS headers based on debug mode and configured origins."""
        # Debug mode stays permissive for local/dev workflows.
        # Production requires explicit allowlist membership.
        normalized_origin = _normalize_origin(origin)
        if is_debug:
            allow_origin = True
        else:
            allow_origin = bool(allowed_origins) and normalized_origin in allowed_origins

        if allow_origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Methods"] = (
                "GET, POST, PUT, PATCH, DELETE, OPTIONS"
            )
            response.headers["Access-Control-Allow-Headers"] = (
                "Authorization, Content-Type, X-Requested-With"
            )
            response.headers["Access-Control-Max-Age"] = "3600"
            # Ensure shared caches vary CORS decisions by request Origin.
            existing_vary = response.headers.get("Vary", "")
            if existing_vary:
                vary_parts = [part.strip() for part in existing_vary.split(",") if part.strip()]
                if "Origin" not in vary_parts:
                    vary_parts.append("Origin")
                response.headers["Vary"] = ", ".join(vary_parts)
            else:
                response.headers["Vary"] = "Origin"

    @staticmethod
    def _add_security_headers(response: Response, is_debug: bool) -> None:
        """Add security headers. HSTS is omitted in debug mode."""
        response.headers["X-Content-Type-Options"] = _CONTENT_TYPE
        response.headers["X-Frame-Options"] = _FRAME
        response.headers["Referrer-Policy"] = _REFERRER
        response.headers["Permissions-Policy"] = _PERMISSIONS
        response.headers["Content-Security-Policy"] = _CSP
        if not is_debug:
            response.headers["Strict-Transport-Security"] = _HSTS
