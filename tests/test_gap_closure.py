import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.main import app

from src.authz import AuthorizationMiddleware
from src.document_processor import redact_pii
from src.ingestion_queue import (
    claim_next_event,
    enqueue_ingestion_event,
    get_dlq_events,
    get_event,
    list_events,
    mark_event_done,
    mark_event_failed,
)
from src.query_policy import classify_query, policy_for_query
from src.resilience import CircuitBreaker, call_with_retry_budget
from src.retention import apply_retention_policies


@pytest.fixture
def client():
    return TestClient(app)


def test_redact_pii_masks_email_phone_and_ssn():
    text = "Contact john.doe@example.com or 555-123-4567; SSN 123-45-6789"
    redacted = redact_pii(text)
    assert "example.com" not in redacted
    assert "555-123-4567" not in redacted
    assert "123-45-6789" not in redacted
    assert "[REDACTED_EMAIL]" in redacted


def test_query_classification_and_policy():
    assert classify_query("What are supplier risks?") == "risk"
    p = policy_for_query("inventory reorder point", top_k=5, requested_rerank_strategy="default")
    assert p.query_class == "inventory"
    assert p.top_k >= 5


def test_circuit_breaker_opens_after_threshold():
    br = CircuitBreaker(fail_threshold=2, recovery_seconds=30)
    assert br.allow() is True
    br.mark_failure()
    assert br.allow() is True
    br.mark_failure()
    assert br.allow() is False


def test_retry_budget_succeeds_after_retry():
    attempts = {"n": 0}

    def flaky():
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise RuntimeError("fail once")
        return "ok"

    assert call_with_retry_budget(flaky, max_attempts=3, backoff_seconds=0.0) == "ok"


def test_ingestion_queue_idempotency_and_dlq(tmp_path, monkeypatch):
    import src.ingestion_queue as iq

    monkeypatch.setattr(iq, "QUEUE_STORE", tmp_path / "queue.json")
    monkeypatch.setattr(iq, "IDEMPOTENCY_STORE", tmp_path / "idempotency.json")
    monkeypatch.setattr(iq, "DLQ_STORE", tmp_path / "dlq.json")

    ev1 = enqueue_ingestion_event(
        filename="a.txt",
        file_path="/tmp/a.txt",
        metadata={"supplier": "Acme"},
        idempotency_key="idem-1",
    )
    ev2 = enqueue_ingestion_event(
        filename="a.txt",
        file_path="/tmp/a.txt",
        metadata={"supplier": "Acme"},
        idempotency_key="idem-1",
    )
    assert ev1.event_id == ev2.event_id

    claimed = claim_next_event()
    assert claimed is not None
    assert claimed.status == "processing"

    mark_event_failed(claimed.event_id, error="boom", poison_max_attempts=1)
    dlq = get_dlq_events()
    assert len(dlq) == 1
    assert dlq[0]["status"] == "poisoned"


def test_retention_policy_prunes_uploads_and_history(tmp_path, monkeypatch):
    import src.retention as rt
    from datetime import datetime, timedelta, timezone
    import os

    uploads = tmp_path / "uploads"
    uploads.mkdir(parents=True)
    old_file = uploads / "old.txt"
    old_file.write_text("old")

    old_ts = (datetime.now(timezone.utc) - timedelta(days=120)).timestamp()
    os.utime(old_file, (old_ts, old_ts))

    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "documents": {
                    "old.txt": {
                        "history": [
                            {"uploaded_at": (datetime.now(timezone.utc) - timedelta(days=500)).isoformat()}
                        ]
                    }
                }
            }
        )
    )

    monkeypatch.setattr(rt, "UPLOAD_DIR", uploads)
    monkeypatch.setattr(rt, "CATALOG_STORE", catalog)

    res = apply_retention_policies(retention_days_uploads=90, retention_days_catalog_history=365)
    assert res["deleted_upload_files"] == 1
    assert res["pruned_catalog_history_entries"] == 1


def test_authorization_middleware_role_and_tenant():
    app = FastAPI()

    @app.get("/api/query/test")
    async def protected():
        return {"ok": True}

    app.add_middleware(
        AuthorizationMiddleware,
        enabled=True,
        require_tenant_header=True,
        valid_roles={"admin", "analyst", "viewer"},
    )
    client = TestClient(app)

    missing_tenant = client.get("/api/query/test", headers={"X-Role": "viewer"})
    assert missing_tenant.status_code == 400

    forbidden = client.get("/api/query/test", headers={"X-Role": "invalid", "X-Tenant-ID": "t1"})
    assert forbidden.status_code == 403

    ok = client.get("/api/query/test", headers={"X-Role": "viewer", "X-Tenant-ID": "t1"})
    assert ok.status_code == 200


def test_documents_event_endpoints(client):
    import uuid

    filename = f"ev_test_{uuid.uuid4().hex}.txt"
    upload = client.post(
        "/api/documents/upload?force=true",
        files={"file": (filename, b"hello event queue", "text/plain")},
    )
    assert upload.status_code == 202
    assert "event_id" in upload.json()

    events = client.get("/api/documents/events")
    assert events.status_code == 200
    assert "events" in events.json()


def test_retention_endpoint(client):
    resp = client.post("/maintenance/retention/run")
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"
