"""
Agentic workflow runner — multi-step supply chain intelligence plans.

Workflows are sequences of named steps. Each step either:
  - runs a RAG query (with optional reasoning pack)
  - runs a scenario analysis
  - synthesises previous step outputs into a conclusion

The runner executes steps sequentially, passing the accumulated context from
prior steps into the next prompt so reasoning builds incrementally.

Built-in workflow templates
---------------------------
- investigate_anomaly    → detect root cause of a supply chain anomaly
- weekly_risk_summary    → synthesise weekly supplier / inventory risk
- propose_mitigations    → generate ranked mitigation actions for identified risks
- supplier_onboarding    → due-diligence checklist evaluation for a new supplier

Design
------
- Each workflow yields a WorkflowRun containing per-step results + final synthesis
- Steps are designed to be resumable: a failed step records the error and the run
  continues with subsequent steps that don't depend on it
- In offline mode the runner returns plausible stub answers for all steps
- All runs are stored in data/workflow_runs.json for audit / HITL review

Usage::

    from src.agent_runner import AgentRunner, WorkflowRequest

    runner = AgentRunner(rag_pipeline, settings)
    run = runner.execute(WorkflowRequest(
        workflow="investigate_anomaly",
        context={"anomaly": "Q3 stockout for SKU-4892 at Warehouse EU-3"},
        filters={"supplier": "Ningbo Electronics"},
    ))
    print(run.synthesis)
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_RUN_STORE = Path("data/workflow_runs.json")


# ── Workflow templates ────────────────────────────────────────────────────────

@dataclass
class WorkflowStep:
    name: str
    description: str
    prompt_template: str   # {context_vars} + {prior_results} placeholders
    pack: Optional[str] = None   # reasoning pack name to overlay, or None


_WORKFLOW_TEMPLATES: dict[str, dict] = {
    "investigate_anomaly": {
        "description": "Root-cause investigation of a supply chain anomaly.",
        "required_context": ["anomaly"],
        "steps": [
            WorkflowStep(
                name="retrieve_relevant_history",
                description="Pull relevant historical documents for the anomaly.",
                prompt_template=(
                    "Retrieve and summarise all supply chain documents relevant to this anomaly:\n"
                    "{anomaly}\n"
                    "Focus on: historical patterns, supplier notes, demand forecasts, inventory levels."
                ),
            ),
            WorkflowStep(
                name="identify_root_causes",
                description="Identify probable root causes from retrieved data.",
                prompt_template=(
                    "Given this anomaly: {anomaly}\n\n"
                    "And the following evidence:\n{retrieve_relevant_history}\n\n"
                    "List the top 3 probable root causes, each with supporting evidence and confidence (0-1)."
                ),
            ),
            WorkflowStep(
                name="assess_downstream_impact",
                description="Estimate downstream impact on inventory, customers, and costs.",
                prompt_template=(
                    "Anomaly: {anomaly}\n"
                    "Root causes identified:\n{identify_root_causes}\n\n"
                    "Assess downstream impact: inventory shortfall, customer service level risk, "
                    "estimated cost exposure, and affected SKUs or regions."
                ),
            ),
            WorkflowStep(
                name="synthesise_findings",
                description="Produce an executive briefing with recommended actions.",
                prompt_template=(
                    "Produce a concise executive briefing for this anomaly: {anomaly}\n\n"
                    "Evidence summary:\n{retrieve_relevant_history}\n\n"
                    "Root causes:\n{identify_root_causes}\n\n"
                    "Impact:\n{assess_downstream_impact}\n\n"
                    "Include: situation summary, top 3 root causes, impact estimate, "
                    "and 3–5 prioritised recommended actions."
                ),
            ),
        ],
    },
    "weekly_risk_summary": {
        "description": "Synthesise weekly supplier and inventory risk for planning review.",
        "required_context": ["date_period"],
        "steps": [
            WorkflowStep(
                name="scan_supplier_risks",
                description="Identify current supplier risks.",
                prompt_template=(
                    "For period {date_period}: scan all available supplier documents and identify "
                    "current risks: lead-time changes, quality issues, capacity constraints, financial signals."
                ),
                pack="risk",
            ),
            WorkflowStep(
                name="scan_inventory_risks",
                description="Identify inventory policy gaps and stockout risks.",
                prompt_template=(
                    "For period {date_period}: review inventory levels and policies. "
                    "Identify: items below safety stock, reorder alerts, slow-moving items, and ABC misalignments."
                ),
                pack="inventory",
            ),
            WorkflowStep(
                name="lead_time_volatility",
                description="Assess lead-time volatility across the supply base.",
                prompt_template=(
                    "For period {date_period}: analyse lead-time data across all suppliers. "
                    "Identify trends, outliers, and items at risk due to lead-time variability."
                ),
                pack="lead_time",
            ),
            WorkflowStep(
                name="weekly_synthesis",
                description="Consolidated weekly risk summary for planning review.",
                prompt_template=(
                    "Date period: {date_period}\n\n"
                    "Supplier risks:\n{scan_supplier_risks}\n\n"
                    "Inventory risks:\n{scan_inventory_risks}\n\n"
                    "Lead-time volatility:\n{lead_time_volatility}\n\n"
                    "Produce a 1-page weekly supply chain risk summary. Include: top 5 risks ranked by severity, "
                    "items requiring immediate action, and a 30-day outlook."
                ),
            ),
        ],
    },
    "propose_mitigations": {
        "description": "Generate ranked mitigation actions for a set of identified risks.",
        "required_context": ["risk_description"],
        "steps": [
            WorkflowStep(
                name="retrieve_mitigation_context",
                description="Pull relevant policies, contracts, and historical mitigations.",
                prompt_template=(
                    "Retrieve supply chain policies, contracts, and past mitigation actions "
                    "relevant to these risks:\n{risk_description}"
                ),
            ),
            WorkflowStep(
                name="generate_options",
                description="Generate a long-list of mitigation options.",
                prompt_template=(
                    "For these supply chain risks:\n{risk_description}\n\n"
                    "Using relevant context:\n{retrieve_mitigation_context}\n\n"
                    "Generate 5–10 potential mitigation actions. For each, describe: "
                    "the action, expected benefit, implementation effort (low/medium/high), "
                    "and time-to-impact (immediate/1-4 weeks/1-3 months)."
                ),
            ),
            WorkflowStep(
                name="rank_and_recommend",
                description="Rank options by impact/effort and produce a final recommendation.",
                prompt_template=(
                    "Risks: {risk_description}\n\n"
                    "Mitigation options:\n{generate_options}\n\n"
                    "Rank all options by impact-to-effort ratio. Select the top 3 for immediate action "
                    "and provide implementation guidance for each. Flag any actions requiring senior approval."
                ),
            ),
        ],
    },
    "supplier_onboarding": {
        "description": "Due-diligence checklist evaluation for onboarding a new supplier.",
        "required_context": ["supplier_name"],
        "steps": [
            WorkflowStep(
                name="document_scan",
                description="Scan all available documents for the supplier.",
                prompt_template=(
                    "Search all available documents for supplier '{supplier_name}'. "
                    "Summarise: what information is available and what is missing."
                ),
                pack="supplier",
            ),
            WorkflowStep(
                name="risk_assessment",
                description="Perform initial risk assessment for the new supplier.",
                prompt_template=(
                    "Based on available information about '{supplier_name}':\n{document_scan}\n\n"
                    "Assess onboarding risks: financial stability signals, quality history, "
                    "geographic/geopolitical exposure, capacity fit, and ESG flags."
                ),
                pack="risk",
            ),
            WorkflowStep(
                name="due_diligence_checklist",
                description="Generate a due-diligence checklist with pass/fail/unknown status.",
                prompt_template=(
                    "Supplier: {supplier_name}\n"
                    "Document scan:\n{document_scan}\n"
                    "Risk assessment:\n{risk_assessment}\n\n"
                    "Generate a due-diligence checklist covering: "
                    "legal entity verification, quality certifications, financial references, "
                    "capacity confirmation, lead-time commitments, insurance, ESG compliance, "
                    "and backup sourcing. Mark each item: PASS | FAIL | INSUFFICIENT_DATA. "
                    "List blocking items that must be resolved before onboarding."
                ),
            ),
        ],
    },
}


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class StepResult:
    step_name: str
    description: str
    output: str
    sources: list[dict] = field(default_factory=list)
    error: Optional[str] = None
    duration_ms: float = 0.0


@dataclass
class WorkflowRun:
    run_id: str
    workflow: str
    context: dict[str, Any]
    status: str                      # running | completed | partial | failed
    steps: list[StepResult]
    synthesis: str                   # final step output or summary
    started_at: str
    completed_at: Optional[str] = None
    offline_mode: bool = False


@dataclass
class WorkflowRequest:
    workflow: str
    context: dict[str, Any]
    filters: dict[str, str] = field(default_factory=dict)
    top_k: int = 6
    rerank_strategy: str = "default"


# ── Runner ────────────────────────────────────────────────────────────────────

class AgentRunner:
    """Executes multi-step supply chain intelligence workflows."""

    def __init__(self, rag_pipeline, settings) -> None:
        self._rag = rag_pipeline
        self._settings = settings

    def list_workflows(self) -> list[dict]:
        return [
            {
                "workflow": k,
                "description": v["description"],
                "required_context": v["required_context"],
                "steps": [s.name for s in v["steps"]],
            }
            for k, v in _WORKFLOW_TEMPLATES.items()
        ]

    def execute(self, request: WorkflowRequest) -> WorkflowRun:
        """Execute a workflow and return a WorkflowRun with all step outputs."""
        template = _WORKFLOW_TEMPLATES.get(request.workflow)
        if not template:
            raise ValueError(
                f"Unknown workflow '{request.workflow}'. "
                f"Available: {list(_WORKFLOW_TEMPLATES)}"
            )

        # Validate required context keys
        missing = [k for k in template["required_context"] if k not in request.context]
        if missing:
            raise ValueError(f"Missing required context keys for '{request.workflow}': {missing}")

        run = WorkflowRun(
            run_id=str(uuid.uuid4()),
            workflow=request.workflow,
            context=request.context,
            status="running",
            steps=[],
            synthesis="",
            started_at=datetime.now(timezone.utc).isoformat(),
            offline_mode=self._rag.offline_mode,
        )

        accumulated: dict[str, str] = dict(request.context)

        for step in template["steps"]:
            result = self._run_step(step, accumulated, request)
            run.steps.append(result)
            if result.error:
                # Record error but keep going with subsequent independent steps
                accumulated[step.name] = f"[ERROR: {result.error}]"
            else:
                accumulated[step.name] = result.output

        # The last step's output is the synthesis
        run.synthesis = accumulated.get(template["steps"][-1].name, "")
        run.status = "partial" if any(s.error for s in run.steps) else "completed"
        run.completed_at = datetime.now(timezone.utc).isoformat()

        _persist_run(run)
        return run

    def get_run(self, run_id: str) -> Optional[WorkflowRun]:
        """Retrieve a persisted run by ID."""
        data = _load_runs()
        record = data.get(run_id)
        if not record:
            return None
        return _deserialise_run(record)

    def list_runs(self, workflow: Optional[str] = None, limit: int = 50) -> list[dict]:
        """List recent workflow runs, optionally filtered by workflow name."""
        data = _load_runs()
        runs = sorted(data.values(), key=lambda r: r.get("started_at", ""), reverse=True)
        if workflow:
            runs = [r for r in runs if r.get("workflow") == workflow]
        return runs[:limit]

    # ── step execution ─────────────────────────────────────────────────────

    def _run_step(
        self,
        step: WorkflowStep,
        accumulated: dict[str, str],
        request: WorkflowRequest,
    ) -> StepResult:
        import time

        t0 = time.monotonic()
        try:
            # Render prompt — substitute context vars and prior step outputs
            try:
                prompt = step.prompt_template.format(**accumulated)
            except KeyError as e:
                return StepResult(
                    step_name=step.name,
                    description=step.description,
                    output="",
                    error=f"Template variable not found: {e}",
                )

            if self._rag.offline_mode:
                output = (
                    f"[OFFLINE] Step '{step.name}': {step.description}. "
                    "Activate OpenAI API key for real analysis."
                )
                return StepResult(
                    step_name=step.name,
                    description=step.description,
                    output=output,
                    duration_ms=(time.monotonic() - t0) * 1000,
                )

            raw = self._rag.query(
                query_text=prompt,
                top_k=request.top_k,
                filters=request.filters or None,
                rerank_strategy=request.rerank_strategy,
            )
            return StepResult(
                step_name=step.name,
                description=step.description,
                output=raw.get("answer", ""),
                sources=raw.get("sources", []),
                duration_ms=(time.monotonic() - t0) * 1000,
            )
        except Exception as e:
            logger.error(f"Workflow step '{step.name}' failed: {e}")
            return StepResult(
                step_name=step.name,
                description=step.description,
                output="",
                error=str(e),
                duration_ms=(time.monotonic() - t0) * 1000,
            )


# ── persistence ───────────────────────────────────────────────────────────────

def _load_runs() -> dict:
    if _RUN_STORE.exists():
        try:
            return json.loads(_RUN_STORE.read_text())
        except Exception:
            return {}
    return {}


def _persist_run(run: WorkflowRun) -> None:
    data = _load_runs()
    data[run.run_id] = {
        "run_id": run.run_id,
        "workflow": run.workflow,
        "context": run.context,
        "status": run.status,
        "steps": [
            {
                "step_name": s.step_name,
                "description": s.description,
                "output": s.output,
                "sources": s.sources,
                "error": s.error,
                "duration_ms": s.duration_ms,
            }
            for s in run.steps
        ],
        "synthesis": run.synthesis,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "offline_mode": run.offline_mode,
    }
    _RUN_STORE.parent.mkdir(parents=True, exist_ok=True)
    _RUN_STORE.write_text(json.dumps(data, indent=2))


def _deserialise_run(record: dict) -> WorkflowRun:
    return WorkflowRun(
        run_id=record["run_id"],
        workflow=record["workflow"],
        context=record["context"],
        status=record["status"],
        steps=[
            StepResult(
                step_name=s["step_name"],
                description=s["description"],
                output=s["output"],
                sources=s.get("sources", []),
                error=s.get("error"),
                duration_ms=s.get("duration_ms", 0.0),
            )
            for s in record.get("steps", [])
        ],
        synthesis=record.get("synthesis", ""),
        started_at=record["started_at"],
        completed_at=record.get("completed_at"),
        offline_mode=record.get("offline_mode", False),
    )
