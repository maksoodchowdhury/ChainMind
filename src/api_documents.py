from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, UploadFile, File
import logging
from pathlib import Path
from typing import Optional

from src.ingestion_worker import (
    JobStatus,
    create_job,
    get_job,
    list_jobs,
    run_ingestion,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/documents", tags=["documents"])

UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/upload", status_code=202)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    supplier: Optional[str] = Form(None),
    doc_type: Optional[str] = Form(None),
    date_period: Optional[str] = Form(None),
) -> dict:
    """Upload a supply chain document and queue it for async indexing.

    Optional metadata fields (stamped on every chunk):
    - **supplier**: e.g. "Ningbo Electronics"
    - **doc_type**: e.g. "demand_plan" | "supplier_note" | "inventory_policy"
    - **date_period**: e.g. "2024-Q3"
    """
    from src.main import rag_pipeline

    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    file_path = UPLOAD_DIR / file.filename
    contents = await file.read()

    with open(file_path, "wb") as f:
        f.write(contents)

    metadata = {
        k: v
        for k, v in {
            "supplier": supplier,
            "doc_type": doc_type,
            "date_period": date_period,
        }.items()
        if v is not None
    }

    job = create_job(filename=file.filename, metadata=metadata)

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
