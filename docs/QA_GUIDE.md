# SupplyChain RAG Assistant — QA & Testing Guide

> **Who is this guide for?** Anyone responsible for making sure the system works correctly — testers, product owners, and developers. You don't need to be a programmer to follow the manual test checklists, but the automated testing sections do require Python.

---

## Table of Contents

1. [What Does "Quality" Mean for a RAG System?](#1-what-does-quality-mean-for-a-rag-system)
2. [Manual Testing Checklist](#2-manual-testing-checklist)
3. [Automated Tests — How to Run Them](#3-automated-tests--how-to-run-them)
4. [What Each Test Covers](#4-what-each-test-covers)
5. [RAG Quality Evaluation (RAGAS)](#5-rag-quality-evaluation-ragas)
6. [Performance Testing](#6-performance-testing)
7. [Common Issues and How to Diagnose Them](#7-common-issues-and-how-to-diagnose-them)
8. [Test Environments](#8-test-environments)
9. [How to Write New Tests With AI Assistance](#9-how-to-write-new-tests-with-ai-assistance)
10. [Release Checklist](#10-release-checklist)

---

## 1. What Does "Quality" Mean for a RAG System?

A RAG system has more dimensions of quality than a typical application. Here is how to think about it:

| Quality dimension | Question to ask | How we measure it |
|---|---|---|
| **Correctness** | Is the answer factually accurate given the documents? | Manual spot-checks + RAGAS faithfulness score |
| **Relevance** | Does the answer actually address the question? | RAGAS answer relevancy score |
| **Source coverage** | Are the right document chunks being retrieved? | RAGAS context precision + recall |
| **No hallucination** | Does the LLM add facts not in the documents? | RAGAS faithfulness score (should be > 0.8) |
| **Latency** | How long does a query take? | Response time logged; target < 5 seconds |
| **Reliability** | Does the API handle errors gracefully? | Error rate monitoring; fault injection tests |
| **Deduplication** | Are duplicate uploads handled? | Fingerprint tests |

---

## 2. Manual Testing Checklist

Use this checklist to verify the system works end-to-end without running any code. Open a browser to `http://localhost:8000/docs` to run these tests.

### 2.1 Startup & Health

- [ ] Go to `http://localhost:8000/health` — response should include `"status": "healthy"`
- [ ] API version shown in health response matches expected version (`0.2.0`)
- [ ] `http://localhost:8000/docs` loads the interactive API documentation

### 2.2 Document Upload

- [ ] Upload a small `.txt` file — should get a `job_id` back immediately (202 response)
- [ ] Check job status — `PENDING` → `PROCESSING` → `DONE` within 30 seconds
- [ ] Upload the same file again — job should complete immediately (fingerprint detected)
- [ ] Upload a `.csv` file — should index successfully
- [ ] Upload an empty file — should fail gracefully with a meaningful error message
- [ ] `GET /api/documents/list` after upload — the uploaded file should appear

### 2.3 Querying

- [ ] Ask a question when no documents are indexed — should return a helpful "no information" message, not crash
- [ ] Ask a question about an uploaded document — answer should contain accurate information from that document
- [ ] Ask a question about something not in any document — answer should say it cannot find relevant information
- [ ] Use `doc_type` filter — answer should only use matching documents
- [ ] Use `top_k=1` — answer based on one source only; source count should be 1
- [ ] Use `top_k=10` — answer based on up to 10 sources

### 2.4 Streaming

- [ ] Call `POST /api/query/stream` — response should arrive as a stream (characters appear progressively)
  - In terminal: `curl -N -X POST http://localhost:8000/api/query/stream -H "Content-Type: application/json" -d '{"query": "What are the critical risks?", "top_k": 3}'`

### 2.5 Authentication (if enabled)

- [ ] With `AUTH_ENABLED=true` and `API_KEYS=test123`, a request without the header should return `401`
- [ ] The same request with `X-API-Key: test123` header should succeed
- [ ] `/health`, `/docs`, `/redoc` should be accessible without an API key even when auth is enabled

### 2.6 Cache (if Redis enabled)

- [ ] Ask the same question twice — second response should be significantly faster (cache hit)
- [ ] Call `DELETE /cache` — should return `{"status": "cleared", "deleted": N}`
- [ ] Ask the question again — should take the same time as the first request (cache was cleared)

---

## 3. Automated Tests — How to Run Them

### Prerequisites

```bash
# Make sure you are in the project folder
cd /home/maks/dev/SupplyChain-RAG-Assistant

# Activate the Python virtual environment
source .venv/bin/activate  # Linux/Mac
# OR: .venv\Scripts\activate  (Windows)
```

### Run all tests

```bash
python -m pytest tests/ -v
```

You should see output like:
```
tests/test_api.py::test_root_endpoint PASSED
tests/test_api.py::test_health_check PASSED
...
============= N passed in X.Xs ==============
```

### Run a specific test file

```bash
# Test only document processor logic
python -m pytest tests/test_document_processor.py -v

# Test only API endpoints
python -m pytest tests/test_api.py -v
```

### Run with detailed output on failure

```bash
python -m pytest tests/ -v --tb=long
```

### Check test coverage (what % of code is tested)

```bash
pip install pytest-cov
python -m pytest tests/ --cov=src --cov-report=term-missing
```

The output shows which lines of code are not covered by any test.

---

## 4. What Each Test Covers

### `tests/test_api.py` — API Endpoint Tests (7 tests)

| Test name | What it verifies |
|---|---|
| `test_root_endpoint` | Root `/` returns service info |
| `test_health_check` | `/health` returns healthy status |
| `test_list_documents_empty` | Empty list when no documents indexed |
| `test_query_empty_index` | Graceful response when nothing is indexed |
| `test_query_success` | Query returns an answer with sources |
| `test_query_with_filters` | Metadata filters are passed through correctly |
| `test_query_no_index` | 503 returned when index is completely unavailable |

### `tests/test_config.py` — Configuration Tests (4 tests)

| Test name | What it verifies |
|---|---|
| `test_settings_from_env` | Environment variables are loaded correctly |
| `test_qdrant_connection_url` | URL is constructed from host/port |
| `test_custom_qdrant_url` | Custom URL overrides host/port |
| `test_default_settings` | Defaults are applied when no env vars set |

### `tests/test_ingestion.py` — Background Job Tests (8 tests)

| Test name | What it verifies |
|---|---|
| `test_create_job` | Job created with PENDING status |
| `test_get_job` | Job retrieved by ID |
| `test_list_jobs` | All jobs listed correctly |
| `test_run_ingestion_success` | Background job completes and sets DONE |
| `test_run_ingestion_failure` | Errors set job to FAILED with message |
| `test_run_ingestion_file_not_found` | Missing file sets FAILED gracefully |
| `test_job_status_transitions` | Status goes PENDING → PROCESSING → DONE |
| `test_concurrent_jobs` | Multiple jobs can run without conflict |

### `tests/test_eval.py` — Evaluation Pipeline Tests (5 tests)

| Test name | What it verifies |
|---|---|
| `test_evaluate_empty_samples` | Empty input handled gracefully |
| `test_ragas_graceful_degradation` | Works without ragas package installed |
| `test_sample_fields` | Required fields validated |
| `test_result_structure` | Response has expected metric fields |
| `test_mocked_ragas` | Full eval flow with mocked RAGAS |

### `tests/test_document_processor.py` — Document Processing Tests (13 tests)

| Test name | What it verifies |
|---|---|
| `test_file_hash_returns_sha256` | Hash is 64-char hex, deterministic |
| `test_file_hash_different_content` | Different content → different hash |
| `test_is_already_indexed_false_for_new_file` | New files return False |
| `test_register_and_check_indexed` | Register + re-check returns True |
| `test_register_updates_existing` | Changed file content → not indexed |
| `test_load_txt_file` | TXT files load correctly with metadata |
| `test_load_csv_file` | CSV rows batched into documents |
| `test_load_markdown_file` | Markdown files load correctly |
| `test_load_unsupported_extension_falls_back` | Unknown extensions don't crash |
| `test_apply_chunking_sentence_strategy` | Sentence chunking produces nodes |
| `test_apply_chunking_fixed_strategy` | Fixed chunking produces nodes |
| `test_apply_chunking_unknown_strategy_falls_back` | Unknown strategy falls back |
| `test_apply_chunking_semantic_without_embed_falls_back` | Semantic without model falls back |
| `test_get_fingerprint_registry_empty_when_no_file` | Missing file → empty dict |

---

## 5. RAG Quality Evaluation (RAGAS)

RAGAS (Retrieval-Augmented Generation Assessment) is an industry-standard framework for measuring how good a RAG system's answers are. It requires the `ragas` and `datasets` packages.

### Install RAGAS

```bash
pip install "ragas>=0.1.0,<0.2.0" datasets
```

### Run a batch evaluation via API

```bash
curl -X POST http://localhost:8000/api/eval/ \
  -H "Content-Type: application/json" \
  -d '{
    "samples": [
      {
        "question": "What is the safety stock formula?",
        "answer": "Safety Stock = Z × σ_demand × √(Lead_time)",
        "contexts": ["Safety Stock (SS) is calculated using: SS = Z × σ_demand × √(Lead_time)"],
        "ground_truth": "Safety Stock = Z × σ × √(L)"
      }
    ]
  }'
```

### Metrics explained (non-technical)

| Metric | What it measures | Target |
|---|---|---|
| **Faithfulness** | Does the answer stay true to the retrieved context? Does it add any facts that weren't in the documents? | > 0.80 |
| **Answer Relevancy** | Does the answer actually address the question that was asked? | > 0.75 |
| **Context Precision** | Of the retrieved chunks, what fraction were actually relevant? | > 0.70 |
| **Context Recall** | Did the system retrieve all the information needed to answer the question? | > 0.70 |

A score of 1.0 is perfect; 0.0 is the worst. Anything above the target thresholds indicates a well-functioning system.

### Run a single query + evaluate in one call

```bash
curl -X POST http://localhost:8000/api/eval/query-and-eval \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What are the critical supply chain risks?",
    "ground_truth": "Single-source dependency on Mitsuya Precision and US-China tariff risk are the two critical risks."
  }'
```

### When to run evaluations

- After uploading a new batch of documents (verify quality didn't drop)
- After changing the chunking strategy or `top_k` setting
- After changing the LLM model
- As part of a regular monthly quality review

---

## 6. Performance Testing

### Latency targets

| Operation | Target | Acceptable |
|---|---|---|
| Document upload (response) | < 500ms | < 2s |
| Indexing 10-page document | < 30s | < 60s |
| Query (first call, no cache) | < 5s | < 10s |
| Query (cache hit) | < 100ms | < 500ms |

### Measuring latency manually

```bash
# Time a query
time curl -s -X POST http://localhost:8000/api/query/ \
  -H "Content-Type: application/json" \
  -d '{"query": "What are the critical risks?", "top_k": 5}' > /dev/null
```

### Load testing with `locust` (optional)

```bash
pip install locust
# Create a simple locustfile.py (see below), then:
locust -f locustfile.py --host http://localhost:8000
```

Example `locustfile.py` for basic load testing:
```python
from locust import HttpUser, task, between

class QueryUser(HttpUser):
    wait_time = between(1, 3)

    @task
    def ask_question(self):
        self.client.post("/api/query/", json={
            "query": "What are the top supply chain risks?",
            "top_k": 5
        })
```

---

## 7. Common Issues and How to Diagnose Them

### "status: unhealthy" on /health

Qdrant is not running or not reachable.

```bash
# Check if Qdrant container is running
docker ps | grep qdrant

# Start it if not
docker run -d -p 6333:6333 qdrant/qdrant
```

### "No relevant documents found" on every query

No documents have been indexed yet, or the index collection doesn't exist.

```bash
# Check what's in the Qdrant collection
curl http://localhost:6333/collections/supply_chain_documents
```

### Upload returns 200 but job never reaches DONE

Check the API logs for errors:
```bash
# If running locally
uvicorn src.main:app --reload --log-level debug

# If running in Docker
docker logs <container_id> --follow
```

Common cause: invalid `OPENAI_API_KEY` (embedding step fails silently).

### Tests fail with "Connection refused"

Tests should NOT require a running Qdrant or API — they mock all external services. If tests fail with connection errors, run:

```bash
python -m pytest tests/ -v --tb=long 2>&1 | head -50
```

Look for import errors or missing mock patches.

### "ModuleNotFoundError: No module named 'src'"

You're running pytest from the wrong directory or without the venv:

```bash
cd /home/maks/dev/SupplyChain-RAG-Assistant
source .venv/bin/activate
python -m pytest tests/ -v
```

### Answer quality is poor (hallucinated or irrelevant)

1. Check `top_k` — try increasing to 6–8 for complex questions
2. Try enabling re-ranking (`ENABLE_RERANKING=true`)
3. Run RAGAS evaluation to get a numeric score
4. Check that the relevant document is actually uploaded (`GET /api/documents/list`)
5. Try rephrasing the question

---

## 8. Test Environments

### Local development

Use the defaults. No external services needed for unit tests (all mocked).
For integration tests, you need Qdrant running locally.

```bash
# .env for local dev (no real OpenAI key needed for unit tests)
OPENAI_API_KEY=test_key_not_real
QDRANT_HOST=localhost
QDRANT_PORT=6333
```

### CI/CD (GitHub Actions)

The automated tests in `tests/` do not require real Qdrant or OpenAI — they mock all external calls. You can run them in any CI environment:

```yaml
# .github/workflows/test.yml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: python -m pytest tests/ -v
```

### Staging / production validation

Before releasing to production, run the demo script against the staging environment:

```bash
python demo/run_demo.py --host https://your-staging-url.azurecontainerapps.io --api-key your_key
```

---

## 9. How to Write New Tests With AI Assistance

Use these prompts to generate new tests with an AI assistant:

### Generate a test for a new endpoint

> "Write a pytest test for the `DELETE /cache` endpoint in the SupplyChain RAG Assistant. The endpoint is in `src/api_health.py`. It should return `{"status": "cleared", "deleted": N}`. Follow the pattern in `tests/test_api.py` where `rag_pipeline` is mocked. The cache module is at `src/cache.py`."

### Generate edge case tests

> "Look at `tests/test_document_processor.py` in the SupplyChain RAG Assistant. Add tests for these edge cases:
> 1. Uploading a file with unicode characters in its name
> 2. An Excel file with multiple sheets
> 3. A CSV file with missing values in some columns
> Follow the same pattern as the existing tests using tmp_path."

### Generate load test scenarios

> "Write a Locust load test script for the SupplyChain RAG Assistant that simulates 3 types of users: (1) a document uploader who uploads one file per minute, (2) a frequent querier who asks questions every 5 seconds, (3) an occasional analyst who runs evaluations every 2 minutes. Target host: http://localhost:8000."

### Generate evaluation test data

> "Create a RAGAS evaluation dataset for the SupplyChain RAG Assistant using these 5 supply chain documents: demand_forecast_q1_2025.txt, supplier_directory.csv, inventory_policy.txt, risk_assessment.txt. Generate 10 question-ground_truth pairs that cover: demand forecasting, supplier selection, safety stock calculation, risk mitigation. Format as a JSON array with fields: question, ground_truth."

---

## 10. Release Checklist

Before deploying a new version, confirm every item:

### Code quality
- [ ] All automated tests pass: `python -m pytest tests/ -v`
- [ ] No obvious security issues (API keys not hardcoded, no SQL injection vectors)
- [ ] `.env.example` is up to date with all new settings

### Functional testing
- [ ] All items in the [Manual Testing Checklist](#2-manual-testing-checklist) checked
- [ ] Demo script runs successfully end-to-end: `python demo/run_demo.py`
- [ ] Streaming endpoint works: `curl -N ...`

### Quality gates
- [ ] At least one RAGAS evaluation run with scores above thresholds:
  - Faithfulness > 0.80
  - Answer Relevancy > 0.75
- [ ] Average query latency < 5 seconds on test dataset

### Deployment
- [ ] Docker build succeeds: `docker build -t supplychain-rag .`
- [ ] `docker-compose up` starts all services cleanly
- [ ] Health check passes after container startup
- [ ] Log level set to `INFO` (not `DEBUG`) for production
- [ ] `AUTH_ENABLED=true` with real API keys set for production

### Documentation
- [ ] README.md reflects any new features or configuration changes
- [ ] USER_GUIDE.md updated if workflows changed
- [ ] DESIGN_GUIDE.md updated if architecture changed
