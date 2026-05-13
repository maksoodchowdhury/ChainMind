"""
Scenario analysis engine — what-if simulations for supply chain planning.

Runs structured scenarios against the RAG knowledge base and returns:
- Projected outcomes with confidence intervals
- Impact scores across supply chain dimensions
- Recommendation rationale with cited evidence

Scenarios are parameterised templates that combine a base question with
variable substitutions (e.g. "demand +20%", "lead-time +30 days").

Design
------
- Each scenario template defines a prompt structure and output schema
- The engine retrieves relevant context via RAG then structures the LLM output
- In offline mode (no OpenAI key) a deterministic placeholder response is
  returned so tests and CI always run without secrets

Usage::

    from src.scenario_engine import ScenarioEngine, ScenarioRequest

    engine = ScenarioEngine(rag_pipeline, settings)
    result = engine.run(ScenarioRequest(
        scenario_type="demand_surge",
        variables={"change_pct": 20, "product_category": "electronics"},
        filters={"supplier": "Ningbo Electronics"},
    ))
    print(result.impact_score)   # float 0-10
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Scenario templates ────────────────────────────────────────────────────────

_SCENARIO_TEMPLATES: dict[str, dict] = {
    "demand_surge": {
        "description": "Model the impact of a sudden demand increase.",
        "variables": {"change_pct": "int — demand increase percentage", "product_category": "str"},
        "prompt": (
            "Analyse what would happen if demand for {product_category} increased by {change_pct}%. "
            "Using the supply chain documents below, assess: inventory adequacy, supplier capacity, "
            "lead-time impact, stockout risk, and required mitigation actions."
        ),
    },
    "supplier_failure": {
        "description": "Assess the impact of a key supplier going offline.",
        "variables": {"supplier_name": "str", "outage_weeks": "int"},
        "prompt": (
            "Simulate the scenario where supplier '{supplier_name}' becomes unavailable for "
            "{outage_weeks} weeks. Using the supply chain documents, assess: affected SKUs, "
            "alternative sourcing options, inventory runway, cost impact, and recovery timeline."
        ),
    },
    "lead_time_increase": {
        "description": "Evaluate the ripple effect of a lead-time extension.",
        "variables": {"supplier_name": "str", "extra_days": "int"},
        "prompt": (
            "Analyse the supply chain impact if '{supplier_name}' increases lead time by {extra_days} days. "
            "Assess: safety stock adequacy, reorder point adjustments, service level risk, "
            "cash flow impact, and recommended buffer strategy."
        ),
    },
    "cost_pressure": {
        "description": "Model the effect of a cost increase on total supply chain economics.",
        "variables": {"cost_increase_pct": "int", "category": "str"},
        "prompt": (
            "Evaluate the impact of a {cost_increase_pct}% cost increase in {category}. "
            "Using available documents, assess: total landed cost impact, alternative sourcing, "
            "make-vs-buy implications, margin erosion, and recommended negotiation levers."
        ),
    },
    "custom": {
        "description": "Free-form what-if scenario.",
        "variables": {"question": "str — the what-if question"},
        "prompt": "{question}",
    },
}

# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class ScenarioRequest:
    scenario_type: str
    variables: dict[str, Any]
    filters: dict[str, str] = field(default_factory=dict)
    top_k: int = 8
    rerank_strategy: str = "default"


@dataclass
class ScenarioOutcome:
    """A single projected outcome within the scenario."""
    dimension: str        # e.g. "stockout_risk", "lead_time_impact"
    assessment: str       # qualitative description
    severity: str         # low | medium | high | critical
    confidence: float     # 0.0–1.0
    evidence: list[str]   # cited source snippets or document names


@dataclass
class ScenarioResult:
    scenario_type: str
    variables: dict[str, Any]
    narrative: str                       # executive summary
    outcomes: list[ScenarioOutcome]
    impact_score: float                  # 0–10, aggregate severity
    confidence_interval: tuple[float, float]  # (low, high) impact estimates
    recommended_actions: list[str]
    sources: list[dict]
    ran_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    offline_mode: bool = False


# ── Engine ────────────────────────────────────────────────────────────────────

class ScenarioEngine:
    """Runs structured what-if scenarios against the RAG knowledge base."""

    def __init__(self, rag_pipeline, settings) -> None:
        self._rag = rag_pipeline
        self._settings = settings

    # ── public interface ──────────────────────────────────────────────────────

    def list_scenarios(self) -> list[dict]:
        return [
            {"type": k, "description": v["description"], "variables": v["variables"]}
            for k, v in _SCENARIO_TEMPLATES.items()
        ]

    def run(self, request: ScenarioRequest) -> ScenarioResult:
        """Execute a scenario and return a structured result."""
        template = _SCENARIO_TEMPLATES.get(request.scenario_type)
        if not template:
            raise ValueError(
                f"Unknown scenario type '{request.scenario_type}'. "
                f"Available: {list(_SCENARIO_TEMPLATES)}"
            )

        try:
            question = template["prompt"].format(**request.variables)
        except KeyError as e:
            raise ValueError(f"Missing required variable {e} for scenario '{request.scenario_type}'")

        # Build the full structured prompt
        system_overlay = (
            "You are a supply chain scenario analyst. "
            "Given retrieved documents, analyse the described scenario. "
            "Return a JSON object with exactly these keys: "
            "narrative (str), outcomes (list of objects with keys: dimension, assessment, "
            "severity, confidence, evidence), impact_score (float 0-10), "
            "confidence_interval (list of [low, high] floats), recommended_actions (list of str). "
            "Base ALL claims on the retrieved context. Do not hallucinate figures."
        )

        augmented_question = f"[SCENARIO ANALYSIS]\n{system_overlay}\n\n{question}"

        if self._rag.offline_mode:
            return self._offline_result(request, question)

        try:
            raw = self._rag.query(
                query_text=augmented_question,
                top_k=request.top_k,
                filters=request.filters or None,
                rerank_strategy=request.rerank_strategy,
            )
            return self._parse_result(request, raw)
        except Exception as e:
            logger.error(f"Scenario run failed: {e}")
            raise

    # ── parsing ───────────────────────────────────────────────────────────────

    def _parse_result(self, request: ScenarioRequest, raw: dict) -> ScenarioResult:
        """Parse the LLM response into a ScenarioResult."""
        answer_text = raw.get("answer", "")
        sources = raw.get("sources", [])

        # Try to extract JSON from the LLM response
        parsed = _extract_json(answer_text)

        outcomes = [
            ScenarioOutcome(
                dimension=o.get("dimension", "unknown"),
                assessment=o.get("assessment", ""),
                severity=o.get("severity", "medium"),
                confidence=float(o.get("confidence", 0.5)),
                evidence=o.get("evidence", []),
            )
            for o in parsed.get("outcomes", [])
        ]

        ci_raw = parsed.get("confidence_interval", [0.0, 10.0])
        ci = (float(ci_raw[0]), float(ci_raw[1])) if isinstance(ci_raw, list) and len(ci_raw) == 2 else (0.0, 10.0)

        return ScenarioResult(
            scenario_type=request.scenario_type,
            variables=request.variables,
            narrative=parsed.get("narrative", answer_text[:500]),
            outcomes=outcomes,
            impact_score=float(parsed.get("impact_score", 5.0)),
            confidence_interval=ci,
            recommended_actions=parsed.get("recommended_actions", []),
            sources=sources,
        )

    def _offline_result(self, request: ScenarioRequest, question: str) -> ScenarioResult:
        """Return a deterministic stub when no OpenAI key is configured."""
        return ScenarioResult(
            scenario_type=request.scenario_type,
            variables=request.variables,
            narrative=(
                f"[OFFLINE MODE] Scenario '{request.scenario_type}' analysis for: {question[:120]}. "
                "Connect an OpenAI API key to receive real analysis."
            ),
            outcomes=[
                ScenarioOutcome(
                    dimension="availability",
                    assessment="Insufficient data in offline mode.",
                    severity="medium",
                    confidence=0.0,
                    evidence=[],
                )
            ],
            impact_score=5.0,
            confidence_interval=(2.0, 8.0),
            recommended_actions=["Configure OpenAI API key to enable full scenario analysis."],
            sources=[],
            offline_mode=True,
        )


# ── helpers ───────────────────────────────────────────────────────────────────

def _extract_json(text: str) -> dict:
    """Try to pull a JSON object out of an LLM response string."""
    # Look for a fenced JSON block first
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1))
        except json.JSONDecodeError:
            pass
    # Try parsing the whole response as JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Find the first {...} block in the text
    brace = re.search(r"\{.*\}", text, re.DOTALL)
    if brace:
        try:
            return json.loads(brace.group())
        except json.JSONDecodeError:
            pass
    return {}
