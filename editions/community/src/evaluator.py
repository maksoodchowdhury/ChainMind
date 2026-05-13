"""
RAGAS-based evaluation pipeline for retrieval quality and answer faithfulness.

Metrics computed:
- faithfulness       — is the answer grounded in the retrieved context?
- answer_relevancy   — does the answer address the question?
- context_precision  — are retrieved chunks ranked by relevance?
- context_recall     — does context cover the ground truth? (needs ground_truth)

Usage::

    from src.evaluator import RAGEvaluator, EvalSample
    evaluator = RAGEvaluator()
    results = evaluator.evaluate([
        EvalSample(
            question="What is Q3 demand?",
            answer="250k units in July.",
            contexts=["Electronics demand in Q3 is 250k units..."],
            ground_truth="Expected demand for electronics is 250,000 units.",
        )
    ])
    print(results.scores)   # {"faithfulness": 0.91, "answer_relevancy": 0.87, ...}
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class EvalSample:
    """A single question-answer-context tuple for evaluation."""

    question: str
    answer: str
    contexts: list[str]
    ground_truth: Optional[str] = None


@dataclass
class EvalResult:
    """Aggregated evaluation scores across all samples."""

    scores: dict[str, float]
    sample_count: int
    errors: list[str] = field(default_factory=list)


class RAGEvaluator:
    """Wraps RAGAS to measure retrieval quality and answer faithfulness."""

    _METRICS_NO_GT = ("faithfulness", "answer_relevancy", "context_precision")
    _METRICS_WITH_GT = _METRICS_NO_GT + ("context_recall",)

    def __init__(self, openai_api_key: Optional[str] = None) -> None:
        self._openai_api_key = openai_api_key
        self._ragas_available: Optional[bool] = None

    def _check_ragas(self) -> bool:
        if self._ragas_available is not None:
            return self._ragas_available
        try:
            import ragas  # noqa: F401
            import datasets  # noqa: F401

            self._ragas_available = True
        except ImportError:
            self._ragas_available = False
            logger.warning(
                "ragas / datasets not installed — evaluation disabled. "
                "Install with: pip install ragas datasets"
            )
        return self._ragas_available

    def evaluate(self, samples: list[EvalSample]) -> EvalResult:
        """Run RAGAS evaluation over a list of samples.

        Falls back to an empty result if RAGAS is not installed rather than
        crashing the calling service.
        """
        if not samples:
            return EvalResult(scores={}, sample_count=0)

        if not self._check_ragas():
            return EvalResult(
                scores={},
                sample_count=len(samples),
                errors=["ragas package not installed"],
            )

        try:
            return self._run(samples)
        except Exception as e:
            logger.error(f"RAGAS evaluation failed: {e}")
            return EvalResult(
                scores={},
                sample_count=len(samples),
                errors=[str(e)],
            )

    def _run(self, samples: list[EvalSample]) -> EvalResult:
        from ragas import evaluate  # type: ignore
        from ragas.metrics import (  # type: ignore
            faithfulness,
            answer_relevancy,
            context_precision,
        )
        from datasets import Dataset  # type: ignore

        has_ground_truth = all(s.ground_truth for s in samples)
        metrics = list(self._METRICS_NO_GT)

        if has_ground_truth:
            from ragas.metrics import context_recall  # type: ignore

            metrics_objs = [faithfulness, answer_relevancy, context_precision, context_recall]
        else:
            metrics_objs = [faithfulness, answer_relevancy, context_precision]

        data = {
            "question": [s.question for s in samples],
            "answer": [s.answer for s in samples],
            "contexts": [s.contexts for s in samples],
        }
        if has_ground_truth:
            data["ground_truth"] = [s.ground_truth for s in samples]

        dataset = Dataset.from_dict(data)
        result = evaluate(dataset, metrics=metrics_objs)
        df = result.to_pandas()

        scores = {col: float(df[col].mean()) for col in df.columns if col in metrics + ["context_recall"]}
        return EvalResult(scores=scores, sample_count=len(samples))
