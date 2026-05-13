import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from src.document_catalog import mark_job_result
from src.ingestion_queue import (
    claim_next_event,
    mark_event_done,
    mark_event_failed,
)

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


@dataclass
class IngestionJob:
    job_id: str
    filename: str
    status: JobStatus = JobStatus.PENDING
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    completed_at: Optional[str] = None
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    chunks_indexed: int = 0


# In-memory job store (per-process; swap for Redis in multi-worker deployments)
_jobs: dict[str, IngestionJob] = {}


def create_job(filename: str, metadata: dict) -> IngestionJob:
    """Create a new ingestion job and register it."""
    unique_key = f"{filename}-{datetime.now(timezone.utc).isoformat()}"
    job_id = hashlib.sha256(unique_key.encode()).hexdigest()[:16]
    job = IngestionJob(job_id=job_id, filename=filename, metadata=metadata)
    _jobs[job_id] = job
    logger.info(f"Created ingestion job {job_id} for {filename}")
    return job


def get_job(job_id: str) -> Optional[IngestionJob]:
    """Get a job by ID."""
    return _jobs.get(job_id)


def list_jobs() -> list[IngestionJob]:
    """List all ingestion jobs."""
    return sorted(_jobs.values(), key=lambda j: j.created_at, reverse=True)


def get_job_counts() -> dict[str, int]:
    """Return current job counts by status plus inflight total."""
    pending = sum(1 for j in _jobs.values() if j.status == JobStatus.PENDING)
    processing = sum(1 for j in _jobs.values() if j.status == JobStatus.PROCESSING)
    done = sum(1 for j in _jobs.values() if j.status == JobStatus.DONE)
    failed = sum(1 for j in _jobs.values() if j.status == JobStatus.FAILED)
    return {
        "pending": pending,
        "processing": processing,
        "done": done,
        "failed": failed,
        "inflight": pending + processing,
        "total": pending + processing + done + failed,
    }


def can_accept_new_job(max_inflight_jobs: int) -> bool:
    """Check whether a new ingestion job can be accepted under queue policy."""
    counts = get_job_counts()
    return counts["inflight"] < max(1, max_inflight_jobs)


async def run_ingestion(
    job_id: str,
    file_path: str,
    rag_pipeline,
    metadata: dict,
) -> None:
    """Background task: index a document and update job status."""
    job = _jobs.get(job_id)
    if not job:
        logger.error(f"Job {job_id} not found in store")
        return

    job.status = JobStatus.PROCESSING
    logger.info(f"Job {job_id}: starting ingestion of {file_path}")

    try:
        chunks = rag_pipeline.load_documents([file_path], extra_metadata=metadata)
        job.chunks_indexed = chunks
        job.status = JobStatus.DONE
        job.completed_at = datetime.now(timezone.utc).isoformat()
        mark_job_result(
            job.filename,
            job.job_id,
            lifecycle_state="approved",
            chunk_count=chunks,
        )
        logger.info(f"Job {job_id}: completed — {chunks} chunks indexed")
    except Exception as e:
        job.status = JobStatus.FAILED
        job.error = str(e)
        job.completed_at = datetime.now(timezone.utc).isoformat()
        mark_job_result(
            job.filename,
            job.job_id,
            lifecycle_state="failed",
            chunk_count=0,
            error=str(e),
        )
        logger.error(f"Job {job_id}: failed — {e}")


async def process_next_ingestion_event(
    rag_pipeline,
    *,
    poison_max_attempts: int = 3,
) -> Optional[IngestionJob]:
    """Claim and process one queued ingestion event.

    Returns the resulting IngestionJob, or None when no event is queued.
    """
    event = claim_next_event()
    if not event:
        return None

    job = create_job(filename=event.filename, metadata=event.metadata)
    try:
        await run_ingestion(
            job_id=job.job_id,
            file_path=event.file_path,
            rag_pipeline=rag_pipeline,
            metadata=event.metadata,
        )
        if job.status == JobStatus.DONE:
            mark_event_done(event.event_id)
        else:
            mark_event_failed(
                event.event_id,
                error=job.error or "unknown_ingestion_error",
                poison_max_attempts=poison_max_attempts,
            )
    except Exception as e:
        mark_event_failed(
            event.event_id,
            error=str(e),
            poison_max_attempts=poison_max_attempts,
        )
    return job
