import pytest
import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import Settings, get_settings


def test_settings_from_env(monkeypatch):
    """Test settings loading from environment variables."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("QDRANT_HOST", "localhost")
    monkeypatch.setenv("COLLECTION_NAME", "test_collection")

    settings = Settings(openai_api_key="test-key")
    assert settings.openai_api_key == "test-key"
    assert settings.qdrant_host == "localhost"


def test_qdrant_url_property():
    """Test Qdrant URL property."""
    settings = Settings(openai_api_key="test-key")
    assert settings.qdrant_connection_url == "http://localhost:6333"


def test_qdrant_custom_url():
    """Test custom Qdrant URL."""
    settings = Settings(
        openai_api_key="test-key",
        qdrant_url="http://custom:6333"
    )
    assert settings.qdrant_connection_url == "http://custom:6333"


def test_defaults():
    """Test default settings values."""
    settings = Settings(openai_api_key="test-key")
    assert settings.chunk_size == 1024
    assert settings.top_k_retrieved == 5
    assert settings.log_level == "INFO"
