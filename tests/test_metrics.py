from src.metrics import evaluate_slo_status, record_request, reset_metrics, snapshot_metrics


def test_snapshot_empty_metrics():
    reset_metrics()
    snap = snapshot_metrics("svc", "1.0")
    assert snap["totals"]["requests"] == 0
    assert snap["totals"]["errors"] == 0
    assert snap["latency_ms"]["p95"] == 0.0


def test_snapshot_with_data():
    reset_metrics()
    record_request("/a", 200, 10)
    record_request("/a", 500, 20)
    record_request("/b", 201, 30)

    snap = snapshot_metrics("svc", "1.0")
    assert snap["totals"]["requests"] == 3
    assert snap["totals"]["errors"] == 1
    assert snap["latency_ms"]["max"] == 30.0
    assert snap["by_path"]["/a"]["requests"] == 2
    assert snap["by_path"]["/a"]["errors"] == 1


def test_slo_status_not_enough_samples_is_healthy():
    snap = {
        "totals": {"requests": 2, "error_rate": 0.5},
        "latency_ms": {"p95": 1200.0},
    }
    status = evaluate_slo_status(
        snap,
        error_rate_threshold=0.01,
        p95_latency_ms_threshold=800.0,
        minimum_requests=10,
    )
    assert status["enough_samples"] is False
    assert status["status"] == "healthy"


def test_slo_status_breached_on_error_rate_and_latency():
    snap = {
        "totals": {"requests": 100, "error_rate": 0.02},
        "latency_ms": {"p95": 900.0},
    }
    status = evaluate_slo_status(
        snap,
        error_rate_threshold=0.01,
        p95_latency_ms_threshold=800.0,
        minimum_requests=20,
    )
    assert status["enough_samples"] is True
    assert status["status"] == "breached"
    assert status["breaches"]["error_rate"] is True
    assert status["breaches"]["p95_latency_ms"] is True