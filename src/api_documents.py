from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, Header, Query, UploadFile, File
import logging
from pathlib import Path
from typing import Optional

from pydantic import BaseModel
from src.document_catalog import (
    get_catalog_document,
    list_catalog_documents,
    register_upload,
    transition_lifecycle_state,
)
from src.document_processor import is_already_indexed, is_semantically_duplicate
from src.ingestion_queue import (
    enqueue_ingestion_event,
    get_dlq_events,
    get_event,
    list_events,
)
from src.ingestion_worker import (
    JobStatus,
    can_accept_new_job,
    create_job,
    get_job,
    get_job_counts,
    list_jobs,
    run_ingestion,
    process_next_ingestion_event,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/documents", tags=["documents"])

UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class StateTransitionRequest(BaseModel):
    new_state: str


@router.post("/upload", status_code=202)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    supplier: Optional[str] = Form(None),
    doc_type: Optional[str] = Form(None),
    date_period: Optional[str] = Form(None),
    force: bool = Query(False, description="Re-index even if content is already indexed"),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> dict:
    """Upload a supply chain document and queue it for async indexing.

    Optional metadata fields (stamped on every chunk):
    - **supplier**: e.g. "Ningbo Electronics"
    - **doc_type**: e.g. "demand_plan" | "supplier_note" | "inventory_policy"
    - **date_period**: e.g. "2024-Q3"
    """
    from src.main import rag_pipeline, settings

    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    if not can_accept_new_job(settings.max_inflight_ingestion_jobs):
        counts = get_job_counts()
        raise HTTPException(
            status_code=503,
            detail={
                "message": "Ingestion queue is full. Please retry later.",
                "inflight_jobs": counts["inflight"],
                "max_inflight_jobs": settings.max_inflight_ingestion_jobs,
            },
            headers={"Retry-After": "10"},
        )

    file_path = UPLOAD_DIR / file.filename
    contents = await file.read()

    with open(file_path, "wb") as f:
        f.write(contents)

    # ── semantic dedup (SHA-256 fingerprint) ──────────────────────────────
    if not force:

        if is_already_indexed(str(file_path)):
            existing = get_catalog_document(file.filename)
            return {
                "status": "duplicate",
                "message": "Document content already indexed. Use ?force=true to re-index.",
                "filename": file.filename,
                "version": existing.get("version") if existing else None,
                "lifecycle_state": existing.get("lifecycle_state") if existing else None,
                "dedup_prevented": True,
            }
        if settings.semantic_dedup_enabled and is_semantically_duplicate(
            str(file_path), threshold=settings.semantic_dedup_threshold
        ):
            return {
                "status": "duplicate",
                "message": "Document is semantically similar to existing indexed content. Use ?force=true to override.",
                "filename": file.filename,
                "dedup_prevented": True,
                "dedup_type": "semantic",
            }

    metadata = {
        k: v
        for k, v in {
            "supplier": supplier,
            "doc_type": doc_type,
            "date_period": date_period,
        }.items()
        if v is not None
    }

    # Event-driven queue mode with idempotency and poison-message handling.
    if settings.ingestion_queue_enabled:
        event = enqueue_ingestion_event(
            filename=file.filename,
            file_path=str(file_path),
            metadata=metadata,
            idempotency_key=idempotency_key,
        )
        governance = register_upload(file.filename, metadata, event.event_id)
        background_tasks.add_task(
            process_next_ingestion_event,
            rag_pipeline=rag_pipeline,
            poison_max_attempts=settings.ingestion_poison_max_attempts,
        )
        return {
            "status": "accepted",
            "event_id": event.event_id,
            "idempotency_key": event.idempotency_key,
            "filename": file.filename,
            "version": governance.get("version"),
            "lifecycle_state": governance.get("lifecycle_state"),
            "size": len(contents),
            "metadata": metadata,
            "message": "Document queued for indexing event. Poll /api/documents/events/{event_id}.",
        }

    job = create_job(filename=file.filename, metadata=metadata)
    governance = register_upload(file.filename, metadata, job.job_id)

    background_tasks.add_task(
        run_ingestion,
        job_id=job.job_id,
        file_path=str(file_path),
        rag_pipeline=rag_pipeline,
        metadata=metadata,
    )

    logger.info(f"Queued ingestion job {job.job_id} for {file.filename}")
    return {
        "status": "accepted",
        "job_id": job.job_id,
        "filename": file.filename,
        "version": governance.get("version"),
        "lifecycle_state": governance.get("lifecycle_state"),
        "size": len(contents),
        "metadata": metadata,
        "message": "Document queued for indexing. Poll /api/documents/status/{job_id} for progress.",
    }


@router.get("/status/{job_id}")
async def get_job_status(job_id: str) -> dict:
    """Poll the status of an ingestion job."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return {
        "job_id": job.job_id,
        "filename": job.filename,
        "status": job.status,
        "chunks_indexed": job.chunks_indexed,
        "metadata": job.metadata,
        "created_at": job.created_at,
        "completed_at": job.completed_at,
        "error": job.error,
    }


@router.get("/jobs")
async def list_ingestion_jobs() -> dict:
    """List all ingestion jobs with their statuses."""
    jobs = list_jobs()
    return {
        "jobs": [
            {
                "job_id": j.job_id,
                "filename": j.filename,
                "status": j.status,
                "chunks_indexed": j.chunks_indexed,
                "created_at": j.created_at,
                "completed_at": j.completed_at,
            }
            for j in jobs
        ],
        "count": len(jobs),
    }


@router.get("/events")
async def list_ingestion_events(status: Optional[str] = None) -> dict:
    """List ingestion events when queue mode is enabled."""
    events = list_events(status=status)
    return {"events": events, "count": len(events)}


@router.get("/events/{event_id}")
async def get_ingestion_event(event_id: str) -> dict:
    event = get_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail=f"Event '{event_id}' not found")
    return event.__dict__


@router.get("/events-dlq")
async def list_ingestion_dlq() -> dict:
    """List poison ingestion events sent to dead-letter queue."""
    items = get_dlq_events()
    return {"events": items, "count": len(items)}


@router.get("/list")
async def list_documents() -> dict:
    """List all uploaded document files."""
    try:
        documents = []
        if UPLOAD_DIR.exists():
            for f in UPLOAD_DIR.iterdir():
                if f.is_file():
                    documents.append(
                        {
                            "filename": f.name,
                            "size": f.stat().st_size,
                            "modified": f.stat().st_mtime,
                        }
                    )
        return {"documents": documents, "count": len(documents)}
    except Exception as e:
        logger.error(f"Failed to list documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/catalog")
async def list_document_catalog() -> dict:
    """List governance metadata (version, lifecycle state, lineage) for documents."""
    documents = list_catalog_documents()
    return {"documents": documents, "count": len(documents)}


@router.get("/catalog/{filename}")
async def get_document_catalog_entry(filename: str) -> dict:
    """Retrieve governance metadata for a single document by filename."""
    entry = get_catalog_document(filename)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Document '{filename}' not found in catalog")
    return entry


@router.patch("/catalog/{filename}/state")
async def update_document_state(filename: str, body: StateTransitionRequest) -> dict:
    """Transition a document's lifecycle state.

    Valid transitions:
    - **draft** → approved | failed
    - **approved** → retired
    - **failed** → draft  *(retry)*
    - **retired** → *(terminal — no further transitions)*
    """
    try:
        entry = transition_lifecycle_state(filename, body.new_state)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return entry
