"""Model registry and workload strategy abstraction for control-plane management."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from src.secure_store import load_json, save_json

REGISTRY_STORE = Path("data/model_registry.json")

_DEFAULT = {
    "models": {
        "default_chat": {"provider": "openai", "model": "gpt-4-turbo-preview", "active": True},
        "default_embed": {"provider": "openai", "model": "text-embedding-3-small", "active": True},
    },
    "workload_strategy": {
        "risk": "default_chat",
        "inventory": "default_chat",
        "supplier": "default_chat",
        "lead_time": "default_chat",
        "general": "default_chat",
    },
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load() -> dict:
    return load_json(REGISTRY_STORE, dict(_DEFAULT))


def _save(payload: dict) -> None:
    save_json(REGISTRY_STORE, payload)


def list_models() -> dict:
    return _load()


def register_model(name: str, *, provider: str, model: str, active: bool = False) -> dict:
    payload = _load()
    payload.setdefault("models", {})[name] = {
        "provider": provider,
        "model": model,
        "active": bool(active),
        "updated_at": _now_iso(),
    }
    _save(payload)
    return payload["models"][name]


def set_workload_strategy(query_class: str, model_alias: str) -> dict:
    payload = _load()
    payload.setdefault("workload_strategy", {})[query_class] = model_alias
    _save(payload)
    return payload["workload_strategy"]
