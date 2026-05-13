"""Integration fabric for connectors, events, sync jobs, and CDC placeholders."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from src.secure_store import load_json, save_json

CONNECTOR_STORE = Path("data/connectors.json")
EVENT_STORE = Path("data/integration_events.json")
SYNC_STORE = Path("data/sync_jobs.json")

_DEFAULT_CONNECTORS = {
    "erp": {"enabled": False, "last_sync_at": None},
    "tms": {"enabled": False, "last_sync_at": None},
    "wms": {"enabled": False, "last_sync_at": None},
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path, default):
    return load_json(path, default)


def _save(path: Path, data) -> None:
    save_json(path, data)


def list_connectors() -> dict:
    payload = _load(CONNECTOR_STORE, {"connectors": _DEFAULT_CONNECTORS})
    payload.setdefault("connectors", _DEFAULT_CONNECTORS)
    return payload


def configure_connector(name: str, *, enabled: bool) -> dict:
    payload = list_connectors()
    connectors = payload.setdefault("connectors", _DEFAULT_CONNECTORS)
    if name not in connectors:
        connectors[name] = {"enabled": False, "last_sync_at": None}
    connectors[name]["enabled"] = bool(enabled)
    _save(CONNECTOR_STORE, payload)
    return connectors[name]


def run_connector_sync(name: str, *, trigger: str = "manual") -> dict:
    connector = configure_connector(name, enabled=True)
    sync_data = _load(SYNC_STORE, {"jobs": []})
    job = {
        "job_id": f"sync-{name}-{int(datetime.now(timezone.utc).timestamp())}",
        "connector": name,
        "trigger": trigger,
        "status": "completed",
        "started_at": _now_iso(),
        "completed_at": _now_iso(),
    }
    sync_data.setdefault("jobs", []).append(job)
    _save(SYNC_STORE, sync_data)

    connectors = list_connectors().setdefault("connectors", _DEFAULT_CONNECTORS)
    connectors.setdefault(name, connector)
    connectors[name]["last_sync_at"] = job["completed_at"]
    _save(CONNECTOR_STORE, {"connectors": connectors})
    return job


def create_cdc_job(connector: str, *, schedule_cron: str) -> dict:
    sync_data = _load(SYNC_STORE, {"jobs": []})
    job = {
        "job_id": f"cdc-{connector}-{int(datetime.now(timezone.utc).timestamp())}",
        "connector": connector,
        "type": "cdc",
        "schedule_cron": schedule_cron,
        "status": "scheduled",
        "created_at": _now_iso(),
    }
    sync_data.setdefault("jobs", []).append(job)
    _save(SYNC_STORE, sync_data)
    return job


def list_sync_jobs() -> list[dict]:
    return _load(SYNC_STORE, {"jobs": []}).get("jobs", [])


def publish_event(event_type: str, payload: dict) -> dict:
    events = _load(EVENT_STORE, {"events": []})
    event = {
        "event_id": f"evt-{int(datetime.now(timezone.utc).timestamp() * 1000)}",
        "event_type": event_type,
        "payload": payload,
        "created_at": _now_iso(),
    }
    events.setdefault("events", []).append(event)
    _save(EVENT_STORE, events)
    return event


def list_events(limit: int = 100) -> list[dict]:
    events = _load(EVENT_STORE, {"events": []}).get("events", [])
    return list(reversed(events))[: max(1, min(int(limit), 1000))]
