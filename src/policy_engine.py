"""Policy-as-code evaluator for platform governance and compliance."""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_POLICY_FILE = Path("config/policies.json")

_DEFAULT_POLICIES = {
    "data_residency": {
        "allowed_regions": ["us", "eu"],
        "default_region": "us",
    },
    "model_usage": {
        "allow_external_models": True,
        "restricted_for_tenants": [],
    },
    "autonomous_actions": {
        "notify_threshold": 3.0,
        "ticket_threshold": 6.0,
        "auto_execute_threshold": 2.0,
    },
}


def load_policies(policy_file: str | None = None) -> dict:
    path = Path(policy_file) if policy_file else DEFAULT_POLICY_FILE
    if path.exists():
        try:
            loaded = json.loads(path.read_text())
            if isinstance(loaded, dict):
                return {**_DEFAULT_POLICIES, **loaded}
        except Exception:
            return dict(_DEFAULT_POLICIES)
    return dict(_DEFAULT_POLICIES)


def evaluate_residency(tenant_region: str, *, policy_file: str | None = None) -> dict:
    policies = load_policies(policy_file)
    allowed = policies.get("data_residency", {}).get("allowed_regions", ["us"])
    ok = tenant_region in allowed
    return {
        "policy": "data_residency",
        "allowed": ok,
        "tenant_region": tenant_region,
        "allowed_regions": allowed,
    }


def evaluate_model_usage(tenant_id: str, *, uses_external_model: bool, policy_file: str | None = None) -> dict:
    policies = load_policies(policy_file)
    usage = policies.get("model_usage", {})
    restricted = set(usage.get("restricted_for_tenants", []))
    allow_external = bool(usage.get("allow_external_models", True))
    ok = (not uses_external_model) or (allow_external and tenant_id not in restricted)
    return {
        "policy": "model_usage",
        "allowed": ok,
        "tenant_id": tenant_id,
        "uses_external_model": uses_external_model,
        "restricted": tenant_id in restricted,
    }
