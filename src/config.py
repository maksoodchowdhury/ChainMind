import logging
from pydantic_settings import BaseSettings
from typing import Optional

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # API Configuration
    app_name: str = "SupplyChain RAG Assistant"
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

    @property
    def valid_api_keys(self) -> set[str]:
        return {k.strip() for k in self.api_keys.split(",") if k.strip()}

    # OpenTelemetry tracing (optional — requires: pip install opentelemetry-api opentelemetry-sdk)
    enable_tracing: bool = False
    otlp_endpoint: str = "http://localhost:4317"

    # Logging
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = False

    @property
    def qdrant_connection_url(self) -> str:
        if self.qdrant_url:
            return self.qdrant_url
        return f"http://{self.qdrant_host}:{self.qdrant_port}"


def get_settings() -> Settings:
    return Settings()
