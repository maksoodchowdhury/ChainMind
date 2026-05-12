import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

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
        logger.info(f"Job {job_id}: completed — {chunks} chunks indexed")
    except Exception as e:
        job.status = JobStatus.FAILED
        job.error = str(e)
        job.completed_at = datetime.now(timezone.utc).isoformat()
        logger.error(f"Job {job_id}: failed — {e}")
