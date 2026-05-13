import logging
import json
import os
from pathlib import Path
from typing import Generator, Optional
from collections import Counter
import re

from llama_index.core import VectorStoreIndex
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.vector_stores.types import (
    MetadataFilters,
    MetadataFilter,
    FilterOperator,
    FilterCondition,
)
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI
from qdrant_client import QdrantClient

from src import document_processor as dp
from src.extensions import apply_extractor_extension, apply_ranker_extension
from src import reranker as reranker_module
from src.resilience import CircuitBreaker, CircuitOpenError, call_with_retry_budget
from src.tracer import span

logger = logging.getLogger(__name__)


def _build_metadata_filters(filters: dict) -> Optional[MetadataFilters]:
    """Convert a plain dict of key=value pairs into LlamaIndex MetadataFilters."""
    if not filters:
        return None
    active = [
        MetadataFilter(key=k, value=v, operator=FilterOperator.EQ)
        for k, v in filters.items()
        if v is not None
    ]
    return MetadataFilters(filters=active, condition=FilterCondition.AND) if active else None


class RAGPipeline:
    """RAG Pipeline for supply chain document processing.

    Enhancements over v1:
    - Async-safe document loading with chunk count return
    - Document-level metadata stored in Qdrant payload
    - Metadata filtering at query time
    - Optional BM25 hybrid search (Reciprocal Rank Fusion)
    - Optional cross-encoder re-ranking
    - Streaming response generator
    """

    def __init__(self, settings) -> None:
        self.settings = settings
        self.client: Optional[QdrantClient] = None
        self.vector_store: Optional[QdrantVectorStore] = None
        self.index: Optional[VectorStoreIndex] = None
        self.llm: Optional[OpenAI] = None
        self.embed_model: Optional[OpenAIEmbedding] = None
        # Accumulates all nodes for BM25; rebuilt on each load_documents call
        self._bm25_nodes: list = []
        self.offline_mode: bool = not bool(getattr(settings, "openai_api_key", None))
        self._offline_corpus: list[dict] = []
        self._breaker = CircuitBreaker(
            fail_threshold=getattr(settings, "circuit_breaker_fail_threshold", 5),
            recovery_seconds=getattr(settings, "circuit_breaker_recovery_seconds", 30),
        )

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """Connect to Qdrant, configure LLM + embeddings, and load existing index."""
        try:
            if self.offline_mode:
                logger.info("OpenAI key not configured — using offline demo mode")
                self.client = None
                self.vector_store = None
                self.index = None
                self.llm = None
                self.embed_model = None
                return

            self.client = QdrantClient(url=self.settings.qdrant_connection_url)
            logger.info(f"Connected to Qdrant at {self.settings.qdrant_connection_url}")

            self.embed_model = OpenAIEmbedding(
                model=self.settings.embedding_model,
                api_key=self.settings.openai_api_key,
            )

            self.vector_store = QdrantVectorStore(
                client=self.client,
                collection_name=self.settings.collection_name,
                prefer_grpc=False,
            )

            self.llm = OpenAI(
                model=self.settings.openai_model,
                api_key=self.settings.openai_api_key,
                temperature=0.3,
            )

            # Recover persisted vectors from Qdrant without re-embedding
            try:
                self.index = VectorStoreIndex.from_vector_store(
                    vector_store=self.vector_store,
                    embed_model=self.embed_model,
                )
                logger.info("Loaded existing index from Qdrant")
            except Exception:
                self.index = None
                logger.info("No existing index found — will create on first upload")

            logger.info("RAG pipeline initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize RAG pipeline: {e}")
            raise

    # ------------------------------------------------------------------
    # Document ingestion
    # ------------------------------------------------------------------

    def load_documents(
        self, file_paths: list[str], extra_metadata: Optional[dict] = None
    ) -> int:
        """Process files with format detection, semantic chunking, and fingerprinting.

        Files whose SHA-256 hash is already registered are skipped (no re-embedding).
        Returns the total number of nodes indexed across all files.
        """
        extra_metadata = extra_metadata or {}
        total_nodes = 0

        for path in file_paths:
            if os.path.isdir(path):
                for f in Path(path).iterdir():
                    if f.is_file():
                        total_nodes += self._process_single_file(str(f), extra_metadata)
            elif os.path.isfile(path):
                total_nodes += self._process_single_file(path, extra_metadata)

        return total_nodes

    def _process_single_file(self, file_path: str, metadata: dict) -> int:
        """Load, chunk, and index a single file. Returns node count (0 if skipped)."""
        with span("rag.ingest.file", {"file": Path(file_path).name}):
            if dp.is_already_indexed(file_path):
                logger.info(f"Skipping already-indexed file: {Path(file_path).name}")
                return 0
            if getattr(self.settings, "semantic_dedup_enabled", False):
                if dp.is_semantically_duplicate(
                    file_path,
                    threshold=getattr(self.settings, "semantic_dedup_threshold", 0.92),
                ):
                    logger.info(f"Skipping semantically-duplicate file: {Path(file_path).name}")
                    return 0
            try:
                docs = dp.load_file_as_documents(
                    file_path,
                    metadata,
                    pii_redaction_enabled=getattr(self.settings, "pii_redaction_enabled", True),
                )
                docs = apply_extractor_extension(
                    docs,
                    extension_name=getattr(self.settings, "active_extractor_extension", None),
                )
                nodes = dp.apply_chunking(
                    docs,
                    chunk_size=self.settings.chunk_size,
                    chunk_overlap=self.settings.chunk_overlap,
                    strategy=self.settings.chunking_strategy,
                    embed_model=self.embed_model,
                )
                if self.offline_mode:
                    self._offline_corpus.extend(
                        [
                            {
                                "document": node.metadata.get("file_name", Path(file_path).name),
                                "text": node.get_content(),
                                "metadata": dict(node.metadata),
                            }
                            for node in nodes
                        ]
                    )
                    dp.register_indexed(file_path, len(nodes))
                    logger.info(f"Offline indexed {len(nodes)} nodes from {Path(file_path).name}")
                    return len(nodes)
                self._create_or_update_index(nodes)
                dp.register_indexed(file_path, len(nodes))
                return len(nodes)
            except Exception as e:
                logger.error(f"Failed to process {file_path}: {e}")
                raise

    def _create_or_update_index(self, nodes: list) -> None:
        if not self.index:
            self.index = VectorStoreIndex(
                nodes,
                vector_store=self.vector_store,
                embed_model=self.embed_model,
                show_progress=True,
            )
            logger.info(f"Created index with {len(nodes)} nodes")
        else:
            self.index.insert_nodes(nodes)
            logger.info(f"Inserted {len(nodes)} nodes into existing index")

        if self.settings.enable_hybrid_search:
            self._bm25_nodes.extend(nodes)

    # ------------------------------------------------------------------
    # Retrieval helpers
    # ------------------------------------------------------------------

    def _get_retriever(self, top_k: int, filters: Optional[dict]):
        """Return the appropriate retriever: vector-only or hybrid BM25+vector."""
        if self.offline_mode:
            return None
        md_filters = _build_metadata_filters(filters or {})

        vector_retriever = VectorIndexRetriever(
            index=self.index,
            similarity_top_k=top_k,
            filters=md_filters,
        )

        if not self.settings.enable_hybrid_search or not self._bm25_nodes:
            return vector_retriever

        try:
            from llama_index.retrievers.bm25 import BM25Retriever  # type: ignore
            from llama_index.core.retrievers import QueryFusionRetriever

            bm25_retriever = BM25Retriever.from_defaults(
                nodes=self._bm25_nodes,
                similarity_top_k=top_k,
            )
            return QueryFusionRetriever(
                retrievers=[vector_retriever, bm25_retriever],
                similarity_top_k=top_k,
                num_queries=1,           # no LLM-based query expansion
                mode="reciprocal_rerank",  # RRF fusion
            )
        except ImportError:
            logger.warning(
                "llama-index-retrievers-bm25 not installed — "
                "falling back to vector-only search. "
                "Install: pip install llama-index-retrievers-bm25 rank-bm25"
            )
            return vector_retriever

    def _apply_reranking(self, nodes: list, query: str, strategy: str = "default") -> list:
        active_ranker = getattr(self.settings, "active_ranker_extension", None)
        if strategy.startswith("extension:"):
            ext_name = strategy.split(":", 1)[1].strip() or active_ranker
            return apply_ranker_extension(nodes, query, ext_name)

        if active_ranker:
            nodes = apply_ranker_extension(nodes, query, active_ranker)

        # "none" => skip re-ranking regardless of server settings
        if strategy == "none":
            return nodes
        # "cross_encoder" => force cross-encoder even if flag is off
        if strategy == "cross_encoder" or self.settings.enable_reranking:
            return reranker_module.rerank(
                query=query,
                nodes=nodes,
                top_n=self.settings.rerank_top_n,
                model_name=self.settings.rerank_model,
            )
        return nodes

    @staticmethod
    def _format_sources(nodes: list) -> list[dict]:
        return [
            {
                "document": node.metadata.get("file_name", "Unknown"),
                "score": float(node.score) if node.score is not None else 0.0,
                "content_snippet": node.node.get_content()[:200],
                "metadata": {
                    k: v
                    for k, v in node.metadata.items()
                    if k not in {"file_name", "_node_content", "_node_type"}
                },
            }
            for node in nodes
        ]

    def _offline_search(self, query_text: str, top_k: int, filters: Optional[dict]) -> list[dict]:
        """Simple keyword-based ranking for demo mode when OpenAI/Qdrant are unavailable."""
        query_tokens = [t for t in re.findall(r"[a-z0-9]+", query_text.lower()) if len(t) > 2]
        if not query_tokens:
            return []

        allowed = filters or {}
        ranked: list[tuple[float, dict]] = []
        for item in self._offline_corpus:
            metadata = item.get("metadata", {})
            if any(str(metadata.get(k, "")).lower() != str(v).lower() for k, v in allowed.items()):
                continue
            text = f"{item.get('document', '')} {item.get('text', '')} {json.dumps(metadata)}".lower()
            counts = Counter(query_tokens)
            score = sum(text.count(tok) * count for tok, count in counts.items())
            if score:
                ranked.append((float(score), item))

        ranked.sort(key=lambda x: x[0], reverse=True)
        sources = []
        for score, item in ranked[:top_k]:
            sources.append(
                {
                    "document": item.get("document", "Unknown"),
                    "score": score,
                    "content_snippet": str(item.get("text", ""))[:200],
                    "metadata": item.get("metadata", {}),
                }
            )
        return sources

    @staticmethod
    def _offline_answer(query_text: str, sources: list[dict]) -> str:
        if not sources:
            return (
                "I could not find a strong match in the uploaded documents. "
                "Try rephrasing the question or upload a more relevant file."
            )

        lead = sources[0]
        second = sources[1] if len(sources) > 1 else None
        summary = [
            f"Based on the uploaded documents, the closest match for '{query_text}' is {lead['document']}.",
            f"Key evidence: {lead['content_snippet'].strip()}".strip(),
        ]
        if second:
            summary.append(f"Additional context from {second['document']}: {second['content_snippet'].strip()}")
        return "\n\n".join(summary)

    # ------------------------------------------------------------------
    # Query — blocking
    # ------------------------------------------------------------------

    def query(
        self,
        query_text: str,
        top_k: Optional[int] = None,
        filters: Optional[dict] = None,
        rerank_strategy: str = "default",
    ) -> dict:
        """Query the index. Returns answer string + citations."""
        if getattr(self.settings, "circuit_breaker_enabled", True) and not self._breaker.allow():
            raise CircuitOpenError("RAG dependency circuit is open. Retry later.")

        if not self.index:
            if not self.offline_mode:
                raise ValueError("Index not initialized. Load documents first.")

        top_k = top_k or self.settings.top_k_retrieved

        with span("rag.query", {"query": query_text[:100], "top_k": top_k}):
            if self.offline_mode:
                sources = self._offline_search(query_text, top_k, filters)
                return {
                    "query": query_text,
                    "answer": self._offline_answer(query_text, sources),
                    "sources": sources,
                }

            try:
                retriever = self._get_retriever(top_k, filters)

                with span("rag.llm.generate"):
                    query_engine = RetrieverQueryEngine.from_args(retriever=retriever, llm=self.llm)
                    if getattr(self.settings, "retry_budget_enabled", True):
                        response = call_with_retry_budget(
                            lambda: query_engine.query(query_text),
                            max_attempts=getattr(self.settings, "retry_budget_max_attempts", 3),
                            backoff_seconds=getattr(self.settings, "retry_budget_backoff_seconds", 0.3),
                        )
                    else:
                        response = query_engine.query(query_text)

                with span("rag.rerank", {"nodes_in": len(response.source_nodes)}):
                    nodes = self._apply_reranking(
                        list(response.source_nodes), query_text, strategy=rerank_strategy
                    )

                self._breaker.mark_success()
            except Exception:
                self._breaker.mark_failure()
                raise

        return {
            "query": query_text,
            "answer": str(response),
            "sources": self._format_sources(nodes),
        }

    # ------------------------------------------------------------------
    # Query — streaming
    # ------------------------------------------------------------------

    def query_stream(
        self,
        query_text: str,
        top_k: Optional[int] = None,
        filters: Optional[dict] = None,
    ) -> Generator[str, None, None]:
        """Yield answer tokens incrementally as the LLM produces them."""
        if not self.index:
            if not self.offline_mode:
                raise ValueError("Index not initialized. Load documents first.")

        top_k = top_k or self.settings.top_k_retrieved
        if self.offline_mode:
            sources = self._offline_search(query_text, top_k, filters)
            for token in self._offline_answer(query_text, sources).split():
                yield token + " "
            return
        retriever = self._get_retriever(top_k, filters)
        query_engine = RetrieverQueryEngine.from_args(
            retriever=retriever, llm=self.llm, streaming=True
        )
        streaming_response = query_engine.query(query_text)
        yield from streaming_response.response_gen

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health_check(self) -> bool:
        try:
            if self.offline_mode:
                return True
            if self.client:
                self.client.get_collections()
                return True
        except Exception as e:
            logger.error(f"Health check failed: {e}")
        return False
