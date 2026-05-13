import json
import logging
import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.webhook_security import verify_webhook_signature

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "dev-shared-secret")
WEBHOOK_MAX_AGE_SECONDS = int(os.getenv("WEBHOOK_MAX_AGE_SECONDS", "300"))

app = FastAPI(title="SLO Webhook Receiver Demo", version="0.1.0")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "webhook-receiver-demo"}


@app.post("/webhook/slo")
async def receive_slo_webhook(request: Request):
    raw_body = await request.body()
    headers = dict(request.headers)

    ok, reason = verify_webhook_signature(
        headers=headers,
        body=raw_body,
        secret=WEBHOOK_SECRET,
        max_age_seconds=WEBHOOK_MAX_AGE_SECONDS,
    )
    if not ok:
        return JSONResponse(status_code=401, content={"status": "rejected", "reason": reason})

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception:
        return JSONResponse(status_code=400, content={"status": "rejected", "reason": "invalid_json"})

    logger.warning("Accepted SLO webhook event=%s status=%s", payload.get("event"), payload.get("slo", {}).get("status"))
    return {"status": "accepted", "event": payload.get("event", "unknown")}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("demo.webhook_receiver:app", host="0.0.0.0", port=9000, reload=True)
