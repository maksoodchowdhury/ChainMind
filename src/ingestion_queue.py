"""Event-driven ingestion queue with idempotency and poison-message handling."""

from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

QUEUE_STORE = Path("data/ingestion_queue.json")
IDEMPOTENCY_STORE = Path("data/ingestion_idempotency.json")
DLQ_STORE = Path("data/ingestion_dlq.json")


@dataclass
class IngestionEvent:
    event_id: str
    idempotency_key: str
    filename: str
    file_path: str
    metadata: dict
    created_at: str
    attempts: int = 0
    status: str = "queued"  # queued | processing | done | failed | poisoned


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return default
    return default


def _save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def _compute_key(filename: str, file_path: str, metadata: dict, explicit_key: str | None) -> str:
    if explicit_key:
        return explicit_key
    payload = json.dumps({"filename": filename, "file_path": file_path, "metadata": metadata}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def enqueue_ingestion_event(
    *,
    filename: str,
    file_path: str,
    metadata: dict,
    idempotency_key: str | None = None,
) -> IngestionEvent:
    """Queue a new ingestion event; duplicates are deduped by idempotency key."""
    queue = _load(QUEUE_STORE, {"events": []})
    idem = _load(IDEMPOTENCY_STORE, {})

    key = _compute_key(filename, file_path, metadata, idempotency_key)
    existing_event_id = idem.get(key)
    if existing_event_id:
        for e in queue.get("events", []):
            if e.get("event_id") == existing_event_id:
                return IngestionEvent(**e)

    event_id = hashlib.sha256(f"{key}-{_now_iso()}".encode("utf-8")).hexdigest()[:16]
    event = IngestionEvent(
        event_id=event_id,
        idempotency_key=key,
        filename=filename,
        file_path=file_path,
        metadata=metadata,
        created_at=_now_iso(),
    )
    queue.setdefault("events", []).append(event.__dict__)
    idem[key] = event_id
    _save(QUEUE_STORE, queue)
    _save(IDEMPOTENCY_STORE, idem)
    return event


def get_event(event_id: str) -> IngestionEvent | None:
    queue = _load(QUEUE_STORE, {"events": []})
    for e in queue.get("events", []):
        if e.get("event_id") == event_id:
            return IngestionEvent(**e)
    return None


def list_events(status: str | None = None) -> list[dict]:
    queue = _load(QUEUE_STORE, {"events": []})
    events = queue.get("events", [])
    if status:
        events = [e for e in events if e.get("status") == status]
    return events


def claim_next_event() -> IngestionEvent | None:
    queue = _load(QUEUE_STORE, {"events": []})
    for e in queue.get("events", []):
        if e.get("status") == "queued":
            e["status"] = "processing"
            e["attempts"] = int(e.get("attempts", 0)) + 1
            _save(QUEUE_STORE, queue)
            return IngestionEvent(**e)
    return None


def mark_event_done(event_id: str) -> None:
    queue = _load(QUEUE_STORE, {"events": []})
    for e in queue.get("events", []):
        if e.get("event_id") == event_id:
            e["status"] = "done"
            break
    _save(QUEUE_STORE, queue)


def mark_event_failed(event_id: str, *, error: str, poison_max_attempts: int = 3) -> None:
    queue = _load(QUEUE_STORE, {"events": []})
    dlq = _load(DLQ_STORE, {"events": []})
    for e in queue.get("events", []):
        if e.get("event_id") == event_id:
            e["error"] = error
            attempts = int(e.get("attempts", 1))
            if attempts >= max(1, poison_max_attempts):
                e["status"] = "poisoned"
                dlq.setdefault("events", []).append({**e, "poisoned_at": _now_iso()})
            else:
                e["status"] = "queued"
            break
    _save(QUEUE_STORE, queue)
    _save(DLQ_STORE, dlq)


def get_dlq_events() -> list[dict]:
    return _load(DLQ_STORE, {"events": []}).get("events", [])
