from __future__ import annotations

import hashlib
import hmac
import time
from typing import Mapping


def compute_signature(secret: str, timestamp: int, body: bytes) -> str:
    """Compute SHA-256 HMAC signature over '<timestamp>.<raw-body>' format."""
    message = f"{timestamp}.".encode("utf-8") + body
    digest = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify_webhook_signature(
    *,
    headers: Mapping[str, str],
    body: bytes,
    secret: str,
    max_age_seconds: int = 300,
    now_epoch_seconds: int | None = None,
) -> tuple[bool, str]:
    """Verify webhook signature and replay window.

    Expected headers:
    - X-SLO-Timestamp: unix epoch seconds
    - X-SLO-Signature: sha256=<hmac>
    """
    ts_raw = headers.get("X-SLO-Timestamp") or headers.get("x-slo-timestamp")
    sig = headers.get("X-SLO-Signature") or headers.get("x-slo-signature")

    if not ts_raw:
        return False, "missing_timestamp"
    if not sig:
        return False, "missing_signature"

    try:
        ts = int(ts_raw)
    except (TypeError, ValueError):
        return False, "invalid_timestamp"

    now = int(time.time()) if now_epoch_seconds is None else int(now_epoch_seconds)
    max_age = max(1, int(max_age_seconds))
    if abs(now - ts) > max_age:
        return False, "timestamp_out_of_window"

    expected = compute_signature(secret, ts, body)
    if not hmac.compare_digest(expected, sig):
        return False, "signature_mismatch"

    return True, "ok"
