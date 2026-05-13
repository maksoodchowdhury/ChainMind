#!/usr/bin/env python3
"""Run an end-to-end SLO alert flow demo.

Usage:
    python demo/run_alert_flow.py --host http://localhost:8000 --receiver http://localhost:9000
"""

import argparse
import sys
from typing import Any

import requests


def print_step(msg: str) -> None:
    print(f"\n==> {msg}")


def print_ok(msg: str) -> None:
    print(f"[OK] {msg}")


def print_fail(msg: str) -> None:
    print(f"[FAIL] {msg}")


def check_endpoint(session: requests.Session, url: str, name: str) -> bool:
    try:
        resp = session.get(url, timeout=5)
        if resp.status_code == 200:
            print_ok(f"{name} reachable: {url}")
            return True
        print_fail(f"{name} returned {resp.status_code}: {url}")
        return False
    except Exception as exc:
        print_fail(f"{name} unreachable: {url} ({exc})")
        return False


def generate_error_traffic(session: requests.Session, host: str, count: int) -> int:
    status_404 = 0
    for _ in range(count):
        resp = session.get(f"{host}/api/documents/status/non-existent-id", timeout=5)
        if resp.status_code == 404:
            status_404 += 1
    return status_404


def run_alert_flow(host: str, receiver: str, error_count: int, api_key: str | None = None) -> int:
    session = requests.Session()
    if api_key:
        session.headers["X-API-Key"] = api_key

    print_step("Checking API and receiver health")
    api_ok = check_endpoint(session, f"{host}/health", "Main API")
    receiver_ok = check_endpoint(session, f"{receiver}/health", "Webhook receiver")
    if not api_ok or not receiver_ok:
        return 1

    print_step(f"Generating error traffic ({error_count} 404 requests) to breach SLO")
    errors = generate_error_traffic(session, host, error_count)
    print_ok(f"Generated {errors}/{error_count} error responses")

    print_step("Checking SLO status")
    slo_resp = session.get(f"{host}/metrics/slo-status", timeout=10)
    slo_resp.raise_for_status()
    slo_data: dict[str, Any] = slo_resp.json()
    print_ok(f"SLO status: {slo_data.get('status')} (enough_samples={slo_data.get('enough_samples')})")

    print_step("Triggering alert check")
    alert_resp = session.post(f"{host}/alerts/slo/check", timeout=10)
    alert_resp.raise_for_status()
    alert_data: dict[str, Any] = alert_resp.json()

    notification = alert_data.get("notification", {})
    print_ok(f"Notification result: sent={notification.get('sent')} reason={notification.get('reason')}")

    print_step("Done")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the SLO webhook alert flow demo")
    parser.add_argument("--host", default="http://localhost:8000", help="Main API host")
    parser.add_argument("--receiver", default="http://localhost:9000", help="Webhook receiver host")
    parser.add_argument("--errors", type=int, default=30, help="Number of error requests to generate")
    parser.add_argument("--api-key", default=None, help="Optional API key header value")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    exit_code = run_alert_flow(
        host=args.host.rstrip("/"),
        receiver=args.receiver.rstrip("/"),
        error_count=max(1, args.errors),
        api_key=args.api_key,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
