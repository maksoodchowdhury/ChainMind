"""RBAC + tenant-aware authorization middleware."""

from __future__ import annotations

from dataclasses import dataclass
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from src.audit import audit_event

SAFE_EXEMPT = frozenset({"/", "/live", "/ready", "/health", "/docs", "/redoc", "/openapi.json", "/ui"})
SAFE_PREFIX = ("/docs/", "/redoc/", "/ui/")


@dataclass(frozen=True)
class Policy:
    min_role: str
    tenant_scoped: bool = True


ROLE_LEVEL = {
    "viewer": 1,
    "analyst": 2,
    "admin": 3,
}

ROUTE_POLICIES: list[tuple[str, Policy]] = [
    ("/api/documents/upload", Policy(min_role="analyst", tenant_scoped=True)),
    ("/api/documents/catalog", Policy(min_role="analyst", tenant_scoped=True)),
    ("/api/documents", Policy(min_role="viewer", tenant_scoped=True)),
    ("/api/query", Policy(min_role="viewer", tenant_scoped=True)),
    ("/api/eval", Policy(min_role="analyst", tenant_scoped=True)),
    ("/api/intelligence", Policy(min_role="analyst", tenant_scoped=True)),
    ("/metrics", Policy(min_role="admin", tenant_scoped=False)),
    ("/alerts", Policy(min_role="admin", tenant_scoped=False)),
]


def _is_exempt(path: str) -> bool:
    return path in SAFE_EXEMPT or any(path.startswith(p) for p in SAFE_PREFIX)


def _match_policy(path: str) -> Policy | None:
    for prefix, policy in ROUTE_POLICIES:
        if path.startswith(prefix):
            return policy
    return None


class AuthorizationMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        *,
        enabled: bool = False,
        require_tenant_header: bool = False,
        valid_roles: set[str] | None = None,
    ):
        super().__init__(app)
        self._enabled = enabled
        self._require_tenant = require_tenant_header
        self._valid_roles = valid_roles or {"admin", "analyst", "viewer"}

    async def dispatch(self, request: Request, call_next):
        if not self._enabled or _is_exempt(request.url.path):
            return await call_next(request)

        role = request.headers.get("X-Role", "viewer").strip().lower()
        tenant_id = request.headers.get("X-Tenant-ID", "").strip()

        if role not in self._valid_roles:
            audit_event(
                "authz_rejected",
                {"path": request.url.path, "role": role, "reason": "invalid_role"},
            )
            return JSONResponse(status_code=403, content={"detail": f"Role '{role}' is not allowed"})

        policy = _match_policy(request.url.path)
        if not policy:
            return await call_next(request)

        # Tenant-aware authorization guardrail
        if (self._require_tenant or policy.tenant_scoped) and not tenant_id:
            audit_event(
                "authz_rejected",
                {"path": request.url.path, "role": role, "reason": "missing_tenant"},
            )
            return JSONResponse(status_code=400, content={"detail": "X-Tenant-ID header is required"})

        if ROLE_LEVEL.get(role, 0) < ROLE_LEVEL.get(policy.min_role, 999):
            audit_event(
                "authz_rejected",
                {
                    "path": request.url.path,
                    "role": role,
                    "tenant_id": tenant_id,
                    "reason": "insufficient_role",
                },
            )
            return JSONResponse(
                status_code=403,
                content={
                    "detail": f"Insufficient role. Required>={policy.min_role}, got={role}",
                    "path": request.url.path,
                },
            )

        request.state.tenant_id = tenant_id or None
        request.state.role = role
        audit_event(
            "authz_accepted",
            {
                "path": request.url.path,
                "role": role,
                "tenant_id": tenant_id,
            },
        )
        return await call_next(request)
