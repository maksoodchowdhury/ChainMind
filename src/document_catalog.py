"""Document governance catalog: versioning, lifecycle state, lineage."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

CATALOG_STORE = Path("data/document_catalog.json")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_catalog() -> dict:
    if CATALOG_STORE.exists():
        try:
            return json.loads(CATALOG_STORE.read_text())
        except Exception:
            return {"documents": {}}
    return {"documents": {}}


def _save_catalog(catalog: dict) -> None:
    CATALOG_STORE.parent.mkdir(parents=True, exist_ok=True)
    CATALOG_STORE.write_text(json.dumps(catalog, indent=2))


def register_upload(filename: str, metadata: dict, job_id: str) -> dict:
    """Create or increment a version for an uploaded document."""
    catalog = _load_catalog()
    docs = catalog.setdefault("documents", {})
    entry = docs.get(filename, {})

    new_version = int(entry.get("version", 0)) + 1
    uploaded_at = _now_iso()
    history = entry.get("history", [])
    history.append(
        {
            "version": new_version,
            "job_id": job_id,
            "uploaded_at": uploaded_at,
            "metadata": metadata,
            "lifecycle_state": "draft",
        }
    )

    docs[filename] = {
        "filename": filename,
        "version": new_version,
        "lifecycle_state": "draft",
        "last_job_id": job_id,
        "last_uploaded_at": uploaded_at,
        "last_indexed_at": entry.get("last_indexed_at"),
        "last_error": None,
        "metadata": metadata,
        "history": history,
    }
    _save_catalog(catalog)
    return docs[filename]


def mark_job_result(
    filename: str,
    job_id: str,
    *,
    lifecycle_state: str,
    chunk_count: int = 0,
    error: str | None = None,
) -> None:
    """Update lifecycle state after indexing completes or fails."""
    catalog = _load_catalog()
    docs = catalog.setdefault("documents", {})
    entry = docs.get(filename)
    if not entry:
        return

    entry["lifecycle_state"] = lifecycle_state
    entry["last_job_id"] = job_id
    entry["last_error"] = error
    if lifecycle_state == "approved":
        entry["last_indexed_at"] = _now_iso()
    entry["chunk_count"] = chunk_count

    for h in reversed(entry.get("history", [])):
        if h.get("job_id") == job_id:
            h["lifecycle_state"] = lifecycle_state
            h["chunk_count"] = chunk_count
            h["error"] = error
            h["completed_at"] = _now_iso()
            break

    _save_catalog(catalog)


def list_catalog_documents() -> list[dict]:
    catalog = _load_catalog()
    docs = catalog.get("documents", {})
    return sorted(docs.values(), key=lambda d: d.get("last_uploaded_at", ""), reverse=True)


def get_catalog_document(filename: str) -> dict | None:
    """Return the catalog entry for a single document, or None if not found."""
    catalog = _load_catalog()
    return catalog.get("documents", {}).get(filename)


# Valid lifecycle state transitions: current_state -> set of allowed next states
_VALID_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"approved", "failed"},
    "approved": {"retired"},
    "failed": {"draft"},
    "retired": set(),  # terminal state
}


def transition_lifecycle_state(filename: str, new_state: str) -> dict:
    """Transition a document's lifecycle state with validation.

    Raises:
        KeyError: document not found
        ValueError: transition not allowed from the current state
    """
    catalog = _load_catalog()
    docs = catalog.setdefault("documents", {})
    entry = docs.get(filename)
    if not entry:
        raise KeyError(f"Document '{filename}' not found in catalog")

    current = entry["lifecycle_state"]
    allowed = _VALID_TRANSITIONS.get(current, set())
    if new_state not in allowed:
        raise ValueError(
            f"Cannot transition '{filename}' from '{current}' to '{new_state}'. "
            f"Allowed transitions: {sorted(allowed) or 'none (terminal state)'}"
        )

    entry["lifecycle_state"] = new_state
    entry["history"].append(
        {
            "event": "state_transition",
            "from_state": current,
            "to_state": new_state,
            "transitioned_at": _now_iso(),
        }
    )
    _save_catalog(catalog)
    return entry
