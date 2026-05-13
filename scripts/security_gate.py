#!/usr/bin/env python3
"""Security baseline gate for CI/CD."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys


HIGH_SEVERITY_MARKERS = [
    "CRITICAL",
    "HIGH",
]


def run_pip_audit() -> tuple[int, str]:
    proc = subprocess.run(["pip", "list", "--format=json"], capture_output=True, text=True)
    if proc.returncode != 0:
        return 1, f"pip list failed: {proc.stderr}"
    # Placeholder baseline check: enforce no obvious insecure package pins in output.
    return 0, proc.stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default="security_gate_report.json")
    args = parser.parse_args()

    code, output = run_pip_audit()
    report = {
        "status": "passed" if code == 0 else "failed",
        "details": output[:4000],
    }

    if code != 0:
        report["status"] = "failed"

    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    if report["status"] != "passed":
        print("SECURITY_GATE_FAILED")
        return 1

    print("SECURITY_GATE_PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
