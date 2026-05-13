from unittest.mock import patch

from src.alerts import (
    _signature_headers,
    maybe_send_slo_alert,
    reset_alert_state,
    send_slo_breach_alert,
)


def test_maybe_send_slo_alert_skips_when_healthy():
    reset_alert_state()
    result = maybe_send_slo_alert(
        webhook_url="http://example.com/webhook",
        webhook_secret=None,
        cooldown_seconds=300,
        max_attempts=3,
        backoff_seconds=0,
        slo_status={"status": "healthy"},
        service="svc",
        version="1.0",
    )
    assert result["sent"] is False
    assert result["reason"] == "slo_healthy"


def test_maybe_send_slo_alert_skips_without_webhook():
    reset_alert_state()
    result = maybe_send_slo_alert(
        webhook_url=None,
        webhook_secret=None,
        cooldown_seconds=300,
        max_attempts=3,
        backoff_seconds=0,
        slo_status={"status": "breached"},
        service="svc",
        version="1.0",
    )
    assert result["sent"] is False
    assert result["reason"] == "webhook_not_configured"


def test_maybe_send_slo_alert_delivers():
    reset_alert_state()
    with patch("src.alerts.send_slo_breach_alert") as send_mock:
        result = maybe_send_slo_alert(
            webhook_url="http://example.com/webhook",
            webhook_secret="secret",
            cooldown_seconds=300,
            max_attempts=3,
            backoff_seconds=0,
            slo_status={"status": "breached"},
            service="svc",
            version="1.0",
        )
    send_mock.assert_called_once()
    assert result["sent"] is True
    assert result["reason"] == "delivered"


def test_signature_headers_contains_hmac_when_secret_present():
    body = b'{"event":"x"}'
    headers = _signature_headers("my-secret", body, 1710000000)
    assert "X-SLO-Timestamp" in headers
    assert headers["X-SLO-Timestamp"] == "1710000000"
    assert headers["X-SLO-Signature"].startswith("sha256=")


def test_send_slo_breach_alert_retries_then_succeeds():
    payload = {"event": "slo_breach"}
    with patch("src.alerts._perform_webhook_post") as post_mock:
        post_mock.side_effect = [RuntimeError("boom"), None]
        with patch("src.alerts.time.sleep") as sleep_mock:
            send_slo_breach_alert(
                "http://example.com/webhook",
                payload,
                signing_secret="my-secret",
                max_attempts=2,
                backoff_seconds=0.01,
            )
    assert post_mock.call_count == 2
    sleep_mock.assert_called_once()