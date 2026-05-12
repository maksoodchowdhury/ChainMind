import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.main import app


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def mock_rag_pipeline():
    """Mock RAG pipeline for testing."""
    with patch("src.main.rag_pipeline") as mock:
        mock.initialize.return_value = None
        mock.health_check.return_value = True
        mock.query.return_value = {
            "query": "test query",
            "answer": "test answer",
            "sources": [],
        }
        yield mock


def test_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "running"
    # New endpoints should be advertised
    assert "query_stream" in data["endpoints"]
    assert "evaluate" in data["endpoints"]
    assert "job_status" in data["endpoints"]


def test_health_check(client, mock_rag_pipeline):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] in ["healthy", "unhealthy"]


def test_list_documents(client):
    response = client.get("/api/documents/list")
    assert response.status_code == 200
    assert "documents" in response.json()


def test_query_empty(client, mock_rag_pipeline):
    response = client.post("/api/query/", json={"query": ""})
    assert response.status_code == 400


def test_query_success(client, mock_rag_pipeline):
    response = client.post(
        "/api/query/", json={"query": "What is our demand forecast?"}
    )
    assert response.status_code == 200
    assert "answer" in response.json()


def test_query_with_filters(client, mock_rag_pipeline):
    """Metadata filters should be accepted without error."""
    response = client.post(
        "/api/query/",
        json={
            "query": "What is supplier lead time?",
            "filters": {"supplier": "Ningbo Electronics", "doc_type": "demand_plan"},
        },
    )
    assert response.status_code == 200
    # Verify filters were forwarded to the pipeline
    call_kwargs = mock_rag_pipeline.query.call_args.kwargs
    assert call_kwargs["filters"].get("supplier") == "Ningbo Electronics"


def test_query_no_index(client, mock_rag_pipeline):
    """Should return 400 when index is not ready."""
    mock_rag_pipeline.query.side_effect = ValueError("Index not initialized")
    response = client.post("/api/query/", json={"query": "demand forecast?"})
    assert response.status_code == 400
