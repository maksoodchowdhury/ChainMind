from unittest.mock import MagicMock, patch

from demo.run_alert_flow import run_alert_flow


def _response(status_code: int, payload: dict | None = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = payload or {}
    resp.raise_for_status.return_value = None
    return resp


def test_run_alert_flow_success_path():
    session = MagicMock()
    session.get.side_effect = [
        _response(200, {"status": "healthy"}),
        _response(200, {"status": "ok"}),
        *[_response(404, {"error": {"code": "http_404"}}) for _ in range(3)],
        _response(200, {"status": "breached", "enough_samples": True}),
    ]
    session.post.return_value = _response(
        200,
        {
            "notification": {"sent": True, "reason": "delivered"},
        },
    )

    with patch("demo.run_alert_flow.requests.Session", return_value=session):
        code = run_alert_flow("http://localhost:8000", "http://localhost:9000", error_count=3)

    assert code == 0
    assert session.post.called


def test_run_alert_flow_health_failure():
    session = MagicMock()
    session.get.side_effect = [
        _response(500, {}),
        _response(200, {"status": "ok"}),
    ]

    with patch("demo.run_alert_flow.requests.Session", return_value=session):
        code = run_alert_flow("http://localhost:8000", "http://localhost:9000", error_count=3)

    assert code == 1
