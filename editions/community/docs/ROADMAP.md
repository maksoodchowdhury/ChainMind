# SupplyChain RAG Assistant — Future Release Roadmap

**Last updated:** 2026-05-12  
**Current baseline:** Phase 1-5 (complete — see PHASE_COMPLIANCE.md)  
**Horizon:** Phase 6 — Contextual Intelligence & Real-Time Knowledge Fabric

---

## Strategic Context

Phases 1-5 established a production-grade RAG platform: event-driven ingestion,
semantic retrieval, multi-tenant isolation, autonomous optimisation loops, and
enterprise deployment controls.

Three structural gaps limit real-world supply-chain value:

| Gap | Symptom | Phase 6 Pillar |
|-----|---------|----------------|
| Stateless query sessions | "Compare that to Q3" fails | Pillar 1 — Conversational Memory |
| Unstructured-only KB | PO numbers and lead-time filters unanswerable | Pillar 2 — Structured Data Ingestion |
| Reactive-only posture | Risk discovered only when asked | Pillar 3 — Proactive Risk Monitor |
| Flat entity model | Tier-2 supplier relationships invisible | Pillar 4 — Supplier Knowledge Graph |

---

## Phase 6 — Pillars

---

### Pillar 1 — Conversational Memory & Session Context

**Goal:** Enable multi-turn dialogue so users can ask follow-up questions within
a coherent context window.

#### Architecture

- `ConversationSession` entity keyed on `(tenant_id, session_id)`, stored in
  Redis with configurable TTL.
- Each turn appended as `{role, content, retrieved_chunks[]}`. Chunks are
  retained per-turn so the reranker can de-duplicate across turns and avoid
  re-surfacing already-cited evidence.
- **Sliding-window compression:** when cumulative token budget exceeds a
  configurable threshold, older turns are summarised by a small model (e.g.
  gpt-4o-mini) and collapsed into a single `system` summary turn.
- **New endpoint:** `POST /api/query/session` — accepts `session_id`; the
  existing `POST /api/query` remains stateless for backward compatibility.
- **UI:** Session sidebar showing conversation history; `New Session` button;
  session state persisted in `localStorage` for fast page-reload recovery.

#### New Modules
- `src/session_store.py` — Redis-backed session CRUD with TTL management
- `src/session_compressor.py` — sliding-window summarisation strategy
- `src/api_session.py` — `/api/query/session` route family

#### Key Risk & Mitigation
- **Risk:** Context stuffing inflating LLM costs.
- **Mitigation:** Hard token cap enforced before every LLM call; chunk
  de-duplication across turns reduces repetition; session TTL evicts idle
  sessions automatically.

#### New Infrastructure
- Redis (single new dependency; added to `docker-compose.yml` alongside Qdrant)

---

### Pillar 2 — Structured Data Ingestion & Hybrid Search

**Goal:** Allow procurement teams to upload CSV, XLSX, and JSON exports (POs,
invoices, lead-time tables) and query them with natural-language filters.

#### Architecture

- **`StructuredIngestion` pipeline:** CSV/XLSX/JSON → typed schema inference →
  row-level embedding of a concatenated field string, with structured column
  values stored as Qdrant payload fields for filter-based retrieval.
- **Hybrid retrieval — BM25 + dense fusion:** sparse BM25 on field values (exact
  match for PO numbers, supplier codes, product SKUs) fused with dense semantic
  search via Reciprocal Rank Fusion (RRF).
- **`StructuredQueryParser`:** a dedicated LLM call that decomposes a
  natural-language question into `(semantic_part, filter_clauses)`, e.g.
  `lead_time > 60 AND status = "OPEN"`. Qdrant payload filtering executes the
  structured predicates; semantic search handles intent.
- New document type `STRUCTURED_TABLE` in the document catalog, with
  column-schema metadata stored alongside the document record.

#### New Modules
- `src/structured_ingestor.py` — schema inference, row embedding, payload
  builder
- `src/hybrid_retriever.py` — BM25 index management + RRF fusion
- `src/structured_query_parser.py` — LLM-based filter clause extractor

#### Key Risk & Mitigation
- **Risk:** Schema drift as ERP exports change across versions.
- **Mitigation:** Schema version pinned at ingest time; uploads with an
  incompatible schema diff trigger a deprecation warning and require an explicit
  `force=true` override.

---

### Pillar 3 — Proactive Risk Monitor (Scheduled Intelligence)

**Goal:** Let users define standing queries that execute on a schedule and fire
alerts when the answer meets a risk condition — turning the system from reactive
to proactive.

#### Architecture

- **`MonitorSpec`** YAML-defined:
  ```yaml
  name: "Open PO lead-time breach"
  query_template: "Which open purchase orders have a lead time exceeding {threshold} days?"
  schedule: "0 8 * * 1-5"        # weekdays at 08:00
  condition:
    type: llm_judge               # or: threshold, regex
    prompt: "Does this answer indicate a supply disruption risk?"
  cooldown_hours: 24
  severity: high                  # gates which alert channel fires
  recipients: ["#supply-risk-slack"]
  ```
- **Scheduler:** APScheduler (in-process) with an upgrade path to Celery Beat
  for high-volume deployments.
- **`LLMJudge`:** yes/no + confidence evaluation of the generated answer against
  the condition; below a confidence threshold the alert is suppressed and logged
  as `UNCERTAIN`.
- On condition met: fires through the existing webhook / alert pipeline →
  Slack, Teams, and email adapters via the integration fabric connector model.
- **UI:** "Monitors" tab within the Review section — create, edit, disable
  monitors; last-run timestamp with answer preview and condition result.

#### New Modules
- `src/monitor_engine.py` — `MonitorSpec` parser, scheduler registration, run
  executor
- `src/llm_judge.py` — condition evaluator (LLM-judge, threshold, regex
  strategies)
- `src/api_monitors.py` — `POST /api/monitors`, `GET /api/monitors`,
  `GET /api/monitors/{id}/runs`, `DELETE /api/monitors/{id}`

#### Key Risk & Mitigation
- **Risk:** Alert fatigue from over-firing monitors.
- **Mitigation:** Mandatory cooldown period per monitor; deduplication window
  suppresses identical consecutive alerts; `severity` field gates channel
  selection so low-severity monitors only log internally.

---

### Pillar 4 — Supplier Knowledge Graph

**Goal:** Answer relationship-aware questions ("Which tier-2 suppliers share a
dependency on this port?") that vector search cannot resolve alone.

#### Architecture

- **Lightweight embedded graph** using `networkx` initially; upgrade path to
  Neo4j via the existing integration fabric connector abstraction (non-breaking
  swap).
- **Node types:** Supplier, Product, Component, Contract, Facility,
  Port/Region.
- **Edge types:** SUPPLIES, SOURCES_FROM, COVERED_BY, LOCATED_IN — each with a
  `confidence` score.
- **`GraphIngestion` worker:** parses relationship fields from structured ingest
  (Pillar 2) or explicit relationship documents; low-confidence edges
  (confidence < 0.6) excluded from LLM context unless the user explicitly
  requests them.
- **Hybrid retrieval extension:** Qdrant semantic search identifies seed entities
  → graph traversal expands to related nodes → combined context passed to LLM.
- **New reasoning pack** `GRAPH_TRAVERSAL` registered in the existing
  `ReasoningPackRegistry` (zero changes to registry infrastructure).
- **UI:** Optional "Show supply chain map" toggle in query results — renders a
  small D3.js force graph of the entities cited in the answer.

#### New Modules
- `src/knowledge_graph.py` — graph model, node/edge CRUD, persistence
- `src/graph_ingestor.py` — relationship extraction from structured + document
  ingest
- `src/graph_retriever.py` — seed-entity lookup + multi-hop traversal
- `src/reasoning_graph_pack.py` — `GRAPH_TRAVERSAL` reasoning pack

#### Key Risk & Mitigation
- **Risk:** Graph quality degrades when source documents are inconsistent.
- **Mitigation:** Confidence score on every edge; graph validation step after
  each bulk ingest run; low-confidence subgraphs quarantined until reviewed via
  the HITL queue.

---

## Delivery Sequence

| Sprint | Deliverable | Value Gate |
|--------|-------------|------------|
| 1 | Pillar 1: Redis session store + `/query/session` endpoint + UI sidebar | Follow-up queries resolve correctly end-to-end |
| 2 | Pillar 2: Structured ingestion pipeline + schema inference | CSV/XLSX files appear in knowledge base |
| 3 | Pillar 2: Hybrid BM25 + dense retrieval + structured query parser | Filtered queries (PO number, lead time) return correct rows |
| 4 | Pillar 3: Monitor engine + APScheduler + LLM judge | First scheduled alert fires to Slack |
| 5 | Pillar 3: Monitor management UI + Slack/Teams adapters | Non-technical users can configure monitors without code |
| 6 | Pillar 4: Graph ingestion + `GRAPH_TRAVERSAL` reasoning pack | Relationship-aware queries cite multi-hop paths |
| 7 | Pillar 4: D3.js supply-chain map in query results | Entity relationships visible in UI |
| 8 | Hardening: integration tests, load tests, updated runbooks | All Phase 6 tests green in CI |

---

## Deliberately Deferred

| Item | Rationale |
|------|-----------|
| Fine-tuned domain embeddings | Only justified after accumulating 10k+ domain-specific query/retrieval pairs from the eval harness |
| Native mobile app | Slack/Teams integration (Pillar 3) covers the mobile surface at a fraction of the cost |
| Full Neo4j migration | `networkx` is sufficient up to ~100k nodes; the connector abstraction makes migration non-breaking when needed |
| Multi-modal ingestion (images, diagrams) | Valuable for technical specs but requires vision model integration — separate workstream |
| Real-time streaming ingestion (Kafka) | Current event-driven queue is sufficient; Kafka warranted only at 10k+ documents/day volume |

---

## Scope Estimate

| Category | Count |
|----------|-------|
| New source modules | ~12 |
| New API route files | ~4 |
| New tests | ~35 |
| Breaking changes to Phase 1-5 APIs | 0 |
| New infrastructure dependencies | 1 (Redis) |

All existing `/api/query`, `/api/ingest`, `/api/documents`, `/api/health`, and
platform endpoints remain fully backward-compatible. Phase 6 features are
additive.
