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


# ── Golden dataset + regression API tests ─────────────────────────────────────

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def api_client(tmp_path, monkeypatch):
    """TestClient with golden store redirected to a tmp dir."""
    import src.api_eval as ae

    monkeypatch.setattr(ae, "_GOLDEN_STORE", tmp_path / "golden_dataset.json")
    from src.main import app

    return TestClient(app)


def test_add_golden_sample(api_client):
    resp = api_client.post(
        "/api/eval/golden-set",
        json={"question": "What is Q3 demand?", "ground_truth": "250k units.", "tags": ["demand"]},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["question"] == "What is Q3 demand?"
    assert "id" in data


def test_list_golden_samples(api_client):
    api_client.post(
        "/api/eval/golden-set",
        json={"question": "Lead time?", "ground_truth": "6 weeks.", "tags": ["logistics"]},
    )
    resp = api_client.get("/api/eval/golden-set")
    assert resp.status_code == 200
    assert resp.json()["count"] >= 1


def test_list_golden_samples_filter_by_tag(api_client):
    api_client.post(
        "/api/eval/golden-set",
        json={"question": "Reorder point?", "ground_truth": "500 units.", "tags": ["inventory"]},
    )
    resp = api_client.get("/api/eval/golden-set?tag=inventory")
    assert resp.status_code == 200
    samples = resp.json()["samples"]
    assert all("inventory" in s["tags"] for s in samples)


def test_delete_golden_sample(api_client):
    add_resp = api_client.post(
        "/api/eval/golden-set",
        json={"question": "Delete me?", "ground_truth": "yes.", "tags": []},
    )
    sample_id = add_resp.json()["id"]
    del_resp = api_client.delete(f"/api/eval/golden-set/{sample_id}")
    assert del_resp.status_code == 204
    # Should be gone
    list_resp = api_client.get("/api/eval/golden-set")
    ids = [s["id"] for s in list_resp.json()["samples"]]
    assert sample_id not in ids


def test_delete_golden_sample_not_found(api_client):
    resp = api_client.delete("/api/eval/golden-set/nonexistent-id")
    assert resp.status_code == 404


def test_regression_run_no_samples(api_client):
    resp = api_client.post("/api/eval/regression-run")
    assert resp.status_code == 400


def test_regression_run_with_golden_samples(api_client):
    api_client.post(
        "/api/eval/golden-set",
        json={"question": "What is safety stock?", "ground_truth": "Buffer inventory.", "tags": []},
    )
    resp = api_client.post("/api/eval/regression-run")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_samples"] >= 1
    assert "run_id" in data
    assert "ran_at" in data
