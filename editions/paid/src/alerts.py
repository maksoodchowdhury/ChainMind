from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from urllib import request as urllib_request

logger = logging.getLogger(__name__)

_last_alert_sent_at: float = 0.0


def reset_alert_state() -> None:
    """Reset alert delivery state (used by tests)."""
    global _last_alert_sent_at
    _last_alert_sent_at = 0.0


def _cooldown_remaining(cooldown_seconds: int) -> int:
    if _last_alert_sent_at <= 0:
        return 0
    elapsed = time.time() - _last_alert_sent_at
    remaining = max(0, int(cooldown_seconds - elapsed))
    return remaining


def _signature_headers(secret: str | None, body: bytes, timestamp: int) -> dict[str, str]:
    if not secret:
        return {}
    message = f"{timestamp}.".encode("utf-8") + body
    signature = hmac.new(
        secret.encode("utf-8"),
        msg=message,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return {
        "X-SLO-Timestamp": str(timestamp),
        "X-SLO-Signature": f"sha256={signature}",
    }


def _perform_webhook_post(url: str, body: bytes, headers: dict[str, str], timeout_seconds: int) -> None:
    req = urllib_request.Request(
        url,
        data=body,
        headers=headers,
        method="POST",
    )
    with urllib_request.urlopen(req, timeout=timeout_seconds) as resp:
        code = resp.getcode()
        if code < 200 or code >= 300:
            raise RuntimeError(f"Webhook returned HTTP {code}")


def send_slo_breach_alert(
    webhook_url: str,
    payload: dict,
    timeout_seconds: int = 5,
    signing_secret: str | None = None,
    max_attempts: int = 3,
    backoff_seconds: float = 1.0,
) -> None:
    """Send SLO breach payload to a generic webhook endpoint with retries."""
    body = json.dumps(payload).encode("utf-8")
    attempts = max(1, int(max_attempts))
    base_backoff = max(0.0, float(backoff_seconds))

    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        timestamp = int(time.time())
        headers = {"Content-Type": "application/json"}
        headers.update(_signature_headers(signing_secret, body, timestamp))
        try:
            _perform_webhook_post(webhook_url, body, headers, timeout_seconds)
            return
        except Exception as exc:
            last_error = exc
            if attempt >= attempts:
                break
            sleep_seconds = base_backoff * (2 ** (attempt - 1))
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

    raise RuntimeError(f"Webhook delivery failed after {attempts} attempt(s): {last_error}")


def maybe_send_slo_alert(
    *,
    webhook_url: str | None,
    webhook_secret: str | None,
    cooldown_seconds: int,
    max_attempts: int,
    backoff_seconds: float,
    slo_status: dict,
    service: str,
    version: str,
) -> dict:
    """Send an alert for breached SLO status when allowed by config and cooldown."""
    global _last_alert_sent_at

    if slo_status.get("status") != "breached":
        return {"sent": False, "reason": "slo_healthy"}

    if not webhook_url:
        return {"sent": False, "reason": "webhook_not_configured"}

    remaining = _cooldown_remaining(max(0, cooldown_seconds))
    if remaining > 0:
        return {
            "sent": False,
            "reason": "cooldown_active",
            "retry_after_seconds": remaining,
        }

    payload = {
        "event": "slo_breach",
        "service": service,
        "version": version,
        "timestamp": int(time.time()),
        "slo": slo_status,
    }

    try:
        send_slo_breach_alert(
            webhook_url,
            payload,
            signing_secret=webhook_secret,
            max_attempts=max_attempts,
            backoff_seconds=backoff_seconds,
        )
        _last_alert_sent_at = time.time()
        logger.warning("SLO breach alert sent to webhook")
        return {"sent": True, "reason": "delivered"}
    except Exception as exc:
        logger.error(f"Failed to deliver SLO alert: {exc}")
        return {"sent": False, "reason": "delivery_failed", "error": str(exc)}
