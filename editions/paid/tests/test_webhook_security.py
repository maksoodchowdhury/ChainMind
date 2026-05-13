from src.webhook_security import compute_signature, verify_webhook_signature


def test_verify_webhook_signature_success():
    body = b'{"event":"slo_breach"}'
    ts = 1700000000
    secret = "top-secret"
    sig = compute_signature(secret, ts, body)

    ok, reason = verify_webhook_signature(
        headers={
            "X-SLO-Timestamp": str(ts),
            "X-SLO-Signature": sig,
        },
        body=body,
        secret=secret,
        max_age_seconds=600,
        now_epoch_seconds=1700000100,
    )
    assert ok is True
    assert reason == "ok"


def test_verify_webhook_signature_replay_window():
    body = b'{}'
    ts = 1700000000
    secret = "top-secret"
    sig = compute_signature(secret, ts, body)

    ok, reason = verify_webhook_signature(
        headers={
            "X-SLO-Timestamp": str(ts),
            "X-SLO-Signature": sig,
        },
        body=body,
        secret=secret,
        max_age_seconds=60,
        now_epoch_seconds=1700001000,
    )
    assert ok is False
    assert reason == "timestamp_out_of_window"


def test_verify_webhook_signature_mismatch():
    body = b'{}'
    ts = 1700000000

    ok, reason = verify_webhook_signature(
        headers={
            "X-SLO-Timestamp": str(ts),
            "X-SLO-Signature": "sha256=bad",
        },
        body=body,
        secret="top-secret",
        max_age_seconds=600,
        now_epoch_seconds=1700000001,
    )
    assert ok is False
    assert reason == "signature_mismatch"
