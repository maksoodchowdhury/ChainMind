"""Query-classification and policy selection for retrieval settings."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class QueryPolicy:
    query_class: str
    top_k: int
    rerank_strategy: str


def classify_query(query: str) -> str:
    q = query.lower()
    if re.search(r"risk|disruption|exposure|incident|breach", q):
        return "risk"
    if re.search(r"inventory|stockout|safety stock|reorder|eoq", q):
        return "inventory"
    if re.search(r"supplier|vendor|otd|quality|defect", q):
        return "supplier"
    if re.search(r"lead time|latency|delay|shipment", q):
        return "lead_time"
    return "general"


def policy_for_query(
    query: str,
    *,
    top_k: int,
    requested_rerank_strategy: str,
) -> QueryPolicy:
    query_class = classify_query(query)
    # Lightweight policy map. Can be externalized later.
    class_top_k = {
        "risk": max(top_k, 8),
        "inventory": max(top_k, 6),
        "supplier": max(top_k, 7),
        "lead_time": max(top_k, 6),
        "general": top_k,
    }
    default_strategy = {
        "risk": "cross_encoder",
        "inventory": "default",
        "supplier": "cross_encoder",
        "lead_time": "default",
        "general": "default",
    }

    rerank = requested_rerank_strategy or default_strategy[query_class]
    if rerank == "default":
        rerank = default_strategy[query_class]

    return QueryPolicy(
        query_class=query_class,
        top_k=class_top_k[query_class],
        rerank_strategy=rerank,
    )
