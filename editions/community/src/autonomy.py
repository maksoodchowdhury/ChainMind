"""Autonomous monitoring agents and policy-driven action planning."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.metrics import evaluate_slo_status
from src.policy_engine import load_policies


@dataclass
class MonitoringSignal:
    signal_type: str
    severity: float
    details: dict


def run_monitoring_agents(snapshot: dict, *, disruption_events: int = 0, demand_deviation_pct: float = 0.0) -> list[MonitoringSignal]:
    signals: list[MonitoringSignal] = []

    slo = evaluate_slo_status(
        snapshot,
        error_rate_threshold=0.01,
        p95_latency_ms_threshold=800.0,
        minimum_requests=20,
    )
    if slo["status"] == "breached":
        severity = 7.5 if slo["breaches"].get("error_rate") else 6.0
        signals.append(MonitoringSignal("service_slo_breach", severity, slo))

    if disruption_events > 0:
        sev = min(10.0, 2.0 + (disruption_events * 1.2))
        signals.append(MonitoringSignal("supplier_disruption_spike", sev, {"disruption_events": disruption_events}))

    if abs(demand_deviation_pct) >= 10.0:
        sev = min(10.0, 3.0 + (abs(demand_deviation_pct) / 10.0))
        signals.append(MonitoringSignal("demand_deviation", sev, {"demand_deviation_pct": demand_deviation_pct}))

    return signals


def propose_actions(signals: list[MonitoringSignal], *, policy_file: str | None = None) -> list[dict]:
    policies = load_policies(policy_file)
    auto = policies.get("autonomous_actions", {})
    notify_t = float(auto.get("notify_threshold", 3.0))
    ticket_t = float(auto.get("ticket_threshold", 6.0))
    auto_exec_t = float(auto.get("auto_execute_threshold", 2.0))

    actions: list[dict] = []
    for s in signals:
        if s.severity < auto_exec_t:
            continue
        if s.severity >= ticket_t:
            action = "create_ticket"
            approval_required = True
        elif s.severity >= notify_t:
            action = "notify"
            approval_required = False
        else:
            action = "suggest_reallocation"
            approval_required = True
        actions.append(
            {
                "signal_type": s.signal_type,
                "severity": s.severity,
                "action": action,
                "approval_required": approval_required,
                "details": s.details,
                "proposed_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    return actions


def recommend_cost_performance_plan(*, latency_budget_ms: float, quality_target: float, cache_hit_rate: float = 0.0) -> dict:
    """Recommend model/retriever/cache settings for a budget target."""
    if latency_budget_ms <= 400:
        model_tier = "fast"
        rerank = "off"
    elif latency_budget_ms <= 900:
        model_tier = "balanced"
        rerank = "default"
    else:
        model_tier = "quality"
        rerank = "cross_encoder"

    if quality_target >= 0.85:
        retrieval_top_k = 8
    elif quality_target >= 0.75:
        retrieval_top_k = 6
    else:
        retrieval_top_k = 4

    cache_strategy = "aggressive" if cache_hit_rate < 0.3 else "normal"
    return {
        "recommended_model_tier": model_tier,
        "rerank_strategy": rerank,
        "top_k": retrieval_top_k,
        "cache_strategy": cache_strategy,
        "estimated_cost_per_1000_queries_usd": {
            "fast": 2.5,
            "balanced": 5.0,
            "quality": 9.0,
        }[model_tier],
    }
