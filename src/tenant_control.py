"""Tenant quota and usage tracking for multi-tenant platform controls."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from src.secure_store import load_json, save_json

USAGE_STORE = Path("data/tenant_usage.json")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _month_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _load() -> dict:
    return load_json(USAGE_STORE, {"tenants": {}})


def _save(payload: dict) -> None:
    save_json(USAGE_STORE, payload)


def _tenant_entry(payload: dict, tenant_id: str) -> dict:
    tenants = payload.setdefault("tenants", {})
    return tenants.setdefault(
        tenant_id,
        {
            "quota": {
                "daily": 1000,
                "monthly": 25000,
            },
            "usage": {
                "daily": {},
                "monthly": {},
            },
            "last_updated_at": _now_iso(),
        },
    )


def set_quota(tenant_id: str, *, daily: int, monthly: int) -> dict:
    payload = _load()
    entry = _tenant_entry(payload, tenant_id)
    entry["quota"] = {
        "daily": max(1, int(daily)),
        "monthly": max(1, int(monthly)),
    }
    entry["last_updated_at"] = _now_iso()
    _save(payload)
    return entry


def get_usage(tenant_id: str) -> dict:
    payload = _load()
    entry = _tenant_entry(payload, tenant_id)
    d = _today_key()
    m = _month_key()
    return {
        "tenant_id": tenant_id,
        "quota": entry["quota"],
        "usage": {
            "daily": int(entry["usage"].get("daily", {}).get(d, 0)),
            "monthly": int(entry["usage"].get("monthly", {}).get(m, 0)),
        },
        "window": {"day": d, "month": m},
        "last_updated_at": entry.get("last_updated_at"),
    }


def would_exceed_quota(tenant_id: str, *, requested_units: int = 1) -> tuple[bool, dict]:
    status = get_usage(tenant_id)
    requested = max(1, int(requested_units))
    projected_daily = status["usage"]["daily"] + requested
    projected_monthly = status["usage"]["monthly"] + requested
    exceeded = (
        projected_daily > int(status["quota"]["daily"])
        or projected_monthly > int(status["quota"]["monthly"])
    )
    return exceeded, {
        **status,
        "requested_units": requested,
        "projected": {
            "daily": projected_daily,
            "monthly": projected_monthly,
        },
    }


def record_usage(tenant_id: str, *, units: int = 1) -> dict:
    payload = _load()
    entry = _tenant_entry(payload, tenant_id)
    d = _today_key()
    m = _month_key()
    usage = entry.setdefault("usage", {"daily": {}, "monthly": {}})
    usage.setdefault("daily", {})
    usage.setdefault("monthly", {})
    usage["daily"][d] = int(usage["daily"].get(d, 0)) + max(1, int(units))
    usage["monthly"][m] = int(usage["monthly"].get(m, 0)) + max(1, int(units))
    entry["last_updated_at"] = _now_iso()
    _save(payload)
    return get_usage(tenant_id)


def list_tenants() -> list[dict]:
    payload = _load()
    tenants = payload.get("tenants", {})
    return [get_usage(tid) for tid in sorted(tenants.keys())]
