"""Tests for RAGAS evaluation pipeline."""

import pytest
from unittest.mock import MagicMock, patch

from src.evaluator import EvalSample, EvalResult, RAGEvaluator


def test_evaluate_empty_samples():
    evaluator = RAGEvaluator()
    result = evaluator.evaluate([])
    assert result.sample_count == 0
    assert result.scores == {}


def test_evaluate_degrades_without_ragas():
    """Should return a graceful error result, not raise, when ragas is missing."""
    evaluator = RAGEvaluator()
    evaluator._ragas_available = None  # force re-probe

    with patch.dict("sys.modules", {"ragas": None, "datasets": None}):
        result = evaluator.evaluate(
            [EvalSample(question="q", answer="a", contexts=["c"])]
        )
    assert result.sample_count == 1
    assert isinstance(result.errors, list)


def test_eval_sample_fields():
    sample = EvalSample(
        question="What is lead time?",
        answer="6-8 weeks.",
        contexts=["Supplier lead time is 6 to 8 weeks."],
        ground_truth="Lead time is 6-8 weeks.",
    )
    assert sample.ground_truth == "Lead time is 6-8 weeks."
    assert len(sample.contexts) == 1


def test_eval_result_structure():
    result = EvalResult(
        scores={"faithfulness": 0.91, "answer_relevancy": 0.85},
        sample_count=3,
    )
    assert result.scores["faithfulness"] == pytest.approx(0.91)
    assert result.sample_count == 3
    assert result.errors == []


def test_evaluate_with_mocked_ragas():
    """Verify _run is called and scores are returned when ragas is available."""
    evaluator = RAGEvaluator()
    expected = EvalResult(
        scores={"faithfulness": 0.9, "answer_relevancy": 0.8, "context_precision": 0.7},
        sample_count=1,
    )
    evaluator._ragas_available = True

    with patch.object(evaluator, "_run", return_value=expected):
        result = evaluator.evaluate(
            [EvalSample(question="q", answer="a", contexts=["ctx"])]
        )
    assert result.scores["faithfulness"] == pytest.approx(0.9)
    assert result.sample_count == 1
