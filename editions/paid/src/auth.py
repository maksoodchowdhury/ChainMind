"""
API-key authentication middleware.

Configuration
─────────────
Set AUTH_ENABLED=true and API_KEYS=key1,key2,key3 in your .env file.
Leave AUTH_ENABLED=false (the default) for local development.

How it works
────────────
Every request must carry the header:
    X-API-Key: <your-key>

Certain paths are always allowed without a key (see EXEMPT_PATHS).
Invalid or missing keys receive HTTP 401 with a JSON body.
"""

import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from src.audit import audit_event

logger = logging.getLogger(__name__)

EXEMPT_PATHS = frozenset({
    "/",
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


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that validates X-API-Key on every protected route."""

    def __init__(self, app, valid_keys: set[str], enabled: bool = True):
        super().__init__(app)
        self._keys = valid_keys
        self._enabled = enabled
        if enabled:
            logger.info(f"API key auth ENABLED ({len(valid_keys)} key(s) configured)")
        else:
            logger.info("API key auth DISABLED (AUTH_ENABLED=false)")

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if (
            not self._enabled
            or path in EXEMPT_PATHS
            or any(path.startswith(prefix) for prefix in EXEMPT_PREFIXES)
        ):
            return await call_next(request)

        key = request.headers.get("X-API-Key", "").strip()
        if not key or key not in self._keys:
            logger.warning(
                f"Rejected {request.method} {request.url.path} — "
                f"invalid or missing API key"
            )
            audit_event(
                "authn_rejected",
                {
                    "method": request.method,
                    "path": request.url.path,
                    "reason": "invalid_or_missing_api_key",
                },
            )
            return JSONResponse(
                status_code=401,
                content={
                    "detail": (
                        "Invalid or missing API key. "
                        "Provide the X-API-Key header with a valid key."
                    )
                },
            )
        audit_event(
            "authn_accepted",
            {
                "method": request.method,
                "path": request.url.path,
            },
        )
        return await call_next(request)
