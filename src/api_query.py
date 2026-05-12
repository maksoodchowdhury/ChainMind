import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/query", tags=["query"])


class QueryFilters(BaseModel):
    """Optional metadata filters scoping the search to a document subset."""

    supplier: Optional[str] = None
    doc_type: Optional[str] = None
    date_period: Optional[str] = None


class QueryRequest(BaseModel):
    """Query request model."""

    query: str
    top_k: int = 5
    filters: Optional[QueryFilters] = None


class Source(BaseModel):
    document: str
    score: float
    content_snippet: str
    metadata: dict = {}


class QueryResponse(BaseModel):
    query: str
    answer: str
    sources: list[Source]


def _active_filters(filters: Optional[QueryFilters]) -> dict:
    """Convert QueryFilters to a plain dict, dropping None values."""
    if not filters:
        return {}
    return {k: v for k, v in filters.model_dump().items() if v is not None}


@router.post("/", response_model=QueryResponse)
async def query_rag(request: QueryRequest) -> QueryResponse:
    """Query the RAG index. Supports optional metadata filters and Redis caching."""
    from src.main import rag_pipeline, settings
    from src import cache as cache_module

    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    filters = _active_filters(request.filters)

    # ── cache check ────────────────────────────────────────────────────────
    if settings.redis_url:
        cached = await cache_module.get_cached(
            settings.redis_url, request.query, filters, request.top_k
        )
        if cached:
            return QueryResponse(**cached)

    # ── RAG query ──────────────────────────────────────────────────────────
    try:
        result = rag_pipeline.query(
            query_text=request.query,
            top_k=request.top_k,
            filters=filters,
        )
    except ValueError as e:
        logger.error(f"Query error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    response = QueryResponse(
        query=result["query"],
        answer=result["answer"],
        sources=[Source(**s) for s in result["sources"]],
    )

    # ── cache store ────────────────────────────────────────────────────────
    if settings.redis_url:
        await cache_module.set_cached(
            settings.redis_url,
            request.query,
            filters,
            request.top_k,
            response.model_dump(),
            settings.cache_ttl_seconds,
        )

    return response


@router.post("/stream")
async def query_rag_stream(request: QueryRequest) -> StreamingResponse:
    """Stream answer tokens via Server-Sent Events (SSE).

    Connect with ``Accept: text/event-stream``.  
    Each event is ``data: {"token": "..."}\\n\\n``.  
    The stream closes with ``data: [DONE]\\n\\n``.
    """
    from src.main import rag_pipeline

    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    filters = _active_filters(request.filters)

    def event_generator():
        try:
            for token in rag_pipeline.query_stream(
                query_text=request.query,
                top_k=request.top_k,
                filters=filters,
            ):
                yield f"data: {json.dumps({'token': token})}\n\n"
        except ValueError as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        except Exception as e:
            logger.error(f"Streaming query failed: {e}")
            yield f"data: {json.dumps({'error': 'Streaming failed'})}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
