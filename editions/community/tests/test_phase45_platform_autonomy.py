from fastapi.testclient import TestClient

from src.main import app


def test_platform_tenant_quota_crud():
    client = TestClient(app)

    put_resp = client.put("/api/platform/tenants/tenant-a/quota", json={"daily": 3, "monthly": 20})
    assert put_resp.status_code == 200
    assert put_resp.json()["quota"]["daily"] == 3

    usage_resp = client.get("/api/platform/tenants/tenant-a/usage")
    assert usage_resp.status_code == 200
    payload = usage_resp.json()
    assert payload["tenant_id"] == "tenant-a"
    assert "quota" in payload


def test_platform_connectors_and_events():
    client = TestClient(app)

    cfg = client.put("/api/platform/connectors/erp", json={"enabled": True})
    assert cfg.status_code == 200
    assert cfg.json()["enabled"] is True

    sync = client.post("/api/platform/connectors/erp/sync", json={"trigger": "test"})
    assert sync.status_code == 200
    assert sync.json()["status"] == "completed"

    event = client.post(
        "/api/platform/events/webhook",
        json={"event_type": "erp.order.updated", "payload": {"order_id": "123"}},
    )
    assert event.status_code == 200
    assert event.json()["status"] == "accepted"


def test_control_plane_model_registry_and_strategy():
    client = TestClient(app)

    reg = client.post(
        "/api/platform/control-plane/models",
        json={
            "alias": "budget_chat",
            "provider": "openai",
            "model": "gpt-4o-mini",
            "active": False,
        },
    )
    assert reg.status_code == 200
    assert reg.json()["model"] == "gpt-4o-mini"

    strat = client.post(
        "/api/platform/control-plane/workload-strategy",
        json={"query_class": "risk", "model_alias": "budget_chat"},
    )
    assert strat.status_code == 200
    assert strat.json()["workload_strategy"]["risk"] == "budget_chat"


def test_autonomy_monitor_actions_optimizer():
    client = TestClient(app)

    monitor = client.post(
        "/api/autonomy/monitor/run",
        json={"disruption_events": 4, "demand_deviation_pct": 15.0},
    )
    assert monitor.status_code == 200
    assert monitor.json()["count"] >= 1

    actions = client.post(
        "/api/autonomy/actions/propose",
        json={"disruption_events": 4, "demand_deviation_pct": 15.0},
    )
    assert actions.status_code == 200
    assert isinstance(actions.json()["actions"], list)

    optimize = client.post(
        "/api/autonomy/optimizer/recommend",
        json={"latency_budget_ms": 350, "quality_target": 0.8, "cache_hit_rate": 0.2},
    )
    assert optimize.status_code == 200
    assert optimize.json()["recommended_model_tier"] in {"fast", "balanced", "quality"}


def test_platform_billing_and_chargeback():
    client = TestClient(app)

    pricing = client.put(
        "/api/platform/billing/pricing",
        json={
            "usd_per_request": 0.003,
            "usd_per_ingestion_event": 0.02,
            "usd_per_storage_doc": 0.001,
        },
    )
    assert pricing.status_code == 200
    assert pricing.json()["pricing"]["usd_per_request"] == 0.003

    report = client.get("/api/platform/billing/chargeback")
    assert report.status_code == 200
    assert "grand_total_usd" in report.json()


def test_platform_extension_framework_and_autonomy_execution():
    client = TestClient(app)

    register_tool = client.post(
        "/api/platform/extensions",
        json={
            "name": "ticket_stub",
            "ext_type": "tool",
            "description": "Create synthetic tickets",
            "entrypoint": "builtin",
        },
    )
    assert register_tool.status_code == 200
    assert register_tool.json()["type"] == "tool"

    activate = client.post(
        "/api/platform/extensions/activate",
        json={"slot": "tool", "name": "ticket_stub"},
    )
    assert activate.status_code == 200
    assert activate.json()["active"]["tool"] == "ticket_stub"

    executed = client.post(
        "/api/autonomy/actions/execute",
        json={"action": {"action": "create_ticket", "severity": 8.2}, "approved": True},
    )
    assert executed.status_code == 200
    assert executed.json()["execution"]["status"] == "executed"
    assert executed.json()["execution"]["tool_result"]["executed"] is True
