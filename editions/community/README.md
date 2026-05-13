# ChainMind Community (Open Source)

A containerized open-source RAG (Retrieval-Augmented Generation) assistant for supply-chain decision support using Python, FastAPI, vector search, and LLMs.

This edition includes the full core workflow (ingestion, query, citations, evaluation, UI) and intentionally excludes enterprise-only control-plane APIs.

## Features

- **Document Management**: Upload and manage supply chain documents (PDFs, text, CSV)
- **Vector Search**: Efficient semantic search using Qdrant vector database
- **LLM Integration**: GPT-4 powered responses with citations
- **REST API**: FastAPI endpoints for all operations
- **Built-in UI**: Attractive browser UI for uploads, querying, streaming, and source inspection
- **Containerized**: Docker and docker-compose for easy deployment
- **Production Hardening**: SLO checks, liveness/readiness gates, backpressure, retries, and circuit breaker
- **Security & Governance**: API auth, RBAC, tenant-aware controls, audit trail, lifecycle catalog, retention
- **Intelligence Layer**: Reasoning packs, what-if scenarios, agentic workflows, HITL queue
- **Open-Core Scope**: local/self-host deployment with core decision intelligence

## Community vs Paid Boundary

Community edition includes:
- `/api/documents/*`, `/api/query/*`, `/api/eval/*`, `/api/intelligence/*`
- Built-in UI at `/ui`

Community edition excludes:
- `/api/platform/*` enterprise control plane
- `/api/autonomy/*` autonomous optimization and action endpoints

## Open Source Governance

- License: `Apache-2.0` (see `LICENSE`)
- Contribution guide: `CONTRIBUTING.md`
- Code of conduct: `CODE_OF_CONDUCT.md`
- Security policy: `SECURITY.md`

## Project Structure

This community edition shares core code from the repository root:

```
editions/community/                    # Community edition (OSS release configuration)
├── .env.example                       # Community defaults
├── .github/workflows/                 # Community CI pipelines
├── CONTRIBUTING.md                    # Contribution guidelines
├── CODE_OF_CONDUCT.md                 # Community code of conduct
├── LICENSE                            # Apache-2.0 license
└── README.md                          # This file

../../                                 # Shared root-level code (single source of truth)
├── src/                               # FastAPI application
├── tests/                             # Unit and integration tests
├── data/                              # Sample documents and catalog
├── demo/                              # Demo scripts
├── requirements.txt                   # Python dependencies
├── docker-compose.yml                 # Docker compose configuration
└── Dockerfile                         # Container image
```

**Why this structure?** The community and paid editions share identical core logic to avoid divergence and maintenance burden. Community-specific files (governance, CI, license) live in this folder; executable code lives at the root.

## Prerequisites

- Python 3.11+
- Docker & Docker Compose (optional, for containerized deployment)
- OpenAI API key

> Note: GitHub Actions community CI is temporarily pinned to Python 3.11 because the current `llama-index` / `pydantic` dependency set is not compatible with Python 3.12 in the CI environment.

## Quick Start

> **Important:** This community edition directory contains configuration and governance files. Code is sourced from the repository root. Navigate to the root folder to run the application.

### Local Development

1. **Navigate to root and setup environment**:
   ```bash
   # From editions/community, go to the project root
   cd ../..
   cp .env.example .env
   # Edit .env and add your OpenAI API key
   ```

2. **Create virtual environment**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Start Qdrant locally** (if not using Docker):
   ```bash
   docker run -p 6333:6333 qdrant/qdrant:v1.7.0
   ```

5. **Run the API**:
   ```bash
   python -m uvicorn src.main:app --reload
   ```

   The API will be available at `http://localhost:8000`

### Docker Deployment

1. **Navigate to root and setup environment**:
   ```bash
   cd ../..
   cp .env.example .env
   # Edit .env with your OpenAI API key
   ```

2. **Start services**:
   ```bash
   docker-compose up --build
   ```

   Services:
   - API: http://localhost:8000
   - Qdrant: http://localhost:6333

## API Endpoints

### Health Check
```bash
GET /health
```

### Document Management
```bash
# Upload document
POST /api/documents/upload
Content-Type: multipart/form-data
Body: file=<file>

# List documents
GET /api/documents/list
```

### Query
```bash
POST /api/query/
Content-Type: application/json
Body: {
  "query": "What is our demand forecast for Q3?",
  "top_k": 5
}
```

### Intelligence
```bash
GET  /api/intelligence/packs
GET  /api/intelligence/scenarios
POST /api/intelligence/scenarios/run
GET  /api/intelligence/workflows
POST /api/intelligence/workflows/run
GET  /api/intelligence/hitl
POST /api/intelligence/hitl/submit
```

### Platform & Autonomy
```bash
GET  /api/platform/tenants
PUT  /api/platform/tenants/{tenant_id}/quota
GET  /api/platform/billing/chargeback
GET  /api/platform/connectors
POST /api/platform/events/webhook
POST /api/platform/cdc/jobs
GET  /api/platform/extensions
POST /api/platform/extensions
POST /api/autonomy/monitor/run
POST /api/autonomy/actions/propose
POST /api/autonomy/actions/execute
POST /api/autonomy/optimizer/recommend
```

### Interactive Documentation
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- App UI: http://localhost:8000/ui

## Configuration

Environment variables (see `.env.example`):

- `OPENAI_API_KEY`: Your OpenAI API key (required)
- `QDRANT_HOST`: Qdrant server host (default: localhost)
- `QDRANT_PORT`: Qdrant server port (default: 6333)
- `COLLECTION_NAME`: Qdrant collection name (default: supply_chain_documents)
- `LOG_LEVEL`: Logging level (default: INFO)
- `AUTH_ENABLED`, `API_KEYS`: API key authentication controls
- `AUTHZ_ENABLED`, `REQUIRE_TENANT_HEADER`: RBAC and tenant header enforcement
- `INGESTION_QUEUE_ENABLED`, `INGESTION_POISON_MAX_ATTEMPTS`: event-driven ingestion controls
- `TENANT_QUOTA_ENABLED`: tenant-level request quota guardrails
- `SECRET_PROVIDER`: env, file, vault, azure-keyvault
- `ENCRYPT_DATA_AT_REST`, `DATA_ENCRYPTION_KEY`: optional encrypted local operational stores

## Testing

Run all tests:
```bash
pytest
```

Current baseline:
- 161 passed, 3 skipped

Run with coverage:
```bash
pytest --cov=src
```

Run specific test file:
```bash
pytest tests/test_api.py -v
```

## Development

### Project Structure Pattern

- **config.py**: All configuration via Pydantic BaseSettings
- **rag_pipeline.py**: RAG logic (separate from API)
- **api_*.py**: Modular API routers
- **main.py**: FastAPI app assembly with lifespan management

### Adding New Features

1. Create documents/chunks
2. Add to vector store in Qdrant
3. Query and retrieve with context
4. Generate response with LLM

## Documentation Map

- `docs/PHASE_COMPLIANCE.md`: phase-by-phase implementation verification
- `docs/RUNBOOK.md`: deployment and rollback operations
- `docs/INCIDENT_RESPONSE_PLAYBOOK.md`: incident response process
- `docs/DR_RTO_RPO.md`: recovery objectives and DR guidance
- `docs/USER_GUIDE.md`: end-user workflows and usage instructions
- `docs/QA_GUIDE.md`: manual/automated validation guidance

## Troubleshooting

**"Connection refused" to Qdrant**:
- Ensure Qdrant is running: `docker ps | grep qdrant`
- Check connection URL in `.env`

**"API key not found"**:
- Verify `OPENAI_API_KEY` is set in `.env`
- Restart the application

**Documents not loaded**:
- Check upload directory exists: `ls -la data/uploads/`
- Review logs for parsing errors

## License

Apache-2.0

## References

- [LlamaIndex Docs](https://docs.llamaindex.ai/)
- [Qdrant Docs](https://qdrant.tech/documentation/)
- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [OpenAI API](https://platform.openai.com/docs)
