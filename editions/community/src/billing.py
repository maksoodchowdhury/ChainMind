"""Tenant chargeback and billing helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.secure_store import load_json, save_json
from src.tenant_control import list_tenants

BILLING_STORE = Path("data/billing_config.json")


def _default_config() -> dict:
    return {
        "pricing": {
            "usd_per_request": 0.002,
            "usd_per_ingestion_event": 0.01,
            "usd_per_storage_doc": 0.0005,
        }
    }


def get_pricing() -> dict:
    cfg = load_json(BILLING_STORE, _default_config())
    cfg.setdefault("pricing", _default_config()["pricing"])
    return cfg["pricing"]


def set_pricing(*, usd_per_request: float, usd_per_ingestion_event: float, usd_per_storage_doc: float) -> dict:
    payload = {"pricing": {
        "usd_per_request": max(0.0, float(usd_per_request)),
        "usd_per_ingestion_event": max(0.0, float(usd_per_ingestion_event)),
        "usd_per_storage_doc": max(0.0, float(usd_per_storage_doc)),
    }}
    save_json(BILLING_STORE, payload)
    return payload["pricing"]


def build_chargeback_report(month: str | None = None) -> dict:
    pricing = get_pricing()
    month_key = month or datetime.now(timezone.utc).strftime("%Y-%m")

    tenants = list_tenants()
    lines: list[dict] = []
    total = 0.0
    for t in tenants:
        monthly_usage = float(t.get("usage", {}).get("monthly", 0))
        request_cost = monthly_usage * pricing["usd_per_request"]
        line_total = request_cost
        lines.append(
            {
                "tenant_id": t.get("tenant_id"),
                "month": month_key,
                "usage": {"requests": int(monthly_usage)},
                "costs_usd": {
                    "request_cost": round(request_cost, 4),
                    "total": round(line_total, 4),
                },
            }
        )
        total += line_total

    return {
        "month": month_key,
        "pricing": pricing,
        "lines": lines,
        "grand_total_usd": round(total, 4),
    }
