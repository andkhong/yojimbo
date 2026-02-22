"""Rate limiting middleware — token bucket per IP for public webhook endpoints.

Protects Twilio webhooks and any public-facing routes from abuse.
Uses a simple in-memory token bucket (resets on restart; suitable for single-instance).
For multi-instance deployments, swap the store for Redis.

Default limits:
  - Twilio webhook endpoints:  60 req/min per IP
  - Auth endpoints:             10 req/min per IP (brute-force protection)
  - API endpoints:             300 req/min per IP (generous for staff dashboards)
"""

import logging
import time
from collections import defaultdict
from threading import Lock

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Token bucket implementation
# ---------------------------------------------------------------------------


class _Bucket:
    """A single token bucket for one IP+path_prefix."""

    __slots__ = ("tokens", "last_refill", "capacity", "refill_rate")

    def __init__(self, capacity: int, refill_rate: float) -> None:
        self.capacity = capacity
        self.refill_rate = refill_rate  # tokens per second
        self.tokens = float(capacity)
        self.last_refill = time.monotonic()

    def consume(self) -> bool:
        """Try to consume one token. Returns True if allowed, False if rate-limited."""
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


class _BucketStore:
    """Thread-safe store of token buckets keyed by (ip, limit_key)."""

    def __init__(self) -> None:
        self._buckets: dict[str, _Bucket] = defaultdict(lambda: _Bucket(0, 0))
        self._lock = Lock()
        self._configs: dict[str, tuple[int, float]] = {}  # limit_key → (capacity, rate/s)

    def register(self, limit_key: str, capacity: int, per_seconds: int) -> None:
        rate = capacity / per_seconds
        self._configs[limit_key] = (capacity, rate)

    def consume(self, ip: str, limit_key: str) -> bool:
        if limit_key not in self._configs:
            return True  # unregistered = no limit
        capacity, rate = self._configs[limit_key]
        bucket_key = f"{limit_key}:{ip}"
        with self._lock:
            if bucket_key not in self._buckets:
                self._buckets[bucket_key] = _Bucket(capacity, rate)
            return self._buckets[bucket_key].consume()


_store = _BucketStore()
_store.register("twilio", capacity=60, per_seconds=60)  # 60/min
_store.register("auth", capacity=10, per_seconds=60)  # 10/min
_store.register("api", capacity=300, per_seconds=60)  # 300/min


def _classify(path: str) -> str | None:
    """Return rate limit key for a path, or None for unlimited."""
    if path.startswith("/api/twilio"):
        return "twilio"
    if path.startswith("/api/auth"):
        return "auth"
    if path.startswith("/api/"):
        return "api"
    return None  # static files, WS, page routes — no limit


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Apply token-bucket rate limits to configured path prefixes.

    Rate limiting is automatically disabled when DEBUG=true (development/test mode).
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        import os

        # Skip rate limiting in debug/test mode to prevent test interference
        # Check the env var directly to avoid stale cached settings object
        if os.getenv("DEBUG", "false").lower() in ("1", "true", "yes"):
            return await call_next(request)

        limit_key = _classify(request.url.path)
        if limit_key is None:
            return await call_next(request)

        ip = _client_ip(request)
        if not _store.consume(ip, limit_key):
            logger.warning(
                "Rate limit exceeded: ip=%s path=%s key=%s",
                ip,
                request.url.path,
                limit_key,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Too many requests — please slow down.",
                    "limit_key": limit_key,
                },
                headers={"Retry-After": "60"},
            )

        return await call_next(request)
