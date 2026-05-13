import logging
from fastapi import FastAPI
from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from src.config import get_settings
from src.rag_pipeline import RAGPipeline
from src.auth import APIKeyMiddleware
from src.authz import AuthorizationMiddleware
from src.tracer import setup_tracing
from src.errors import error_payload
from src.middleware import (
    RequestIDMiddleware,
    RequestLoggingMiddleware,
    RateLimitMiddleware,
    TenantQuotaMiddleware,
)
from src.api_health import router as health_router
from src.api_documents import router as documents_router
from src.api_query import router as query_router
from src.api_eval import router as eval_router
from src.api_intelligence import router as intelligence_router
from src.api_platform import router as platform_router
from src.api_autonomy import router as autonomy_router

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Initialize settings and RAG pipeline
settings = get_settings()
rag_pipeline = RAGPipeline(settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown."""
    logger.info("Starting %s v%s...", settings.app_name, settings.app_version)
    try:
        if settings.enforce_transport_security and not settings.debug:
            if settings.qdrant_connection_url.startswith("http://"):
                raise RuntimeError(
                    "Transport security enforcement is enabled but Qdrant URL is not TLS (https)."
                )

        setup_tracing(
            service_name=settings.app_name,
            otlp_endpoint=settings.otlp_endpoint,
            enabled=settings.enable_tracing,
        )
        # initialize() now recovers the existing index from Qdrant automatically
        rag_pipeline.initialize()
    except Exception as e:
        logger.error(f"Startup failed: {e}")
        raise
    yield
    logger.info("Shutting down %s...", settings.app_name)
# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="RAG API for supply chain decision support",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add API key authentication middleware
app.add_middleware(
    APIKeyMiddleware,
    valid_keys=settings.valid_api_keys,
    enabled=settings.auth_enabled,
)

# Add role-based + tenant-aware authorization guardrails
app.add_middleware(
    AuthorizationMiddleware,
    enabled=settings.authz_enabled,
    require_tenant_header=settings.require_tenant_header,
    valid_roles=settings.valid_roles,
)

# Add basic rate limiting guardrails for production hardening
app.add_middleware(
    RateLimitMiddleware,
    enabled=settings.rate_limit_enabled,
    requests_per_window=settings.rate_limit_requests_per_window,
    window_seconds=settings.rate_limit_window_seconds,
)

# Add tenant-level quota guardrails for multi-tenant fairness
app.add_middleware(
    TenantQuotaMiddleware,
    enabled=settings.tenant_quota_enabled,
)

# Add request correlation IDs for observability across services
app.add_middleware(RequestIDMiddleware)

# Add structured request logging
app.add_middleware(
    RequestLoggingMiddleware,
    enabled=settings.enable_structured_logging,
)

# Include routers
app.include_router(health_router)
app.include_router(documents_router)
app.include_router(query_router)
app.include_router(eval_router)
app.include_router(intelligence_router)
app.include_router(platform_router)
app.include_router(autonomy_router)

# Serve the built-in UI at /ui
app.mount("/ui", StaticFiles(directory="src/ui", html=True), name="ui")


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    request_id = getattr(request.state, "request_id", None)
    message = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return JSONResponse(
        status_code=exc.status_code,
        headers=exc.headers,
        content=error_payload(
            request_id=request_id,
            code=f"http_{exc.status_code}",
            message=message,
            details=exc.detail if not isinstance(exc.detail, str) else None,
        ),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=422,
        content=error_payload(
            request_id=request_id,
            code="validation_error",
            message="Invalid request payload",
            details=exc.errors(),
        ),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", None)
    logger.exception("Unhandled exception while serving request", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content=error_payload(
            request_id=request_id,
            code="internal_server_error",
            message="An unexpected error occurred",
        ),
    )


@app.get("/")
async def root() -> dict:
    """Root endpoint."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "endpoints": {
            "live": "/live",
            "ready": "/ready",
            "health": "/health",
            "operational_metrics": "/metrics/operational",
            "slo_status": "/metrics/slo-status",
            "slo_alert_check": "/alerts/slo/check",
            "retention_maintenance": "/maintenance/retention/run",
            "upload": "/api/documents/upload",
            "ingestion_events": "/api/documents/events",
            "ingestion_dlq": "/api/documents/events-dlq",
            "job_status": "/api/documents/status/{job_id}",
            "list_documents": "/api/documents/list",
            "query": "/api/query/",
            "query_stream": "/api/query/stream",
            "evaluate": "/api/eval/",
            "query_and_eval": "/api/eval/query-and-eval",
            "reasoning_packs": "/api/intelligence/packs",
            "scenarios": "/api/intelligence/scenarios",
            "workflows": "/api/intelligence/workflows",
            "hitl_queue": "/api/intelligence/hitl",
            "platform": "/api/platform",
            "autonomy": "/api/autonomy",
            "ui": "/ui",
            "docs": "/docs",
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=settings.log_level.lower(),
    )
