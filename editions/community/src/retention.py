"""Retention policy helpers for runtime data stores."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

UPLOAD_DIR = Path("data/uploads")
CATALOG_STORE = Path("data/document_catalog.json")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def apply_retention_policies(
    *,
    retention_days_uploads: int,
    retention_days_catalog_history: int,
) -> dict:
    """Apply retention windows to uploads and catalog history."""
    deleted_files = 0
    pruned_history = 0

    cutoff_uploads = _now() - timedelta(days=max(1, retention_days_uploads))
    if UPLOAD_DIR.exists():
        for p in UPLOAD_DIR.iterdir():
            if p.is_file():
                mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
                if mtime < cutoff_uploads:
                    p.unlink(missing_ok=True)
                    deleted_files += 1

    if CATALOG_STORE.exists():
        try:
            payload = json.loads(CATALOG_STORE.read_text())
        except Exception:
            payload = {"documents": {}}
        docs = payload.get("documents", {})
        cutoff_history = _now() - timedelta(days=max(1, retention_days_catalog_history))
        for entry in docs.values():
            hist = entry.get("history", [])
            kept = []
            for h in hist:
                ts = h.get("uploaded_at") or h.get("transitioned_at") or h.get("completed_at")
                if not ts:
                    kept.append(h)
                    continue
                try:
                    dt = datetime.fromisoformat(ts)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                except Exception:
                    kept.append(h)
                    continue
                if dt >= cutoff_history:
                    kept.append(h)
                else:
                    pruned_history += 1
            entry["history"] = kept
        CATALOG_STORE.write_text(json.dumps(payload, indent=2))

    return {
        "deleted_upload_files": deleted_files,
        "pruned_catalog_history_entries": pruned_history,
        "applied_at": _now().isoformat(),
    }
