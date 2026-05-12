import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from src.config import get_settings
from src.rag_pipeline import RAGPipeline
from src.auth import APIKeyMiddleware
from src.tracer import setup_tracing
from src.api_health import router as health_router
from src.api_documents import router as documents_router
from src.api_query import router as query_router
from src.api_eval import router as eval_router

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
    logger.info("Starting SupplyChain RAG Assistant v%s...", settings.app_version)
    try:
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
    logger.info("Shutting down SupplyChain RAG Assistant...")
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

# Include routers
app.include_router(health_router)
app.include_router(documents_router)
app.include_router(query_router)
app.include_router(eval_router)

# Serve the built-in UI at /ui
app.mount("/ui", StaticFiles(directory="src/ui", html=True), name="ui")


@app.get("/")
async def root() -> dict:
    """Root endpoint."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "endpoints": {
            "health": "/health",
            "upload": "/api/documents/upload",
            "job_status": "/api/documents/status/{job_id}",
            "list_documents": "/api/documents/list",
            "query": "/api/query/",
            "query_stream": "/api/query/stream",
            "evaluate": "/api/eval/",
            "query_and_eval": "/api/eval/query-and-eval",
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
