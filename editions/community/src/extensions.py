"""Extension framework for custom extractors, rankers, and tools."""

from __future__ import annotations

import json
import re
from pathlib import Path

from src.secure_store import load_json, save_json

EXT_STORE = Path("data/extensions.json")

_ALLOWED_TYPES = {"extractor", "ranker", "tool"}


def _default_store() -> dict:
    return {
        "extensions": {},
        "active": {
            "extractor": None,
            "ranker": None,
            "tool": None,
        },
    }


def list_extensions(ext_type: str | None = None) -> list[dict]:
    payload = load_json(EXT_STORE, _default_store())
    exts = list(payload.get("extensions", {}).values())
    if ext_type:
        exts = [e for e in exts if e.get("type") == ext_type]
    return exts


def register_extension(name: str, *, ext_type: str, description: str = "", entrypoint: str = "builtin") -> dict:
    if ext_type not in _ALLOWED_TYPES:
        raise ValueError(f"ext_type must be one of {sorted(_ALLOWED_TYPES)}")
    payload = load_json(EXT_STORE, _default_store())
    rec = {
        "name": name,
        "type": ext_type,
        "description": description,
        "entrypoint": entrypoint,
        "enabled": True,
    }
    payload.setdefault("extensions", {})[name] = rec
    save_json(EXT_STORE, payload)
    return rec


def set_active_extension(slot: str, name: str | None) -> dict:
    if slot not in _ALLOWED_TYPES:
        raise ValueError(f"slot must be one of {sorted(_ALLOWED_TYPES)}")
    payload = load_json(EXT_STORE, _default_store())
    if name is not None and name not in payload.get("extensions", {}):
        raise KeyError(f"Extension '{name}' not found")
    payload.setdefault("active", {})[slot] = name
    save_json(EXT_STORE, payload)
    return payload.get("active", {})


def get_active_extensions() -> dict:
    payload = load_json(EXT_STORE, _default_store())
    return payload.get("active", {})


def apply_extractor_extension(docs: list, extension_name: str | None) -> list:
    if not extension_name:
        return docs
    if extension_name == "supplychain_normalizer":
        for d in docs:
            d.text = re.sub(r"\s+", " ", d.text).strip()
        return docs
    return docs


def apply_ranker_extension(nodes: list, query: str, extension_name: str | None) -> list:
    if not extension_name:
        return nodes
    q = query.lower()
    if extension_name == "risk_bias_ranker":
        for node in nodes:
            snippet = node.node.get_content().lower()
            if "risk" in q and ("risk" in snippet or "disruption" in snippet):
                node.score = (float(node.score or 0.0) + 0.3)
        return sorted(nodes, key=lambda n: float(n.score or 0.0), reverse=True)
    return nodes


def invoke_tool_extension(extension_name: str | None, *, action: dict) -> dict:
    if not extension_name:
        return {"executed": False, "reason": "no_tool_extension_active"}
    if extension_name == "ticket_stub":
        return {
            "executed": True,
            "tool": extension_name,
            "result": {
                "ticket_id": f"INC-{abs(hash(json.dumps(action, sort_keys=True))) % 100000}",
                "status": "created",
            },
        }
    return {"executed": False, "reason": "unknown_tool_extension"}
