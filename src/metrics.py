from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from threading import Lock

_LOCK = Lock()
_MAX_SAMPLES = 2000
_latency_samples_ms: deque[float] = deque(maxlen=_MAX_SAMPLES)
_status_codes: deque[int] = deque(maxlen=_MAX_SAMPLES)
_by_path: dict[str, dict[str, deque]] = {}


def reset_metrics() -> None:
    """Reset metric samples (primarily used by tests)."""
    with _LOCK:
        _latency_samples_ms.clear()
        _status_codes.clear()
        _by_path.clear()


def record_request(path: str, status_code: int, duration_ms: float) -> None:
    """Record a request sample for operational metrics."""
    with _LOCK:
        _latency_samples_ms.append(float(duration_ms))
        _status_codes.append(int(status_code))

        path_bucket = _by_path.setdefault(
            path,
            {
                "latency_ms": deque(maxlen=500),
                "status_codes": deque(maxlen=500),
            },
        )
        path_bucket["latency_ms"].append(float(duration_ms))
        path_bucket["status_codes"].append(int(status_code))


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    if percentile <= 0:
        return min(values)
    if percentile >= 100:
        return max(values)
    values_sorted = sorted(values)
    rank = (len(values_sorted) - 1) * (percentile / 100.0)
    lower = int(rank)
    upper = min(lower + 1, len(values_sorted) - 1)
    weight = rank - lower
    return values_sorted[lower] * (1 - weight) + values_sorted[upper] * weight


def _latency_stats(values: list[float]) -> dict:
    if not values:
        return {
            "avg": 0.0,
            "max": 0.0,
            "p50": 0.0,
            "p95": 0.0,
            "p99": 0.0,
        }
    return {
        "avg": round(sum(values) / len(values), 2),
        "max": round(max(values), 2),
        "p50": round(_percentile(values, 50), 2),
        "p95": round(_percentile(values, 95), 2),
        "p99": round(_percentile(values, 99), 2),
    }


def snapshot_metrics(service: str, version: str) -> dict:
    """Build a snapshot of operational request metrics."""
    with _LOCK:
        latencies = list(_latency_samples_ms)
        statuses = list(_status_codes)

        total_requests = len(statuses)
        total_errors = sum(1 for s in statuses if s >= 400)
        error_rate = (total_errors / total_requests) if total_requests else 0.0

        by_path_payload = {}
        for path, bucket in _by_path.items():
            path_latencies = list(bucket["latency_ms"])
            path_statuses = list(bucket["status_codes"])
            path_total = len(path_statuses)
            path_errors = sum(1 for s in path_statuses if s >= 400)
            by_path_payload[path] = {
                "requests": path_total,
                "errors": path_errors,
                "error_rate": round((path_errors / path_total) if path_total else 0.0, 4),
                "latency_ms": _latency_stats(path_latencies),
            }

    return {
        "service": service,
        "version": version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "totals": {
            "requests": total_requests,
            "errors": total_errors,
            "error_rate": round(error_rate, 4),
        },
        "latency_ms": _latency_stats(latencies),
        "by_path": by_path_payload,
    }


def evaluate_slo_status(
    snapshot: dict,
    *,
    error_rate_threshold: float,
    p95_latency_ms_threshold: float,
    minimum_requests: int,
) -> dict:
    """Evaluate whether current metrics violate configured SLO guardrails."""
    totals = snapshot.get("totals", {})
    latency = snapshot.get("latency_ms", {})

    requests = int(totals.get("requests", 0))
    error_rate = float(totals.get("error_rate", 0.0))
    p95_latency = float(latency.get("p95", 0.0))
    enough_samples = requests >= max(1, minimum_requests)

    error_rate_breached = enough_samples and error_rate > error_rate_threshold
    latency_breached = enough_samples and p95_latency > p95_latency_ms_threshold
    healthy = not (error_rate_breached or latency_breached)

    return {
        "status": "healthy" if healthy else "breached",
        "enough_samples": enough_samples,
        "requests_observed": requests,
        "thresholds": {
            "error_rate": error_rate_threshold,
            "p95_latency_ms": p95_latency_ms_threshold,
            "minimum_requests": minimum_requests,
        },
        "observed": {
            "error_rate": round(error_rate, 4),
            "p95_latency_ms": round(p95_latency, 2),
        },
        "breaches": {
            "error_rate": error_rate_breached,
            "p95_latency_ms": latency_breached,
        },
    }
