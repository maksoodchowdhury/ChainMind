# SupplyChain RAG Assistant — Design Guide

> **Who is this guide for?** Anyone who wants to understand *how* the system works, whether to explain it to a stakeholder, extend it with AI assistance, or hand it off to a new team member. No deep programming knowledge is required to read and understand this guide.

---

## Table of Contents

1. [The Big Picture](#1-the-big-picture)
2. [The Journey of a Document](#2-the-journey-of-a-document)
3. [The Journey of a Question](#3-the-journey-of-a-question)
4. [Building Blocks — What Each Part Does](#4-building-blocks--what-each-part-does)
5. [Technology Choices — Why We Picked What We Picked](#5-technology-choices--why-we-picked-what-we-picked)
6. [Data Flow Diagram](#6-data-flow-diagram)
7. [Configuration — The Control Panel](#7-configuration--the-control-panel)
8. [Optional Features — Turn On When Ready](#8-optional-features--turn-on-when-ready)
9. [Deployment Architecture](#9-deployment-architecture)
10. [How to Extend the System](#10-how-to-extend-the-system)

---

## 1. The Big Picture

Imagine a very thorough research assistant. You hand them every supply chain document in your organisation. They read everything, organise it by topic, and stand by to answer questions. When you ask a question, they quickly find the relevant passages and give you a clear, cited answer.

That is exactly what this system does — automatically.

The three core steps are always the same:

```
1. INGEST  →  2. RETRIEVE  →  3. GENERATE
   (read &         (find the         (write the
   index docs)    right chunks)      answer)
```

This pattern is called **RAG**: **R**etrieval-**A**ugmented **G**eneration. The "augmented" part means the AI is not guessing — it has real retrieved evidence before it writes anything.

---

## 2. The Journey of a Document

Here is what happens step-by-step when you upload a file:

### Step 1 — Upload

You upload a file (PDF, CSV, TXT, Excel, Markdown) through the API. The system immediately responds with a `job_id` and starts processing the file in the background so you don't have to wait.

### Step 2 — Fingerprinting (deduplication)

The system calculates a **SHA-256 fingerprint** (a unique mathematical signature) of the file's content. If the exact same file has been uploaded before, it skips re-processing it. This prevents the index from filling up with duplicates.

> **Analogy:** Like checking a book's ISBN before adding it to a library catalogue. If it's already there, you don't add a second copy.

### Step 3 — Parsing (reading the file)

Different file types need different readers:
- **Text / Markdown / PDF** → read directly
- **CSV** → each group of 20 rows becomes one text block ("Key: Value" format)
- **Excel** → each worksheet is processed as a separate text block

The content is combined with **metadata** (supplier, doc_type, date_period) that you provided at upload time.

### Step 4 — Chunking (splitting into searchable pieces)

The system splits each document into smaller overlapping pieces called **chunks**. Why? Because a 50-page document as a single unit is too big and unfocused to search accurately. A chunk of 2–3 paragraphs is precise enough to answer a specific question.

The default strategy is **sentence-aware splitting**: chunks always end at sentence boundaries, so no sentence is cut in half.

Three strategies are available:
- **Sentence** (default) — respects sentence boundaries, fast, works for all docs
- **Fixed** — splits at exactly N characters, simple and predictable
- **Semantic** — groups sentences by meaning (requires an embedding model call, slower but more precise for complex documents)

### Step 5 — Embedding (converting text to numbers)

Each chunk is converted into a list of numbers called an **embedding vector** (1536 numbers for OpenAI's model). These numbers capture the *meaning* of the text, not just the words. Two chunks that mean similar things will have similar numbers.

> **Analogy:** Like plotting every chunk on a map where the distance between two points represents how similar their meanings are.

### Step 6 — Storing in Qdrant

The embeddings (and the original text + metadata) are stored in **Qdrant**, a high-performance vector database. Qdrant is optimised for finding the nearest neighbours in this high-dimensional space at millisecond speed.

### Step 7 — Job completion

The background job is marked as **DONE** and the fingerprint is saved to prevent future re-indexing.

---

## 3. The Journey of a Question

When you ask a question, here is what happens:

### Step 1 — Cache check (optional)

If Redis caching is enabled, the system first checks whether this exact question (with the same filters and top_k setting) was asked before. If yes, it returns the cached answer instantly — no LLM call needed.

### Step 2 — Embedding the question

Your question is converted into an embedding vector using the same model used for documents. This ensures questions and documents live in the same "meaning space".

### Step 3 — Vector retrieval

The question vector is compared against all stored document vectors. Qdrant returns the **top-K most similar chunks** (default: 5). If metadata filters were specified (e.g., `doc_type=demand_plan`), only chunks from matching documents are considered.

### Step 4 — Optional: Hybrid search

If hybrid search is enabled, the system also runs a **BM25 keyword search** (like traditional Google search) and fuses the two result sets. This catches documents that are highly relevant by exact keyword match but perhaps not as high in the vector similarity ranking.

### Step 5 — Optional: Re-ranking

A **cross-encoder model** re-reads each retrieved chunk alongside your question and re-scores them with higher precision. The top-N chunks after re-ranking are passed to the LLM.

> **Analogy:** First a librarian quickly finds the most likely books (vector search). Then they actually skim each book to confirm which ones are truly most relevant (re-ranking).

### Step 6 — Answer generation

The top chunks are assembled into a **prompt** and sent to the LLM (GPT-4 by default). The LLM has been instructed to:
- Answer based only on the provided context
- Cite which documents it used
- Say "I don't know" if the context doesn't contain enough information

### Step 7 — Response

The answer (and source citations) are returned to you. If streaming is enabled, the words appear progressively as the LLM generates them.

---

## 4. Building Blocks — What Each Part Does

```
project/
├── src/
│   ├── main.py              ← App entry point: wires everything together
│   ├── config.py            ← All settings (env vars with defaults)
│   ├── rag_pipeline.py      ← Core RAG logic: ingest + query
│   ├── document_processor.py ← File loading, chunking, fingerprinting
│   ├── ingestion_worker.py  ← Background job runner + status tracking
│   ├── reranker.py          ← Cross-encoder re-ranking
│   ├── cache.py             ← Redis query result caching
│   ├── auth.py              ← API key authentication middleware
│   ├── tracer.py            ← OpenTelemetry distributed tracing
│   ├── evaluator.py         ← RAGAS quality evaluation
│   ├── api_health.py        ← GET /health, DELETE /cache
│   ├── api_documents.py     ← POST /upload, GET /status, GET /list
│   ├── api_query.py         ← POST /query, POST /query/stream
│   └── api_eval.py          ← POST /evaluate, POST /query-and-eval
├── tests/                   ← Automated tests (pytest)
├── demo/                    ← Demo data + interactive demo runner
├── docs/                    ← This documentation
├── data/                    ← Uploaded files + fingerprints store
├── docker-compose.yml       ← Docker setup (API + Qdrant)
└── requirements.txt         ← Python dependencies
```

### The core loop in `rag_pipeline.py`

This is the heart of the system. Two key methods:

- **`load_documents(paths)`** — reads files, chunks them, stores embeddings in Qdrant
- **`query(text, top_k, filters)`** — embeds the question, retrieves chunks, calls LLM, returns answer

### Background jobs in `ingestion_worker.py`

Uploading and indexing a large file can take 10–60 seconds. Doing this synchronously would make the API feel unresponsive. Instead:
1. Upload returns immediately with a `job_id`
2. Processing runs in the background
3. You poll `/api/documents/status/{job_id}` to see when it finishes

---

## 5. Technology Choices — Why We Picked What We Picked

| Technology | What it does | Why this choice |
|---|---|---|
| **Python** | Programming language | Dominant in AI/ML; huge ecosystem |
| **FastAPI** | Web framework | Async-native, automatic API docs, blazing fast |
| **LlamaIndex** | RAG orchestration | Handles chunking, indexing, retrieval, and LLM calls with a clean API |
| **Qdrant** | Vector database | Open-source, self-hostable, production-grade, fast |
| **OpenAI GPT-4** | Answer generation | Best-in-class accuracy; easy API |
| **OpenAI text-embedding-3-small** | Embeddings | Cost-effective, 1536 dimensions, strong semantic understanding |
| **Docker** | Containerisation | Consistent environment; Qdrant runs as a container |
| **Redis** (optional) | Caching | Sub-millisecond repeated query responses |
| **sentence-transformers** (optional) | Re-ranking | Local model, no API cost; cross-encoder is more precise than vector similarity |
| **RAGAS** (optional) | Evaluation | Industry-standard metrics for RAG quality assessment |
| **OpenTelemetry** (optional) | Tracing | Vendor-neutral distributed tracing; works with Jaeger, Azure Monitor, Datadog |

---

## 6. Data Flow Diagram

```
USER
 │
 │  POST /api/documents/upload
 ▼
[FastAPI API] ──── Auth middleware ──── (reject if invalid key)
 │
 │  Create job, return job_id
 ▼
[ingestion_worker] (background)
 │
 ├── document_processor.file_hash()     ← Already indexed? → SKIP
 ├── document_processor.load_file()     ← Parse TXT/PDF/CSV/Excel
 ├── document_processor.apply_chunking()← Split into chunks
 ├── rag_pipeline._create_or_update_index()
 │       └── OpenAI Embeddings API ─────→ 1536-dim vectors per chunk
 │       └── Qdrant.upsert()            ← Store vectors + metadata
 └── register_indexed()                 ← Save fingerprint


USER
 │
 │  POST /api/query/
 ▼
[FastAPI API] ──── Auth ──── Cache check (Redis) ──── return cached if hit
 │
 │  cache miss
 ▼
[rag_pipeline.query()]
 ├── OpenAI Embeddings API              ← Embed the question
 ├── Qdrant.search(vector, filters)     ← Top-K similar chunks
 ├── (optional) BM25 keyword search ────┤
 │                                      └── QueryFusionRetriever merge
 ├── (optional) CrossEncoder re-rank    ← Re-score, keep top-N
 ├── OpenAI GPT-4 API                   ← Generate answer from chunks
 └── return {answer, sources}
         │
         └── cache.set() (Redis)        ← Cache for future requests
```

---

## 7. Configuration — The Control Panel

All settings live in a single place: the `.env` file (copy from `.env.example`).

| Setting | Default | What it controls |
|---|---|---|
| `OPENAI_API_KEY` | *(required)* | Your OpenAI account key |
| `OPENAI_MODEL` | `gpt-4-turbo-preview` | Which LLM to use for answers |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Which OpenAI embedding model to use |
| `QDRANT_HOST` | `qdrant` | Where Qdrant is running |
| `COLLECTION_NAME` | `supply_chain_documents` | The Qdrant "table" name |
| `CHUNK_SIZE` | `1024` | Max characters per chunk |
| `CHUNK_OVERLAP` | `256` | Characters shared between adjacent chunks |
| `CHUNKING_STRATEGY` | `sentence` | `sentence` \| `semantic` \| `fixed` |
| `TOP_K_RETRIEVED` | `5` | Default chunks retrieved per query |
| `ENABLE_HYBRID_SEARCH` | `false` | BM25 + vector fusion (requires extra install) |
| `ENABLE_RERANKING` | `false` | Cross-encoder re-ranking (requires extra install) |
| `REDIS_URL` | *(empty)* | Redis connection string for caching |
| `CACHE_TTL_SECONDS` | `3600` | How long to cache query results (1 hour) |
| `AUTH_ENABLED` | `false` | Require `X-API-Key` header on all requests |
| `API_KEYS` | *(empty)* | Comma-separated list of valid API keys |
| `ENABLE_TRACING` | `false` | OpenTelemetry tracing export |
| `OTLP_ENDPOINT` | `http://localhost:4317` | Where to send traces |

---

## 8. Optional Features — Turn On When Ready

The system is designed with **graceful degradation**: optional features are disabled by default and only activate if you both install the required package *and* set the config flag. This means the core system works even without Redis, re-ranking, or tracing.

### Hybrid Search (BM25 + Vector)

Improves recall for queries that use exact keywords (e.g., specific supplier codes like "SUP-003").

```bash
pip install llama-index-retrievers-bm25 rank-bm25
```
Set `ENABLE_HYBRID_SEARCH=true` in `.env`.

### Cross-Encoder Re-ranking

Improves precision by re-scoring retrieved chunks with a local neural model.

```bash
pip install sentence-transformers
```
Set `ENABLE_RERANKING=true` in `.env`.

### Redis Caching

Dramatically speeds up repeated identical queries (e.g., dashboard refreshes).

```bash
pip install redis
docker run -p 6379:6379 redis:alpine
```
Set `REDIS_URL=redis://localhost:6379` in `.env`.

### RAGAS Evaluation

Measures answer quality with industry-standard metrics (faithfulness, relevancy, precision, recall).

```bash
pip install "ragas>=0.1.0,<0.2.0" datasets
```
Use `POST /api/eval/` or `POST /api/eval/query-and-eval` endpoints.

### OpenTelemetry Tracing

Sends timing and span data to Jaeger, Zipkin, Azure Monitor, or any OTLP-compatible backend.

```bash
pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc
```
Set `ENABLE_TRACING=true` and `OTLP_ENDPOINT=http://your-collector:4317` in `.env`.

---

## 9. Deployment Architecture

### Local development (default)

```
Your machine:
  uvicorn src.main:app  (port 8000)
  docker run qdrant/qdrant  (port 6333)
  [optionally] docker run redis  (port 6379)
```

### Docker Compose (recommended for teams)

```bash
docker-compose up
```

Starts API + Qdrant together. The `docker-compose.yml` mounts `./data` for persistence.

### Production (Cloud — Azure Container Apps example)

```
Internet → Azure API Management → Container App (FastAPI)
                                      ↕
                               Azure Container Registry
                                      ↕
                               Qdrant (Container App or AKS)
                                      ↕
                               Azure Cache for Redis
```

See the [Azure deployment guide](../README.md#deployment) or ask GitHub Copilot:

> "Generate an Azure Bicep template to deploy this FastAPI app as an Azure Container App, with Qdrant as a separate Container App and Redis as Azure Cache for Redis."

---

## 10. How to Extend the System

The codebase is structured so that each feature lives in its own file. Here are the most common extension patterns with AI-ready prompts:

### Add a new API endpoint

> "I want to add `GET /api/documents/{document_id}` to retrieve metadata for a single indexed document from Qdrant. The project uses FastAPI and the existing document endpoints are in `src/api_documents.py`. The Qdrant client is accessed via `rag_pipeline.vector_store`. Show me how to add this endpoint."

### Add a new document format

> "The SupplyChain RAG Assistant currently handles TXT, PDF, CSV, and Excel files. I need to add support for DOCX (Microsoft Word) files. The file loading logic is in `src/document_processor.py` in the `load_file_as_documents()` function. Show me how to add DOCX support using the `python-docx` library."

### Replace OpenAI with a local LLM

> "I want to run the SupplyChain RAG Assistant without sending data to OpenAI. Replace the OpenAI LLM and embedding model with a local Ollama server running `llama3.2` for LLM and `nomic-embed-text` for embeddings. The current config is in `src/config.py` and the LLM/embedding setup is in `src/rag_pipeline.py`."

### Add user-based access control

> "Each API user should only be able to search documents they uploaded. The system currently supports API key auth via `src/auth.py`. Extend it so each API key is associated with an `owner_id` in a simple JSON config file, and add `owner_id` to document metadata at upload time (in `src/api_documents.py`). Queries should automatically filter by the calling user's `owner_id`."

### Add a webhook on indexing completion

> "When a document finishes indexing (status = DONE) in `src/ingestion_worker.py`, send an HTTP POST to a configurable webhook URL with the job details. Add `WEBHOOK_URL` to the settings in `src/config.py` and implement the webhook call."
