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


def test_valid_roles_property():
    settings = Settings(openai_api_key="test-key", allowed_roles="admin, analyst,viewer")
    assert settings.valid_roles == {"admin", "analyst", "viewer"}


def test_new_hardening_defaults_present():
    settings = Settings(openai_api_key="test-key")
    assert settings.circuit_breaker_enabled is True
    assert settings.retry_budget_enabled is True
    assert settings.ingestion_queue_enabled is True
    assert settings.semantic_dedup_enabled is True


def test_secret_provider_file(monkeypatch, tmp_path):
    secrets = tmp_path / "secrets.json"
    secrets.write_text('{"OPENAI_API_KEY": "file-key"}')
    settings = Settings(openai_api_key=None, secret_provider="file", secrets_file=str(secrets))
    from src.secrets_provider import load_secret

    value = load_secret("OPENAI_API_KEY", provider=settings.secret_provider, secrets_file=settings.secrets_file)
    assert value == "file-key"


def test_transport_security_setting_exists():
    settings = Settings(openai_api_key="test-key", enforce_transport_security=True)
    assert settings.enforce_transport_security is True


def test_secret_provider_vault_env_map(monkeypatch):
    monkeypatch.setenv("VAULT_SECRET_OPENAI_API_KEY", "vault-key")
    from src.secrets_provider import load_secret

    value = load_secret("OPENAI_API_KEY", provider="vault")
    assert value == "vault-key"
