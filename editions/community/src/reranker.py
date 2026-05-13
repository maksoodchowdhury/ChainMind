"""
Cross-encoder re-ranking layer.

Loads a sentence-transformers CrossEncoder on first use. If the package is not
installed the module degrades gracefully — nodes are returned in their original
vector-similarity order.
"""

import logging
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

_model = None
_model_name: str = ""
_available: bool | None = None  # None = not yet probed


def _load(model_name: str) -> bool:
    global _model, _model_name, _available
    if _available is not None and _model_name == model_name:
        return _available
    try:
        from sentence_transformers import CrossEncoder  # type: ignore

        _model = CrossEncoder(model_name)
        _model_name = model_name
        _available = True
        logger.info(f"Re-ranker ready: {model_name}")
    except ImportError:
        _available = False
        logger.warning(
            "sentence-transformers not installed — re-ranking disabled. "
            "Install with: pip install sentence-transformers"
        )
    except Exception as e:
        _available = False
        logger.warning(f"Re-ranker could not load '{model_name}': {e}")
    return _available


def rerank(query: str, nodes: list, top_n: int, model_name: str) -> list:
    """
    Re-rank retrieved NodeWithScore objects using a cross-encoder.

    Falls back to returning the first ``top_n`` nodes by vector score when the
    re-ranker is unavailable.
    """
    if not nodes:
        return nodes

    if not _load(model_name):
        return nodes[:top_n]

    pairs = [(query, node.node.get_content()) for node in nodes]
    scores = _model.predict(pairs)  # type: ignore[union-attr]

    # Mutate scores so callers can inspect them
    for node, score in zip(nodes, scores):
        node.score = float(score)

    reranked = sorted(nodes, key=lambda n: n.score, reverse=True)[:top_n]
    logger.debug(f"Re-ranked {len(nodes)} → {len(reranked)} nodes")
    return reranked
