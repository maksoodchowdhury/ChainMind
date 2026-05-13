"""Lightweight Python SDK client for core platform APIs."""

from __future__ import annotations

import requests


class SupplyChainSDK:
    def __init__(self, base_url: str, api_key: str | None = None, tenant_id: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.tenant_id = tenant_id

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["X-API-Key"] = self.api_key
        if self.tenant_id:
            h["X-Tenant-ID"] = self.tenant_id
        return h

    def query(self, query: str, top_k: int = 5) -> dict:
        resp = requests.post(
            f"{self.base_url}/api/query/",
            json={"query": query, "top_k": top_k},
            headers=self._headers(),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def run_workflow(self, workflow: str, context: dict) -> dict:
        resp = requests.post(
            f"{self.base_url}/api/intelligence/workflows/run",
            json={"workflow": workflow, "context": context},
            headers=self._headers(),
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()

    def tenant_usage(self, tenant_id: str) -> dict:
        resp = requests.get(
            f"{self.base_url}/api/platform/tenants/{tenant_id}/usage",
            headers=self._headers(),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
