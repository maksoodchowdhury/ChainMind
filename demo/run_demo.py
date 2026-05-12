#!/usr/bin/env python3
"""
SupplyChain RAG Assistant — Interactive Demo
============================================
This script demonstrates the full capabilities of the RAG assistant using
synthetic supply chain documents.

Usage:
    python demo/run_demo.py [--host http://localhost:8000] [--api-key YOUR_KEY]

Prerequisites:
    1. API is running: uvicorn src.main:app --reload
    2. Qdrant is running: docker run -p 6333:6333 qdrant/qdrant
"""

import argparse
import json
import sys
import time
from pathlib import Path

import requests

# ── CONFIGURATION ──────────────────────────────────────────────────────────────

DEMO_DATA_DIR = Path(__file__).parent / "data"

DEMO_FILES = [
    {
        "path": DEMO_DATA_DIR / "demand_forecast_q1_2025.txt",
        "supplier": "acme-planning",
        "doc_type": "demand_plan",
        "date_period": "Q1-2025",
        "description": "Q1 2025 Demand Forecast",
    },
    {
        "path": DEMO_DATA_DIR / "supplier_directory.csv",
        "supplier": "multi-supplier",
        "doc_type": "supplier_info",
        "date_period": "2025",
        "description": "Supplier Directory (10 suppliers)",
    },
    {
        "path": DEMO_DATA_DIR / "inventory_policy.txt",
        "supplier": "acme-ops",
        "doc_type": "inventory_policy",
        "date_period": "2025",
        "description": "Inventory Management Policy v3.2",
    },
    {
        "path": DEMO_DATA_DIR / "risk_assessment.txt",
        "supplier": "acme-risk",
        "doc_type": "risk_assessment",
        "date_period": "Q1-2025",
        "description": "Q1 2025 Risk Assessment Report",
    },
]

DEMO_QUERIES = [
    # ── Demand & Forecasting ──────────────────────────────────────────────────
    {
        "group": "Demand Planning",
        "query": "What is the total forecasted demand for Q1 2025 and which category is growing fastest?",
        "top_k": 4,
        "filters": {"doc_type": "demand_plan"},
    },
    {
        "group": "Demand Planning",
        "query": "What is the demand forecast for Consumer Electronics and which SKUs are the biggest drivers?",
        "top_k": 4,
        "filters": {"doc_type": "demand_plan"},
    },
    # ── Supplier Information ──────────────────────────────────────────────────
    {
        "group": "Supplier Intelligence",
        "query": "Which suppliers have a single-source risk and what is being done about it?",
        "top_k": 5,
        "filters": {},
    },
    {
        "group": "Supplier Intelligence",
        "query": "Who are our top suppliers by annual spend and what are their on-time delivery rates?",
        "top_k": 5,
        "filters": {"doc_type": "supplier_info"},
    },
    {
        "group": "Supplier Intelligence",
        "query": "Which supplier should I use for EU-compliant consumer electronics and why?",
        "top_k": 4,
        "filters": {},
    },
    # ── Inventory Policy ─────────────────────────────────────────────────────
    {
        "group": "Inventory Policy",
        "query": "How is safety stock calculated and what are the service level targets by product category?",
        "top_k": 4,
        "filters": {"doc_type": "inventory_policy"},
    },
    {
        "group": "Inventory Policy",
        "query": "What happens when inventory has not moved in 180 days?",
        "top_k": 3,
        "filters": {"doc_type": "inventory_policy"},
    },
    # ── Risk Assessment ───────────────────────────────────────────────────────
    {
        "group": "Risk Management",
        "query": "What are the critical supply chain risks in Q1 2025 and what is the mitigation plan?",
        "top_k": 5,
        "filters": {"doc_type": "risk_assessment"},
    },
    {
        "group": "Risk Management",
        "query": "What is our exposure if US-China trade tariffs increase and what contingencies exist?",
        "top_k": 4,
        "filters": {},
    },
    # ── Cross-document reasoning ──────────────────────────────────────────────
    {
        "group": "Cross-Document Analysis",
        "query": "Mitsuya Precision is flagged as a single-source supplier. What is the demand for their products and what is the risk mitigation timeline?",
        "top_k": 6,
        "filters": {},
    },
]

# ── HELPERS ─────────────────────────────────────────────────────────────────────


def print_header(text: str, char: str = "═") -> None:
    width = 70
    print(f"\n{char * width}")
    print(f"  {text}")
    print(f"{char * width}")


def print_section(text: str) -> None:
    print(f"\n  {'─' * 60}")
    print(f"  {text}")
    print(f"  {'─' * 60}")


def print_ok(text: str) -> None:
    print(f"  ✓  {text}")


def print_fail(text: str) -> None:
    print(f"  ✗  {text}")


def print_info(text: str) -> None:
    print(f"  →  {text}")


# ── API CLIENT ──────────────────────────────────────────────────────────────────


class DemoClient:
    def __init__(self, host: str, api_key: str | None):
        self.host = host.rstrip("/")
        self.session = requests.Session()
        if api_key:
            self.session.headers["X-API-Key"] = api_key

    def health(self) -> dict:
        return self.session.get(f"{self.host}/health", timeout=5).json()

    def upload(self, file_path: Path, supplier: str, doc_type: str, date_period: str) -> dict:
        with open(file_path, "rb") as f:
            resp = self.session.post(
                f"{self.host}/api/documents/upload",
                files={"file": (file_path.name, f)},
                data={"supplier": supplier, "doc_type": doc_type, "date_period": date_period},
                timeout=30,
            )
        resp.raise_for_status()
        return resp.json()

    def job_status(self, job_id: str) -> dict:
        return self.session.get(f"{self.host}/api/documents/status/{job_id}", timeout=5).json()

    def wait_for_job(self, job_id: str, timeout: int = 120) -> str:
        """Poll job until DONE or FAILED, return final status."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            status = str(self.job_status(job_id).get("status", "unknown")).lower()
            if status in ("done", "failed"):
                return status
            time.sleep(2)
        return "timeout"

    def list_documents(self) -> dict:
        return self.session.get(f"{self.host}/api/documents/list", timeout=5).json()

    def query(self, query: str, top_k: int = 5, filters: dict | None = None) -> dict:
        payload: dict = {"query": query, "top_k": top_k}
        if filters:
            payload["filters"] = filters
        resp = self.session.post(
            f"{self.host}/api/query/",
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()


# ── DEMO STEPS ──────────────────────────────────────────────────────────────────


def check_health(client: DemoClient) -> bool:
    print_section("Step 1: Health Check")
    try:
        health = client.health()
        status = health.get("status", "unknown")
        if status == "healthy":
            print_ok(f"API is healthy — {health.get('service')} v{health.get('version')}")
            components = health.get("components", {})
            for name, val in components.items():
                print_info(f"{name}: {val}")
            return True
        else:
            print_fail(f"API unhealthy: {status}")
            print_info("Is Qdrant running? Try: docker run -p 6333:6333 qdrant/qdrant")
            return False
    except requests.ConnectionError:
        print_fail(f"Cannot connect to {client.host}")
        print_info("Is the API running? Try: uvicorn src.main:app --reload")
        return False


def upload_documents(client: DemoClient) -> bool:
    print_section("Step 2: Upload Demo Documents")
    all_ok = True

    for doc in DEMO_FILES:
        path: Path = doc["path"]  # type: ignore[assignment]
        if not path.exists():
            print_fail(f"File not found: {path}")
            all_ok = False
            continue

        print(f"\n  Uploading: {doc['description']}")
        try:
            result = client.upload(
                path,
                supplier=str(doc["supplier"]),
                doc_type=str(doc["doc_type"]),
                date_period=str(doc["date_period"]),
            )
            job_id = result.get("job_id")
            print_info(f"Job submitted: {job_id}")

            print("  →  Indexing...", end=" ")
            sys.stdout.flush()
            final_status = client.wait_for_job(job_id, timeout=120)

            if final_status == "done":
                print_ok(f"Indexed successfully  [{doc['doc_type']}]")
            else:
                print_fail(f"Indexing {final_status.upper()} — check API logs")
                all_ok = False

        except requests.HTTPError as e:
            print_fail(f"Upload failed: {e}")
            all_ok = False

    return all_ok


def run_queries(client: DemoClient) -> None:
    print_section("Step 3: Run Demo Queries")

    current_group = ""
    for i, demo in enumerate(DEMO_QUERIES, 1):
        group = demo["group"]
        if group != current_group:
            print(f"\n  ── {group} ──")
            current_group = group

        print(f"\n  [{i}/{len(DEMO_QUERIES)}] {demo['query'][:70]}...")
        filters = demo.get("filters") or {}
        if filters:
            print_info(f"Filters: {json.dumps(filters)}")

        try:
            t0 = time.time()
            result = client.query(
                query=str(demo["query"]),
                top_k=int(demo.get("top_k", 5)),  # type: ignore[arg-type]
                filters=filters if filters else None,
            )
            elapsed = time.time() - t0

            answer = result.get("answer", "No answer returned")
            sources = result.get("sources", [])

            print(f"\n  ANSWER ({elapsed:.1f}s):")
            # Wrap long answer text to 65 chars
            for line in answer.split("\n"):
                stripped = line.strip()
                if stripped:
                    print(f"    {stripped}")

            if sources:
                print(f"\n  SOURCES ({len(sources)}):")
                for s in sources[:3]:  # show at most 3
                    fname = s.get("document", "unknown")
                    score = s.get("score")
                    score_str = f" (score: {score:.3f})" if score else ""
                    print(f"    • {fname}{score_str}")

        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 503:
                print_fail("Index not ready yet. Upload may still be processing.")
            else:
                print_fail(f"Query failed: {e}")
        except Exception as e:
            print_fail(f"Unexpected error: {e}")

        time.sleep(0.5)  # brief pause between queries


def show_document_list(client: DemoClient) -> None:
    print_section("Step 4: Indexed Documents")
    try:
        result = client.list_documents()
        docs = result.get("documents", [])
        if not docs:
            print_info("No documents found in index.")
            return
        print(f"  Total indexed documents: {len(docs)}")
        for doc in docs:
            fname = doc.get("filename", "?")
            size = doc.get("size", 0)
            print(f"    • {fname}  [{size} bytes]")
    except Exception as e:
        print_fail(f"Could not list documents: {e}")


# ── MAIN ────────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="SupplyChain RAG Assistant Demo")
    parser.add_argument("--host", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--api-key", default=None, help="API key (if auth is enabled)")
    parser.add_argument(
        "--skip-upload",
        action="store_true",
        help="Skip document upload (use if already indexed)",
    )
    args = parser.parse_args()

    client = DemoClient(host=args.host, api_key=args.api_key)

    print_header("SupplyChain RAG Assistant — Live Demo")
    print(f"  API:  {args.host}")
    print(f"  Auth: {'enabled (key provided)' if args.api_key else 'not configured'}")

    # 1. Health check
    if not check_health(client):
        sys.exit(1)

    # 2. Upload documents
    if not args.skip_upload:
        upload_ok = upload_documents(client)
        if not upload_ok:
            print("\n  Some uploads failed but continuing with queries...")
        # Brief wait after indexing to ensure Qdrant index is flushed
        print_info("Waiting 3 seconds for index to settle...")
        time.sleep(3)
    else:
        print_info("Skipping upload (--skip-upload flag set)")

    # 3. Show indexed documents
    show_document_list(client)

    # 4. Run queries
    run_queries(client)

    print_header("Demo Complete", char="═")
    print("  Try interactive queries: open http://localhost:8000/docs")
    print("  Stream a query:  curl -N -X POST http://localhost:8000/api/query/stream \\")
    print('    -H "Content-Type: application/json" \\')
    print('    -d \'{"query": "What are the critical risks?", "top_k": 5}\'\n')


if __name__ == "__main__":
    main()
