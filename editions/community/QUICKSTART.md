# Quick Start Guide

## 🚀 Launch in 3 Steps

### Step 1: Configure API Key
```bash
cp .env.example .env
# Edit .env and add your OpenAI API key (https://platform.openai.com/account/api-keys)
```

### Step 2: Choose Deployment Method

#### Option A: Local Development (Recommended)
```bash
# Terminal 1: Start Qdrant vector database
docker run -p 6333:6333 qdrant/qdrant:v1.7.0

# Terminal 2: Start API with reload
python -m uvicorn src.main:app --reload
# → API at http://localhost:8000
# → Docs at http://localhost:8000/docs
```

#### Option B: Docker Compose (Production)
```bash
docker-compose up --build
# → API at http://localhost:8000
# → Qdrant at http://localhost:6333
```

### Step 3: Test the System

**Upload a document** (in your browser or with curl):
```bash
curl -X POST http://localhost:8000/api/documents/upload \
  -F "file=@data/sample_supply_chain_forecast.txt"
```

**Query the RAG system**:
```bash
curl -X POST http://localhost:8000/api/query/ \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the Q3 demand forecast?", "top_k": 5}'
```

**Check health**:
```bash
curl http://localhost:8000/health
```

**Check readiness gate**:
```bash
curl http://localhost:8000/ready
```

**Check operational metrics**:
```bash
curl http://localhost:8000/metrics/operational
```

---

## Production Hardening Profile

Enable these environment settings in `.env` for a safer production baseline:

```bash
ENABLE_STRUCTURED_LOGGING=true
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS_PER_WINDOW=120
RATE_LIMIT_WINDOW_SECONDS=60
MAX_INFLIGHT_INGESTION_JOBS=50
AUTH_ENABLED=true
API_KEYS=replace-with-real-keys
```

What these controls do:
- `ENABLE_STRUCTURED_LOGGING`: emits JSON request logs with request IDs.
- `RATE_LIMIT_*`: protects API capacity against request spikes.
- `MAX_INFLIGHT_INGESTION_JOBS`: applies ingestion backpressure with `503` + `Retry-After`.
- `AUTH_ENABLED` + `API_KEYS`: protects API endpoints with API-key access control.

Optional SLO alerting controls:
- `SLO_WEBHOOK_URL`: destination endpoint for SLO breach alerts.
- `SLO_WEBHOOK_SECRET`: HMAC secret used to sign alert payloads.
- `SLO_WEBHOOK_MAX_ATTEMPTS`: number of delivery retries.
- `SLO_WEBHOOK_BACKOFF_SECONDS`: base exponential backoff between retries.

SLO alert webhook headers:
- `X-SLO-Timestamp`: Unix timestamp used for signature generation.
- `X-SLO-Signature`: `sha256=<hmac>` computed over `<timestamp>.<raw-body>`.

Trigger an alert evaluation run:

curl -X POST http://localhost:8000/alerts/slo/check

This endpoint evaluates SLO thresholds and sends a webhook event only when:
- SLO status is `breached`
- Webhook URL is configured
- Alert cooldown window has elapsed

Receiver-side verification (Python):

```python
from src.webhook_security import verify_webhook_signature

def handle_webhook(headers: dict[str, str], raw_body: bytes):
  ok, reason = verify_webhook_signature(
    headers=headers,
    body=raw_body,
    secret="your-shared-secret",
    max_age_seconds=300,
  )
  if not ok:
    return {"status": "rejected", "reason": reason}, 401
  return {"status": "accepted"}, 200
```

Local end-to-end receiver demo:

```bash
# Terminal 1: Start the webhook receiver
cd /path/to/SupplyChain-RAG-Assistant
source .venv/bin/activate
export WEBHOOK_SECRET=dev-shared-secret
python -m uvicorn demo.webhook_receiver:app --host 0.0.0.0 --port 9000 --reload

# Terminal 2: Start the main API
cd /path/to/SupplyChain-RAG-Assistant
source .venv/bin/activate
export SLO_WEBHOOK_URL=http://localhost:9000/webhook/slo
export SLO_WEBHOOK_SECRET=dev-shared-secret
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 3: Trigger SLO check (after generating some error traffic)
curl -X POST http://localhost:8000/alerts/slo/check
```

One-command alert flow demo (after Terminal 1 and 2 are running):

```bash
cd /path/to/SupplyChain-RAG-Assistant
source .venv/bin/activate
python demo/run_alert_flow.py --host http://localhost:8000 --receiver http://localhost:9000 --errors 30
```

With Makefile shortcuts:

```bash
make run-alert-demo
make test-alert-demo
```

The script will:
- verify API and receiver health
- generate controlled error traffic to trigger SLO breach
- call `/metrics/slo-status`
- call `/alerts/slo/check` and print notification outcome

---

## Readiness and Metrics Interpretation

`GET /ready` fields:
- `status`: `ready` or `not_ready`
- `mode`: `normal` or `degraded`
- `accepting_traffic`: `true` means safe to send production traffic
- `components`: dependency-level health (`qdrant`, `cache`)

`GET /metrics/operational` fields:
- `totals.requests`: total requests seen by this process
- `totals.errors`: total `4xx/5xx` responses
- `totals.error_rate`: error ratio from `0.0` to `1.0`
- `latency_ms.p50/p95/p99`: latency distribution for SLO tracking
- `by_path`: per-endpoint request/error/latency breakdown

Suggested baseline SLO targets:
- Availability: `>= 99.9%`
- API latency: `p95 <= 800ms` for non-streaming query routes
- Error rate: `<= 1%` sustained per 5-minute window
- Readiness: `accepting_traffic=true` before routing new traffic

---

## 📚 Documentation
- **README.md** - User-facing guide with API examples
- **ARCHITECTURE.md** - Deep dive into design and tech stack
- **docs/PHASE_COMPLIANCE.md** - Current Phase 1-5 capability verification
- **docs/RUNBOOK.md** - Deployment, canary/blue-green, rollback guidance
- **docs/INCIDENT_RESPONSE_PLAYBOOK.md** - Incident response workflow
- **docs/DR_RTO_RPO.md** - Recovery objective targets and DR procedure
- **Swagger UI** - http://localhost:8000/docs (interactive testing)

---

## 🧪 Run Tests
```bash
# All tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=src
```

---

## 🎯 Suggested Validation Path
1. Upload at least 3 domain documents and verify ingestion events (`/api/documents/events`)
2. Run scenario and workflow endpoints under `/api/intelligence/*`
3. Validate tenant/platform controls under `/api/platform/*`
4. Validate autonomous monitoring and action APIs under `/api/autonomy/*`
5. Execute full regression suite with `pytest -q`

---

**Need help?** See README.md or ARCHITECTURE.md for detailed information.
