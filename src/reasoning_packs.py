"""
Domain reasoning packs — supply-chain-specific prompt templates.

Each pack wraps a focused system prompt + structured output contract so the LLM
reasons within the narrow scope of one supply-chain discipline.  The pack is
passed to the query layer as an overlay that *replaces* the generic RAG prompt
while keeping the retrieved context injection mechanism unchanged.

Supported packs
---------------
- risk           → supplier risk, single-source exposure, geopolitical flags
- inventory      → reorder points, safety stock, EOQ, ABC classification
- supplier       → reliability score, on-time delivery, defect rate, lead-time trend
- lead_time      → volatility assessment, buffer recommendations, trend analysis

Usage::

    from src.reasoning_packs import get_pack, list_packs, ReasoningPack

    pack = get_pack("risk")
    # pack.system_prompt  → str fed to LLM as system message
    # pack.output_schema  → dict describing expected JSON keys
    # pack.render(context_text, question) → final user prompt
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ReasoningPack:
    """A domain-specific reasoning configuration for the LLM."""

    name: str
    description: str
    system_prompt: str
    output_schema: dict
    required_metadata_fields: list[str] = field(default_factory=list)

    def render(self, context: str, question: str) -> str:
        """Compose the user-turn message that includes retrieved context."""
        return (
            f"## Retrieved Supply-Chain Context\n\n{context}\n\n"
            f"## Question\n\n{question}\n\n"
            f"## Instructions\n\nAnswer using ONLY the context above. "
            f"Respond as valid JSON matching the schema: {self.output_schema}"
        )


# ── Pack definitions ─────────────────────────────────────────────────────────

_RISK_PACK = ReasoningPack(
    name="risk",
    description="Supplier risk assessment — single-source exposure, disruption probability, geopolitical flags.",
    system_prompt=(
        "You are a supply chain risk analyst. "
        "Given retrieved documents, identify and score supply-chain risks. "
        "Be precise, cite document sources, and flag confidence where data is sparse. "
        "Always return structured JSON. Do not hallucinate metrics not present in context."
    ),
    output_schema={
        "risk_summary": "string — 2-3 sentence executive summary",
        "risks": [
            {
                "category": "string (e.g. single_source | geopolitical | lead_time | quality | capacity)",
                "description": "string",
                "severity": "low | medium | high | critical",
                "confidence": "float 0-1",
                "affected_suppliers": ["string"],
                "source_documents": ["string"],
            }
        ],
        "overall_risk_score": "float 0-10",
        "recommended_actions": ["string"],
        "data_gaps": ["string — fields or suppliers with insufficient data"],
    },
    required_metadata_fields=["supplier"],
)

_INVENTORY_PACK = ReasoningPack(
    name="inventory",
    description="Inventory policy analysis — reorder points, safety stock, EOQ, ABC classification.",
    system_prompt=(
        "You are an inventory optimization specialist. "
        "Analyse retrieved supply-chain documents to evaluate inventory levels, "
        "reorder policies, and carrying costs. "
        "Provide quantitative recommendations where data permits. "
        "Always return structured JSON."
    ),
    output_schema={
        "inventory_summary": "string — executive summary",
        "sku_analyses": [
            {
                "sku_or_category": "string",
                "current_stock_level": "string or null",
                "reorder_point_recommendation": "string or null",
                "safety_stock_recommendation": "string or null",
                "eoq_estimate": "string or null",
                "abc_class": "A | B | C | unknown",
                "risk_of_stockout": "low | medium | high | unknown",
                "source_documents": ["string"],
            }
        ],
        "policy_gaps": ["string"],
        "recommended_actions": ["string"],
    },
    required_metadata_fields=["doc_type"],
)

_SUPPLIER_PACK = ReasoningPack(
    name="supplier",
    description="Supplier reliability scorecard — on-time delivery, defect rate, lead-time trend.",
    system_prompt=(
        "You are a supplier performance analyst. "
        "Using retrieved supplier documents and notes, produce a reliability scorecard. "
        "Score dimensions 0-10 where 10 is best. "
        "Cite sources and flag missing KPIs explicitly. "
        "Always return structured JSON."
    ),
    output_schema={
        "supplier_name": "string",
        "scorecard": {
            "on_time_delivery": "float 0-10 or null",
            "defect_rate_score": "float 0-10 or null",
            "lead_time_consistency": "float 0-10 or null",
            "responsiveness": "float 0-10 or null",
            "overall_score": "float 0-10 or null",
        },
        "trend": "improving | stable | deteriorating | insufficient_data",
        "key_findings": ["string"],
        "red_flags": ["string"],
        "recommended_actions": ["string"],
        "source_documents": ["string"],
        "missing_kpis": ["string"],
    },
    required_metadata_fields=["supplier"],
)

_LEAD_TIME_PACK = ReasoningPack(
    name="lead_time",
    description="Lead-time volatility assessment — buffer recommendations, trend analysis.",
    system_prompt=(
        "You are a supply chain planning specialist focused on lead-time analysis. "
        "Assess lead-time data from retrieved documents: identify variability patterns, "
        "recommend safety buffers, and flag disruption risks. "
        "Always return structured JSON."
    ),
    output_schema={
        "lead_time_summary": "string",
        "assessments": [
            {
                "supplier_or_route": "string",
                "average_lead_time": "string or null",
                "variability": "low | medium | high | unknown",
                "trend": "shortening | stable | lengthening | unknown",
                "recommended_buffer_days": "int or null",
                "disruption_risk": "low | medium | high | unknown",
                "source_documents": ["string"],
            }
        ],
        "overall_volatility": "low | medium | high | critical",
        "recommended_actions": ["string"],
    },
    required_metadata_fields=["supplier", "date_period"],
)

# ── Registry ─────────────────────────────────────────────────────────────────

_PACKS: dict[str, ReasoningPack] = {
    "risk": _RISK_PACK,
    "inventory": _INVENTORY_PACK,
    "supplier": _SUPPLIER_PACK,
    "lead_time": _LEAD_TIME_PACK,
}


def get_pack(name: str) -> ReasoningPack:
    """Return a reasoning pack by name. Raises KeyError if not found."""
    if name not in _PACKS:
        raise KeyError(f"Unknown reasoning pack '{name}'. Available: {list(_PACKS)}")
    return _PACKS[name]


def list_packs() -> list[dict]:
    """Return summary metadata for all available packs."""
    return [
        {
            "name": p.name,
            "description": p.description,
            "required_metadata_fields": p.required_metadata_fields,
            "output_schema_keys": list(p.output_schema.keys()),
        }
        for p in _PACKS.values()
    ]
