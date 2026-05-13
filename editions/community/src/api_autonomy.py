"""Autonomous copilot APIs: monitoring agents, action planning, and optimizers."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from src.action_executor import execute_action, list_executions
from src.autonomy import propose_actions, recommend_cost_performance_plan, run_monitoring_agents
from src.metrics import snapshot_metrics

router = APIRouter(prefix="/api/autonomy", tags=["autonomy"])


class MonitorRequest(BaseModel):
    disruption_events: int = 0
    demand_deviation_pct: float = 0.0


class OptimizerRequest(BaseModel):
    latency_budget_ms: float
    quality_target: float
    cache_hit_rate: float = 0.0


class ExecuteActionRequest(BaseModel):
    action: dict
    approved: bool = False


@router.post("/monitor/run")
async def run_monitor(body: MonitorRequest) -> dict:
    from src.main import settings

    snapshot = snapshot_metrics(settings.app_name, settings.app_version)
    signals = run_monitoring_agents(
        snapshot,
        disruption_events=body.disruption_events,
        demand_deviation_pct=body.demand_deviation_pct,
    )
    return {
        "signals": [
            {
                "signal_type": s.signal_type,
                "severity": s.severity,
                "details": s.details,
            }
            for s in signals
        ],
        "count": len(signals),
    }


@router.post("/actions/propose")
async def propose(monitor: MonitorRequest) -> dict:
    from src.main import settings

    snapshot = snapshot_metrics(settings.app_name, settings.app_version)
    signals = run_monitoring_agents(
        snapshot,
        disruption_events=monitor.disruption_events,
        demand_deviation_pct=monitor.demand_deviation_pct,
    )
    return {"actions": propose_actions(signals), "count": len(signals)}


@router.post("/actions/execute")
async def execute(body: ExecuteActionRequest) -> dict:
    result = execute_action(body.action, approved=body.approved)
    return {"status": result.get("status"), "execution": result}


@router.get("/actions/executions")
async def executions(limit: int = 100) -> dict:
    return {"executions": list_executions(limit=limit)}


@router.post("/optimizer/recommend")
async def optimizer(body: OptimizerRequest) -> dict:
    return recommend_cost_performance_plan(
        latency_budget_ms=body.latency_budget_ms,
        quality_target=body.quality_target,
        cache_hit_rate=body.cache_hit_rate,
    )
