#!/usr/bin/env python3
"""Quality gate for CI/CD: fail on evaluation regression or missing baseline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")
    return json.loads(path.read_text())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current", required=True, help="Path to current quality report JSON")
    parser.add_argument("--baseline", required=True, help="Path to baseline quality report JSON")
    parser.add_argument("--max-groundedness-drop", type=float, default=0.03)
    parser.add_argument("--max-citation-precision-drop", type=float, default=0.03)
    args = parser.parse_args()

    current = load_json(Path(args.current))
    baseline = load_json(Path(args.baseline))

    curr_groundedness = float(current.get("groundedness", current.get("scores", {}).get("faithfulness", 0.0)))
    base_groundedness = float(baseline.get("groundedness", baseline.get("scores", {}).get("faithfulness", 0.0)))

    curr_citation = float(current.get("citation_precision", current.get("scores", {}).get("context_precision", 0.0)))
    base_citation = float(baseline.get("citation_precision", baseline.get("scores", {}).get("context_precision", 0.0)))

    groundedness_drop = base_groundedness - curr_groundedness
    citation_drop = base_citation - curr_citation

    failures = []
    if groundedness_drop > args.max_groundedness_drop:
        failures.append(
            f"Groundedness dropped by {groundedness_drop:.4f} (allowed {args.max_groundedness_drop:.4f})"
        )
    if citation_drop > args.max_citation_precision_drop:
        failures.append(
            f"Citation precision dropped by {citation_drop:.4f} (allowed {args.max_citation_precision_drop:.4f})"
        )

    if failures:
        print("QUALITY_GATE_FAILED")
        for f in failures:
            print(f" - {f}")
        return 1

    print("QUALITY_GATE_PASSED")
    print(
        json.dumps(
            {
                "groundedness_current": curr_groundedness,
                "groundedness_baseline": base_groundedness,
                "citation_precision_current": curr_citation,
                "citation_precision_baseline": base_citation,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
