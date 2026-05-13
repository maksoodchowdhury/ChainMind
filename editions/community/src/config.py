import logging
import os
from pydantic_settings import BaseSettings
from typing import Optional

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # API Configuration
    app_name: str = "ChainMind Community"
    app_version: str = "0.2.0"
    debug: bool = False

    # OpenAI Configuration
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4-turbo-preview"
    embedding_model: str = "text-embedding-3-small"

    # Qdrant Configuration
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_url: Optional[str] = None
    collection_name: str = "supply_chain_documents"

    # LlamaIndex — chunking & retrieval
    chunk_size: int = 1024
    chunk_overlap: int = 256
    top_k_retrieved: int = 5

    # Hybrid search (BM25 + vector via Reciprocal Rank Fusion)
    # Requires: pip install llama-index-retrievers-bm25 rank-bm25
    enable_hybrid_search: bool = False

    # Cross-encoder re-ranking
    # Requires: pip install sentence-transformers
    enable_reranking: bool = False
    rerank_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    rerank_top_n: int = 3  # Final results after re-ranking (must be ≤ top_k_retrieved)

    # Chunking strategy: "sentence" (default) | "semantic" | "fixed"
    chunking_strategy: str = "sentence"

    # Redis query-result cache (optional — requires: pip install redis)
    redis_url: Optional[str] = None
    cache_ttl_seconds: int = 3600

    # API key authentication
    auth_enabled: bool = False
    api_keys: str = ""   # comma-separated list, e.g. "key1,key2"

    # Authorization & tenancy
    authz_enabled: bool = False
    require_tenant_header: bool = False
    allowed_roles: str = "admin,analyst,viewer"
    tenant_isolation_mode: str = "shared-index"  # shared-index | dedicated-index
    tenant_quota_enabled: bool = True
    tenant_default_daily_quota: int = 1000
    tenant_default_monthly_quota: int = 25000

    @property
    def valid_roles(self) -> set[str]:
        return {r.strip().lower() for r in self.allowed_roles.split(",") if r.strip()}

    @property
    def valid_api_keys(self) -> set[str]:
        return {k.strip() for k in self.api_keys.split(",") if k.strip()}

    # OpenTelemetry tracing (optional — requires: pip install opentelemetry-api opentelemetry-sdk)
    enable_tracing: bool = False
    otlp_endpoint: str = "http://localhost:4317"

    # Logging
    log_level: str = "INFO"
    enable_structured_logging: bool = True

    # Basic in-memory rate limiting
    rate_limit_enabled: bool = False
    rate_limit_requests_per_window: int = 60
    rate_limit_window_seconds: int = 60

    # Resilience controls
    circuit_breaker_enabled: bool = True
    circuit_breaker_fail_threshold: int = 5
    circuit_breaker_recovery_seconds: int = 30
    retry_budget_enabled: bool = True
    retry_budget_max_attempts: int = 3
    retry_budget_backoff_seconds: float = 0.3

    # Ingestion queue backpressure
    max_inflight_ingestion_jobs: int = 50

    # Event-driven ingestion queue
    ingestion_queue_enabled: bool = True
    ingestion_poison_max_attempts: int = 3

    # Data safety: PII and retention
    pii_redaction_enabled: bool = True
    retention_days_uploads: int = 90
    retention_days_catalog_history: int = 365

    # Semantic deduplication (similarity threshold 0-1)
    semantic_dedup_enabled: bool = True
    semantic_dedup_threshold: float = 0.92

    # Secret management
    secret_provider: str = "env"  # env | file | vault | azure-keyvault
    secrets_file: str = "config/secrets.json"
    policy_file: str = "config/policies.json"
    azure_key_vault_url: Optional[str] = None

    # Data-at-rest encryption controls for persisted operational stores
    encrypt_data_at_rest: bool = False
    data_encryption_key: Optional[str] = None

    # Extension framework activation
    active_extractor_extension: Optional[str] = None
    active_ranker_extension: Optional[str] = None
    active_tool_extension: Optional[str] = None

    # Autonomous execution controls
    autonomy_auto_execute_enabled: bool = False
    autonomy_notify_webhook_url: Optional[str] = None
    autonomy_ticket_webhook_url: Optional[str] = None

    # Transport security guards
    enforce_transport_security: bool = False

    # SLO evaluation thresholds
    slo_error_rate_threshold: float = 0.01
    slo_p95_latency_ms_threshold: float = 800.0
    slo_minimum_requests: int = 20
    slo_webhook_url: Optional[str] = None
    slo_webhook_secret: Optional[str] = None
    slo_alert_cooldown_seconds: int = 300
    slo_webhook_max_attempts: int = 3
    slo_webhook_backoff_seconds: float = 1.0

    class Config:
        env_file = ".env"
        case_sensitive = False

    @property
    def qdrant_connection_url(self) -> str:
        if self.qdrant_url:
            return self.qdrant_url
        return f"http://{self.qdrant_host}:{self.qdrant_port}"


def get_settings() -> Settings:
    from src.secrets_provider import load_secret

    settings = Settings()
    if settings.encrypt_data_at_rest:
        os.environ["DATA_ENCRYPTION_ENABLED"] = "true"
    if settings.data_encryption_key:
        os.environ["DATA_ENCRYPTION_KEY"] = settings.data_encryption_key
    if settings.azure_key_vault_url:
        os.environ["AZURE_KEY_VAULT_URL"] = settings.azure_key_vault_url

    if not settings.openai_api_key:
        settings.openai_api_key = load_secret(
            "OPENAI_API_KEY",
            provider=settings.secret_provider,
            secrets_file=settings.secrets_file,
        )
    return settings
