import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.evaluator import EvalSample, RAGEvaluator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/eval", tags=["evaluation"])

# ── persistent golden-dataset store ───────────────────────────────────────────
_GOLDEN_STORE = Path("data/golden_dataset.json")


def _load_golden() -> dict:
    if _GOLDEN_STORE.exists():
        try:
            return json.loads(_GOLDEN_STORE.read_text())
        except Exception:
            return {"samples": {}}
    return {"samples": {}}


def _save_golden(data: dict) -> None:
    _GOLDEN_STORE.parent.mkdir(parents=True, exist_ok=True)
    _GOLDEN_STORE.write_text(json.dumps(data, indent=2))

_evaluator: Optional[RAGEvaluator] = None


def _get_evaluator() -> RAGEvaluator:
    global _evaluator
    if _evaluator is None:
        from src.main import settings

        _evaluator = RAGEvaluator(openai_api_key=settings.openai_api_key)
    return _evaluator


class EvalSampleRequest(BaseModel):
    question: str
    answer: str
    contexts: list[str]
    ground_truth: Optional[str] = None


class EvalRequest(BaseModel):
    """Batch of samples to evaluate with RAGAS."""

    samples: list[EvalSampleRequest]


class EvalResponse(BaseModel):
    scores: dict[str, float]
    sample_count: int
    errors: list[str] = []


@router.post("/", response_model=EvalResponse)
async def evaluate_rag(request: EvalRequest) -> EvalResponse:
    """Evaluate a batch of (question, answer, contexts) triples with RAGAS.

    Metrics returned:
    - **faithfulness**: fraction of answer claims supported by context
    - **answer_relevancy**: how well the answer addresses the question
    - **context_precision**: are highly relevant chunks ranked first?
    - **context_recall**: does context cover the ground truth? *(requires ground_truth)*
    """
    if not request.samples:
        raise HTTPException(status_code=400, detail="No samples provided")

    samples = [
        EvalSample(
            question=s.question,
            answer=s.answer,
            contexts=s.contexts,
            ground_truth=s.ground_truth,
        )
        for s in request.samples
    ]

    result = _get_evaluator().evaluate(samples)

    return EvalResponse(
        scores=result.scores,
        sample_count=result.sample_count,
        errors=result.errors,
    )


@router.post("/query-and-eval")
async def query_then_evaluate(
    question: str,
    ground_truth: Optional[str] = None,
    top_k: int = 5,
) -> EvalResponse:
    """Run a single RAG query then immediately evaluate it.

    Useful for quickly measuring the quality of a specific question
    without building a separate evaluation dataset.
    """
    from src.main import rag_pipeline

    try:
        result = rag_pipeline.query(question, top_k=top_k)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    contexts = [s["content_snippet"] for s in result["sources"]]
    sample = EvalSample(
        question=question,
        answer=result["answer"],
        contexts=contexts,
        ground_truth=ground_truth,
    )

    eval_result = _get_evaluator().evaluate([sample])
    return EvalResponse(
        scores=eval_result.scores,
        sample_count=1,
        errors=eval_result.errors,
    )


# ── Golden dataset CRUD ────────────────────────────────────────────────────────

class GoldenSampleRequest(BaseModel):
    question: str
    ground_truth: str
    tags: list[str] = []


class GoldenSampleResponse(BaseModel):
    id: str
    question: str
    ground_truth: str
    tags: list[str] = []
    created_at: str


@router.post("/golden-set", status_code=201, response_model=GoldenSampleResponse)
async def add_golden_sample(body: GoldenSampleRequest) -> GoldenSampleResponse:
    """Store a golden question/answer pair for regression testing."""
    data = _load_golden()
    sample_id = str(uuid.uuid4())
    record = {
        "id": sample_id,
        "question": body.question,
        "ground_truth": body.ground_truth,
        "tags": body.tags,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    data["samples"][sample_id] = record
    _save_golden(data)
    return GoldenSampleResponse(**record)


@router.get("/golden-set")
async def list_golden_samples(tag: Optional[str] = None) -> dict:
    """List all golden samples, optionally filtered by tag."""
    data = _load_golden()
    samples = list(data.get("samples", {}).values())
    if tag:
        samples = [s for s in samples if tag in s.get("tags", [])]
    return {"samples": samples, "count": len(samples)}


@router.delete("/golden-set/{sample_id}", status_code=204)
async def delete_golden_sample(sample_id: str) -> None:
    """Delete a golden sample by ID."""
    data = _load_golden()
    if sample_id not in data.get("samples", {}):
        raise HTTPException(status_code=404, detail=f"Golden sample '{sample_id}' not found")
    del data["samples"][sample_id]
    _save_golden(data)


# ── Regression run ─────────────────────────────────────────────────────────────

class RegressionRunResponse(BaseModel):
    run_id: str
    total_samples: int
    scores: dict[str, float]
    errors: list[str] = []
    ran_at: str


@router.post("/regression-run", response_model=RegressionRunResponse)
async def run_regression(tag: Optional[str] = None) -> RegressionRunResponse:
    """Run evaluation over all (or tagged) golden samples using the live RAG pipeline.

    Each golden question is answered by the RAG engine; the answer + retrieved
    contexts are scored with RAGAS against the stored ground truth.
    """
    from src.main import rag_pipeline

    data = _load_golden()
    samples = list(data.get("samples", {}).values())
    if tag:
        samples = [s for s in samples if tag in s.get("tags", [])]

    if not samples:
        raise HTTPException(
            status_code=400,
            detail="No golden samples found. Add samples via POST /api/eval/golden-set first.",
        )

    eval_samples: list[EvalSample] = []
    errors: list[str] = []

    for s in samples:
        try:
            result = rag_pipeline.query(s["question"])
            contexts = [src["content_snippet"] for src in result.get("sources", [])]
            eval_samples.append(
                EvalSample(
                    question=s["question"],
                    answer=result["answer"],
                    contexts=contexts,
                    ground_truth=s["ground_truth"],
                )
            )
        except Exception as e:
            errors.append(f"[{s['id']}] {s['question'][:60]}: {e}")

    result = _get_evaluator().evaluate(eval_samples)
    return RegressionRunResponse(
        run_id=str(uuid.uuid4()),
        total_samples=len(samples),
        scores=result.scores,
        errors=errors + result.errors,
        ran_at=datetime.now(timezone.utc).isoformat(),
    )


# ── Quality diagnostics report ─────────────────────────────────────────────────

@router.get("/quality-report")
async def quality_report() -> dict:
    """Retrieval quality diagnostics report.

    Returns:
    - **golden_sample_count**: how many golden samples are stored
    - **avg_source_score**: mean similarity score across all sources in recent queries
    - **source_diversity**: number of distinct documents referenced by golden samples
    - **ragas_available**: whether the RAGAS evaluation backend is installed
    - **last_evaluated_at**: timestamp of most recently stored regression run data
    """
    from src.metrics import snapshot_metrics

    golden_data = _load_golden()
    golden_count = len(golden_data.get("samples", {}))
    evaluator = _get_evaluator()

    # Collect source diversity from golden samples (query each and count unique docs)
    from src.main import rag_pipeline

    unique_docs: set[str] = set()
    scores: list[float] = []
    sample_errors: list[str] = []

    for s in list(golden_data.get("samples", {}).values())[:20]:  # cap at 20 for latency
        try:
            result = rag_pipeline.query(s["question"])
            for src in result.get("sources", []):
                unique_docs.add(src.get("document", ""))
                if src.get("score") is not None:
                    scores.append(float(src["score"]))
        except Exception as e:
            sample_errors.append(str(e))

    avg_score = sum(scores) / len(scores) if scores else None
    metrics = snapshot_metrics()

    return {
        "golden_sample_count": golden_count,
        "avg_source_score": avg_score,
        "source_diversity": len(unique_docs),
        "unique_sources": sorted(unique_docs),
        "ragas_available": evaluator._check_ragas(),
        "request_metrics_summary": {
            "total_requests": metrics.get("total_requests", 0),
            "error_rate": metrics.get("error_rate", 0.0),
            "p95_latency_ms": metrics.get("p95_latency_ms", 0.0),
        },
        "errors": sample_errors,
        "report_generated_at": datetime.now(timezone.utc).isoformat(),
    }
