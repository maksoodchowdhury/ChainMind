import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.evaluator import EvalSample, RAGEvaluator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/eval", tags=["evaluation"])

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
