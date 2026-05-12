from fastapi import APIRouter
import logging

from src.document_processor import get_fingerprint_registry

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


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
        "service": "SupplyChain RAG Assistant",
        "version": "0.2.0",
        "components": {
            "qdrant": "healthy" if is_rag_healthy else "unhealthy",
            "cache": cache_status,
            "indexed_files": len(fingerprints),
        },
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
