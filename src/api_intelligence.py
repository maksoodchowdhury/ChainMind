"""
Phase 3 Intelligence Layer API.

Endpoints
---------
Reasoning packs
  GET  /api/intelligence/packs               → list all domain packs
  POST /api/intelligence/packs/{pack}/query  → domain-focused RAG query

Scenario analysis
  GET  /api/intelligence/scenarios           → list scenario templates
  POST /api/intelligence/scenarios/run       → run a what-if scenario

Agentic workflows
  GET  /api/intelligence/workflows           → list workflow templates
  POST /api/intelligence/workflows/run       → start a multi-step workflow
  GET  /api/intelligence/workflows/{run_id}  → get a completed run
  GET  /api/intelligence/workflows           → (+ ?workflow= filter) list runs

Human-in-the-loop
  POST /api/intelligence/hitl/submit         → submit item for review
  GET  /api/intelligence/hitl                → list review queue (+ ?status= filter)
  GET  /api/intelligence/hitl/stats          → queue stats
  GET  /api/intelligence/hitl/{review_id}    → get single review
  POST /api/intelligence/hitl/{review_id}/decide   → approve/reject/needs_revision
  POST /api/intelligence/hitl/{review_id}/resubmit → resubmit after revision
  POST /api/intelligence/hitl/{review_id}/feedback → append free-form feedback
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.reasoning_packs import get_pack, list_packs
from src.scenario_engine import ScenarioEngine, ScenarioRequest
from src.agent_runner import AgentRunner, WorkflowRequest
from src.hitl import HITLQueue, ReviewRequest, ReviewDecision

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/intelligence", tags=["intelligence"])

# Singletons created on first use (avoids import-time circular dependency)
_scenario_engine: Optional[ScenarioEngine] = None
_agent_runner: Optional[AgentRunner] = None
_hitl_queue: Optional[HITLQueue] = None


def _get_scenario_engine() -> ScenarioEngine:
    global _scenario_engine
    if _scenario_engine is None:
        from src.main import rag_pipeline, settings
        _scenario_engine = ScenarioEngine(rag_pipeline, settings)
    return _scenario_engine


def _get_agent_runner() -> AgentRunner:
    global _agent_runner
    if _agent_runner is None:
        from src.main import rag_pipeline, settings
        _agent_runner = AgentRunner(rag_pipeline, settings)
    return _agent_runner


def _get_hitl_queue() -> HITLQueue:
    global _hitl_queue
    if _hitl_queue is None:
        _hitl_queue = HITLQueue()
    return _hitl_queue


# ── Request / Response models ─────────────────────────────────────────────────

class PackQueryRequest(BaseModel):
    query: str
    top_k: int = 6
    filters: dict[str, str] = {}
    rerank_strategy: str = "default"


class ScenarioRunRequest(BaseModel):
    scenario_type: str
    variables: dict[str, Any]
    filters: dict[str, str] = {}
    top_k: int = 8
    rerank_strategy: str = "default"


class WorkflowRunRequest(BaseModel):
    workflow: str
    context: dict[str, Any]
    filters: dict[str, str] = {}
    top_k: int = 6
    rerank_strategy: str = "default"


class HITLSubmitRequest(BaseModel):
    source_type: str
    source_id: str
    title: str
    content: str
    submitted_by: str
    priority: str = "normal"
    tags: list[str] = []
    metadata: dict = {}


class HITLDecideRequest(BaseModel):
    decision: str
    reviewer: str
    comment: str = ""
    correction: Optional[str] = None


class HITLResubmitRequest(BaseModel):
    revised_content: str
    submitted_by: str


class HITLFeedbackRequest(BaseModel):
    feedback: str
    by: str


# ── Reasoning packs ───────────────────────────────────────────────────────────

@router.get("/packs")
async def list_reasoning_packs() -> dict:
    """List all available domain reasoning packs."""
    return {"packs": list_packs(), "count": len(list_packs())}


@router.post("/packs/{pack_name}/query")
async def query_with_pack(pack_name: str, request: PackQueryRequest) -> dict:
    """Run a domain-focused RAG query using a reasoning pack's system prompt.

    The pack's structured output schema is injected into the prompt so the LLM
    returns domain-specific JSON rather than free-form text.

    Available packs: **risk**, **inventory**, **supplier**, **lead_time**
    """
    try:
        pack = get_pack(pack_name)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))

    from src.main import rag_pipeline

    augmented_query = (
        f"[DOMAIN: {pack.name.upper()}]\n"
        f"System instructions: {pack.system_prompt}\n\n"
        f"{request.query}\n\n"
        f"Return JSON matching this schema: {pack.output_schema}"
    )

    try:
        result = rag_pipeline.query(
            query_text=augmented_query,
            top_k=request.top_k,
            filters=request.filters or None,
            rerank_strategy=request.rerank_strategy,
        )
    except Exception as e:
        logger.error(f"Pack query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "pack": pack_name,
        "query": request.query,
        "answer": result["answer"],
        "sources": result["sources"],
        "output_schema": pack.output_schema,
    }


# ── Scenario analysis ─────────────────────────────────────────────────────────

@router.get("/scenarios")
async def list_scenarios() -> dict:
    """List all available what-if scenario templates."""
    engine = _get_scenario_engine()
    scenarios = engine.list_scenarios()
    return {"scenarios": scenarios, "count": len(scenarios)}


@router.post("/scenarios/run")
async def run_scenario(request: ScenarioRunRequest) -> dict:
    """Run a what-if scenario analysis against the RAG knowledge base.

    Returns structured outcomes with impact scores, confidence intervals,
    and evidence-backed recommendations.

    Built-in scenario types: **demand_surge**, **supplier_failure**,
    **lead_time_increase**, **cost_pressure**, **custom**
    """
    engine = _get_scenario_engine()
    try:
        result = engine.run(
            ScenarioRequest(
                scenario_type=request.scenario_type,
                variables=request.variables,
                filters=request.filters,
                top_k=request.top_k,
                rerank_strategy=request.rerank_strategy,
            )
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Scenario run error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "scenario_type": result.scenario_type,
        "variables": result.variables,
        "narrative": result.narrative,
        "outcomes": [
            {
                "dimension": o.dimension,
                "assessment": o.assessment,
                "severity": o.severity,
                "confidence": o.confidence,
                "evidence": o.evidence,
            }
            for o in result.outcomes
        ],
        "impact_score": result.impact_score,
        "confidence_interval": list(result.confidence_interval),
        "recommended_actions": result.recommended_actions,
        "sources": result.sources,
        "ran_at": result.ran_at,
        "offline_mode": result.offline_mode,
    }


# ── Agentic workflows ─────────────────────────────────────────────────────────

@router.get("/workflows")
async def list_workflows_or_runs(
    list_runs: bool = Query(False, description="If true, return recent workflow runs instead of templates"),
    workflow: Optional[str] = Query(None, description="Filter runs by workflow name"),
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    """List workflow templates (default) or recent workflow runs (?list_runs=true)."""
    runner = _get_agent_runner()
    if list_runs:
        runs = runner.list_runs(workflow=workflow, limit=limit)
        return {"runs": runs, "count": len(runs)}
    workflows = runner.list_workflows()
    return {"workflows": workflows, "count": len(workflows)}


@router.post("/workflows/run")
async def run_workflow(request: WorkflowRunRequest) -> dict:
    """Execute a multi-step agentic workflow.

    The runner executes each step sequentially, passing accumulated context
    from prior steps forward. Returns the full step trace and a final synthesis.

    Built-in workflows: **investigate_anomaly**, **weekly_risk_summary**,
    **propose_mitigations**, **supplier_onboarding**
    """
    runner = _get_agent_runner()
    try:
        run = runner.execute(
            WorkflowRequest(
                workflow=request.workflow,
                context=request.context,
                filters=request.filters,
                top_k=request.top_k,
                rerank_strategy=request.rerank_strategy,
            )
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Workflow execution error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "run_id": run.run_id,
        "workflow": run.workflow,
        "status": run.status,
        "context": run.context,
        "steps": [
            {
                "step_name": s.step_name,
                "description": s.description,
                "output": s.output,
                "sources": s.sources,
                "error": s.error,
                "duration_ms": round(s.duration_ms, 1),
            }
            for s in run.steps
        ],
        "synthesis": run.synthesis,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "offline_mode": run.offline_mode,
    }


@router.get("/workflows/{run_id}")
async def get_workflow_run(run_id: str) -> dict:
    """Retrieve a persisted workflow run by ID."""
    runner = _get_agent_runner()
    run = runner.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Workflow run '{run_id}' not found")
    return {
        "run_id": run.run_id,
        "workflow": run.workflow,
        "status": run.status,
        "context": run.context,
        "steps": [
            {
                "step_name": s.step_name,
                "description": s.description,
                "output": s.output,
                "error": s.error,
                "duration_ms": round(s.duration_ms, 1),
            }
            for s in run.steps
        ],
        "synthesis": run.synthesis,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "offline_mode": run.offline_mode,
    }


# ── Human-in-the-loop ────────────────────────────────────────────────────────

@router.post("/hitl/submit", status_code=201)
async def submit_for_review(request: HITLSubmitRequest) -> dict:
    """Submit an AI-generated finding for human review before action.

    Sets status to **pending**. Reviewers can then approve, reject, or
    request revision via the decide endpoint.
    """
    queue = _get_hitl_queue()
    try:
        item = queue.submit(
            ReviewRequest(
                source_type=request.source_type,
                source_id=request.source_id,
                title=request.title,
                content=request.content,
                submitted_by=request.submitted_by,
                priority=request.priority,
                tags=request.tags,
                metadata=request.metadata,
            )
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return _review_to_dict(item)


@router.get("/hitl")
async def list_review_queue(
    status: Optional[str] = Query(None, description="Filter by status: pending | approved | rejected | needs_revision"),
    priority: Optional[str] = Query(None, description="Filter by priority: low | normal | high | urgent"),
    source_type: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    """List items in the human review queue."""
    queue = _get_hitl_queue()
    try:
        items = queue.list_items(status=status, priority=priority, source_type=source_type, limit=limit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"items": [_review_to_dict(i) for i in items], "count": len(items)}


@router.get("/hitl/stats")
async def review_queue_stats() -> dict:
    """Return review queue counts by status and priority."""
    return _get_hitl_queue().queue_stats()


@router.get("/hitl/{review_id}")
async def get_review_item(review_id: str) -> dict:
    """Get a single review item with full history."""
    item = _get_hitl_queue().get(review_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Review '{review_id}' not found")
    return _review_to_dict(item)


@router.post("/hitl/{review_id}/decide")
async def decide_review(review_id: str, body: HITLDecideRequest) -> dict:
    """Record a reviewer's decision: approved | rejected | needs_revision."""
    queue = _get_hitl_queue()
    try:
        item = queue.decide(
            review_id,
            ReviewDecision(
                decision=body.decision,
                reviewer=body.reviewer,
                comment=body.comment,
                correction=body.correction,
            ),
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return _review_to_dict(item)


@router.post("/hitl/{review_id}/resubmit")
async def resubmit_review(review_id: str, body: HITLResubmitRequest) -> dict:
    """Resubmit a needs_revision item with corrected content."""
    queue = _get_hitl_queue()
    try:
        item = queue.resubmit(review_id, body.revised_content, body.submitted_by)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return _review_to_dict(item)


@router.post("/hitl/{review_id}/feedback")
async def capture_feedback(review_id: str, body: HITLFeedbackRequest) -> dict:
    """Append free-form feedback to a review item for model correction workflows."""
    queue = _get_hitl_queue()
    try:
        item = queue.capture_feedback(review_id, body.feedback, body.by)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _review_to_dict(item)


# ── helpers ───────────────────────────────────────────────────────────────────

def _review_to_dict(item) -> dict:
    return {
        "review_id": item.review_id,
        "source_type": item.source_type,
        "source_id": item.source_id,
        "title": item.title,
        "content": item.content,
        "submitted_by": item.submitted_by,
        "priority": item.priority,
        "tags": item.tags,
        "metadata": item.metadata,
        "status": item.status,
        "submitted_at": item.submitted_at,
        "decided_at": item.decided_at,
        "reviewer": item.reviewer,
        "comment": item.comment,
        "correction": item.correction,
        "history": item.history,
    }
