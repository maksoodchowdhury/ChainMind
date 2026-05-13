"""Execution helpers for policy-driven autonomous actions."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.extensions import get_active_extensions, invoke_tool_extension
from src.secure_store import load_json, save_json

ACTIONS_STORE = Path("data/autonomy_actions.json")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def execute_action(action: dict, *, approved: bool) -> dict:
    payload = load_json(ACTIONS_STORE, {"actions": []})
    active = get_active_extensions()
    tool_name = active.get("tool")

    status = "executed" if approved else "awaiting_approval"
    tool_result = {"executed": False, "reason": "approval_required"}
    if approved:
        tool_result = invoke_tool_extension(tool_name, action=action)

    rec = {
        "action_id": f"act-{int(datetime.now(timezone.utc).timestamp() * 1000)}",
        "status": status,
        "approved": approved,
        "action": action,
        "tool_result": tool_result,
        "executed_at": _now_iso(),
    }
    payload.setdefault("actions", []).append(rec)
    save_json(ACTIONS_STORE, payload)
    return rec


def list_executions(limit: int = 100) -> list[dict]:
    payload = load_json(ACTIONS_STORE, {"actions": []})
    return list(reversed(payload.get("actions", [])))[: max(1, min(limit, 1000))]
