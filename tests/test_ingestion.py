"""Tests for async ingestion worker."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.ingestion_worker import (
    JobStatus,
    IngestionJob,
    create_job,
    get_job,
    list_jobs,
    run_ingestion,
)


def test_create_job_returns_job():
    job = create_job("forecast.txt", {"supplier": "Acme", "doc_type": "demand_plan"})
    assert job.filename == "forecast.txt"
    assert job.status == JobStatus.PENDING
    assert job.metadata["supplier"] == "Acme"
    assert len(job.job_id) == 16


def test_create_job_unique_ids():
    job_a = create_job("file_a.txt", {})
    job_b = create_job("file_b.txt", {})
    assert job_a.job_id != job_b.job_id


def test_get_job_returns_registered_job():
    job = create_job("get_test.txt", {})
    retrieved = get_job(job.job_id)
    assert retrieved is not None
    assert retrieved.job_id == job.job_id


def test_get_job_missing_returns_none():
    assert get_job("nonexistent-id") is None


def test_list_jobs_contains_created_jobs():
    job = create_job("list_test.txt", {})
    jobs = list_jobs()
    assert any(j.job_id == job.job_id for j in jobs)


@pytest.mark.asyncio
async def test_run_ingestion_success():
    mock_pipeline = MagicMock()
    mock_pipeline.load_documents.return_value = 5

    job = create_job("ingest_success.txt", {"doc_type": "policy"})
    await run_ingestion(
        job_id=job.job_id,
        file_path="/fake/path/ingest_success.txt",
        rag_pipeline=mock_pipeline,
        metadata={"doc_type": "policy"},
    )

    assert job.status == JobStatus.DONE
    assert job.chunks_indexed == 5
    assert job.completed_at is not None
    assert job.error is None
    mock_pipeline.load_documents.assert_called_once_with(
        ["/fake/path/ingest_success.txt"], extra_metadata={"doc_type": "policy"}
    )


@pytest.mark.asyncio
async def test_run_ingestion_failure():
    mock_pipeline = MagicMock()
    mock_pipeline.load_documents.side_effect = RuntimeError("Qdrant unavailable")

    job = create_job("ingest_fail.txt", {})
    await run_ingestion(
        job_id=job.job_id,
        file_path="/fake/path/ingest_fail.txt",
        rag_pipeline=mock_pipeline,
        metadata={},
    )

    assert job.status == JobStatus.FAILED
    assert "Qdrant unavailable" in job.error
    assert job.completed_at is not None


@pytest.mark.asyncio
async def test_run_ingestion_missing_job():
    """Should not raise even if job_id is not in the store."""
    mock_pipeline = MagicMock()
    await run_ingestion(
        job_id="phantom-id",
        file_path="/fake/path.txt",
        rag_pipeline=mock_pipeline,
        metadata={},
    )
    mock_pipeline.load_documents.assert_not_called()
