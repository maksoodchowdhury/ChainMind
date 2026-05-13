import os
import time
from fastapi.testclient import TestClient

from src.webhook_security import compute_signature


# Set env before importing app module values
os.environ["WEBHOOK_SECRET"] = "dev-shared-secret"
os.environ["WEBHOOK_MAX_AGE_SECONDS"] = "300"

from demo.webhook_receiver import app  # noqa: E402


def test_webhook_receiver_rejects_bad_signature():
    client = TestClient(app)
    body = b'{"event":"slo_breach"}'
    ts = str(int(time.time()))
    response = client.post(
        "/webhook/slo",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-SLO-Timestamp": ts,
            "X-SLO-Signature": "sha256=bad",
        },
    )
    assert response.status_code == 401


def test_webhook_receiver_accepts_signed_payload():
    client = TestClient(app)
    body = b'{"event":"slo_breach","slo":{"status":"breached"}}'
    ts = str(int(time.time()))
    sig = compute_signature("dev-shared-secret", int(ts), body)
    response = client.post(
        "/webhook/slo",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-SLO-Timestamp": ts,
            "X-SLO-Signature": sig,
        },
    )
    assert response.status_code == 200
