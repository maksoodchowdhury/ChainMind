from fastapi import APIRouter
import logging

from src.alerts import maybe_send_slo_alert
from src.document_processor import get_fingerprint_registry
from src.metrics import evaluate_slo_status, snapshot_metrics
from src.retention import apply_retention_policies

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/live")
async def liveness_check() -> dict:
    """Lightweight liveness endpoint for orchestrators."""
    from src.main import settings

    return {
        "status": "alive",
        "service": settings.app_name,
        "version": settings.app_version,
    }


@router.get("/ready")
async def readiness_check() -> dict:
    """Readiness endpoint that checks dependencies required to serve traffic."""
    from src.main import rag_pipeline, settings
    from src import cache as cache_module

    is_rag_ready = rag_pipeline.health_check()
    cache_status = "not_configured"
    if settings.redis_url:
        try:
            client = cache_module._get_client(settings.redis_url)
            if client:
                await client.ping()
                cache_status = "healthy"
            else:
                cache_status = "unavailable"
        except Exception:
            cache_status = "unavailable"

    mode = "normal"
    if is_rag_ready and cache_status == "unavailable":
        mode = "degraded"

    return {
        "status": "ready" if is_rag_ready else "not_ready",
        "mode": mode,
        "accepting_traffic": is_rag_ready,
        "service": settings.app_name,
        "version": settings.app_version,
        "components": {
            "qdrant": "healthy" if is_rag_ready else "unhealthy",
            "cache": cache_status,
        },
    }


@router.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    from src.main import rag_pipeline, settings
    from src import cache as cache_module

    is_rag_healthy = rag_pipeline.health_check()

    cache_status = "not_configured"
    if settings.redis_url:
        try:
            client = cache_module._get_client(settings.redis_url)
            if client:
                await client.ping()
                cache_status = "healthy"
            else:
                cache_status = "unavailable"
        except Exception:
            cache_status = "unavailable"

    fingerprints = get_fingerprint_registry()
    return {
        "status": "healthy" if is_rag_healthy else "unhealthy",
        "service": settings.app_name,
        "version": settings.app_version,
        "components": {
            "qdrant": "healthy" if is_rag_healthy else "unhealthy",
            "cache": cache_status,
            "indexed_files": len(fingerprints),
        },
    }


@router.get("/metrics/operational")
async def operational_metrics() -> dict:
    """Operational request metrics for SLO tracking and troubleshooting."""
    from src.main import settings

    return snapshot_metrics(settings.app_name, settings.app_version)


@router.get("/metrics/slo-status")
async def slo_status() -> dict:
    """Alert-friendly summary of whether current request SLOs are breached."""
    from src.main import settings

    snapshot = snapshot_metrics(settings.app_name, settings.app_version)
    status = evaluate_slo_status(
        snapshot,
        error_rate_threshold=settings.slo_error_rate_threshold,
        p95_latency_ms_threshold=settings.slo_p95_latency_ms_threshold,
        minimum_requests=settings.slo_minimum_requests,
    )
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "generated_at": snapshot.get("generated_at"),
        **status,
    }


@router.post("/alerts/slo/check")
async def check_and_notify_slo() -> dict:
    """Evaluate SLO status and optionally notify a configured webhook on breach."""
    from src.main import settings

    snapshot = snapshot_metrics(settings.app_name, settings.app_version)
    slo = evaluate_slo_status(
        snapshot,
        error_rate_threshold=settings.slo_error_rate_threshold,
        p95_latency_ms_threshold=settings.slo_p95_latency_ms_threshold,
        minimum_requests=settings.slo_minimum_requests,
    )
    notification = maybe_send_slo_alert(
        webhook_url=settings.slo_webhook_url,
        webhook_secret=settings.slo_webhook_secret,
        cooldown_seconds=settings.slo_alert_cooldown_seconds,
        max_attempts=settings.slo_webhook_max_attempts,
        backoff_seconds=settings.slo_webhook_backoff_seconds,
        slo_status=slo,
        service=settings.app_name,
        version=settings.app_version,
    )

    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "generated_at": snapshot.get("generated_at"),
        "slo": slo,
        "notification": notification,
    }


@router.delete("/cache")
async def clear_cache() -> dict:
    """Invalidate all cached query results."""
    from src.main import settings
    from src import cache as cache_module

    if not settings.redis_url:
        return {"status": "cache_not_configured", "deleted": 0}

    deleted = await cache_module.invalidate_all(settings.redis_url)
    logger.info(f"Cache cleared: {deleted} keys removed")
    return {"status": "cleared", "deleted": deleted}


@router.post("/maintenance/retention/run")
async def run_retention_maintenance() -> dict:
    """Apply retention policies for uploads and governance history."""
    from src.main import settings

    result = apply_retention_policies(
        retention_days_uploads=settings.retention_days_uploads,
        retention_days_catalog_history=settings.retention_days_catalog_history,
    )
    return {"status": "completed", **result}
