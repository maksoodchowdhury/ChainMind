import json
import logging
import time
import uuid
from collections import deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from src.metrics import record_request
from src.tenant_control import record_usage, would_exceed_quota

logger = logging.getLogger(__name__)

EXEMPT_PATHS = frozenset({
    "/",
    "/live",
    "/ready",
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/ui",
})

EXEMPT_PREFIXES = (
    "/docs/",
    "/redoc/",
    "/ui/",
)


def _is_exempt(path: str) -> bool:
    return path in EXEMPT_PATHS or any(path.startswith(prefix) for prefix in EXEMPT_PREFIXES)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a request correlation ID to every response."""

    async def dispatch(self, request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Emit structured logs for each request."""

    def __init__(self, app, enabled: bool = True):
        super().__init__(app)
        self._enabled = enabled

    async def dispatch(self, request, call_next):
        if not self._enabled:
            return await call_next(request)

        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - started) * 1000.0

        payload = {
            "event": "http_request",
            "request_id": getattr(request.state, "request_id", None),
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round(duration_ms, 2),
            "client_ip": request.client.host if request.client else "unknown",
        }
        record_request(
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        logger.info(json.dumps(payload, separators=(",", ":")))
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory fixed-window rate limiter per API key or client IP."""

    def __init__(
        self,
        app,
        enabled: bool = False,
        requests_per_window: int = 60,
        window_seconds: int = 60,
    ):
        super().__init__(app)
        self._enabled = enabled
        self._requests_per_window = max(1, requests_per_window)
        self._window_seconds = max(1, window_seconds)
        self._requests: dict[str, deque[float]] = {}

    def _bucket_key(self, request) -> str:
        api_key = request.headers.get("X-API-Key", "").strip()
        if api_key:
            return f"api_key:{api_key}"
        client_ip = request.client.host if request.client else "unknown"
        return f"ip:{client_ip}"

    async def dispatch(self, request, call_next):
        if not self._enabled or _is_exempt(request.url.path):
            return await call_next(request)

        now = time.time()
        cutoff = now - self._window_seconds
        key = self._bucket_key(request)
        bucket = self._requests.setdefault(key, deque())

        while bucket and bucket[0] < cutoff:
            bucket.popleft()

        if len(bucket) >= self._requests_per_window:
            retry_after = max(1, int(bucket[0] + self._window_seconds - now))
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": str(retry_after)},
                content={
                    "detail": "Rate limit exceeded. Please retry later.",
                    "request_limit": self._requests_per_window,
                    "window_seconds": self._window_seconds,
                },
            )

        bucket.append(now)
        return await call_next(request)


class TenantQuotaMiddleware(BaseHTTPMiddleware):
    """Tenant-level quota guardrail to prevent noisy-neighbor impact."""

    def __init__(self, app, enabled: bool = False):
        super().__init__(app)
        self._enabled = enabled

    async def dispatch(self, request, call_next):
        if not self._enabled or _is_exempt(request.url.path):
            return await call_next(request)

        tenant_id = request.headers.get("X-Tenant-ID", "").strip()
        if not tenant_id:
            return await call_next(request)

        exceeded, status = would_exceed_quota(tenant_id, requested_units=1)
        if exceeded:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Tenant quota exceeded",
                    "tenant_id": tenant_id,
                    "quota": status.get("quota", {}),
                    "usage": status.get("usage", {}),
                },
            )

        response = await call_next(request)
        # Count only successful and accepted requests toward tenant consumption.
        if response.status_code < 500:
            record_usage(tenant_id, units=1)
        return response
