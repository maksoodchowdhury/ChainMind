from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.middleware import RateLimitMiddleware


def test_rate_limit_enforced():
    app = FastAPI()

    @app.get("/api/ping")
    async def ping():
        return {"ok": True}

    app.add_middleware(
        RateLimitMiddleware,
        enabled=True,
        requests_per_window=2,
        window_seconds=60,
    )

    client = TestClient(app)
    assert client.get("/api/ping").status_code == 200
    assert client.get("/api/ping").status_code == 200
    blocked = client.get("/api/ping")
    assert blocked.status_code == 429
    assert blocked.json()["detail"] == "Rate limit exceeded. Please retry later."


def test_rate_limit_exempt_path_not_limited():
    app = FastAPI()

    @app.get("/health")
    async def health():
        return {"ok": True}

    app.add_middleware(
        RateLimitMiddleware,
        enabled=True,
        requests_per_window=1,
        window_seconds=60,
    )

    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert client.get("/health").status_code == 200
