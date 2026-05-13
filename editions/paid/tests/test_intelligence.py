"""Tests for Phase 3 — Domain reasoning packs, Scenario engine, Agent runner, HITL."""

import pytest
from unittest.mock import MagicMock, patch


# ── Reasoning packs ───────────────────────────────────────────────────────────

from src.reasoning_packs import get_pack, list_packs, ReasoningPack


def test_list_packs_returns_all_four():
    packs = list_packs()
    names = {p["name"] for p in packs}
    assert names == {"risk", "inventory", "supplier", "lead_time"}


def test_get_pack_known():
    pack = get_pack("risk")
    assert isinstance(pack, ReasoningPack)
    assert pack.name == "risk"
    assert pack.system_prompt
    assert isinstance(pack.output_schema, dict)


def test_get_pack_unknown_raises():
    with pytest.raises(KeyError, match="Unknown reasoning pack"):
        get_pack("nonexistent_pack")


def test_pack_render_includes_context_and_question():
    pack = get_pack("inventory")
    rendered = pack.render("Some context text.", "What is the reorder point?")
    assert "Some context text." in rendered
    assert "What is the reorder point?" in rendered
    assert "schema" in rendered.lower()


def test_pack_output_schema_keys():
    for pack_name in ("risk", "inventory", "supplier", "lead_time"):
        pack = get_pack(pack_name)
        assert len(pack.output_schema) >= 3, f"{pack_name} schema too small"


# ── Scenario engine ───────────────────────────────────────────────────────────

from src.scenario_engine import ScenarioEngine, ScenarioRequest, _extract_json


def _mock_rag(offline=True):
    rag = MagicMock()
    rag.offline_mode = offline
    rag.query.return_value = {
        "query": "test",
        "answer": '{"narrative": "test narrative", "outcomes": [], "impact_score": 3.5, "confidence_interval": [2.0, 5.0], "recommended_actions": ["action 1"]}',
        "sources": [],
    }
    return rag


def test_list_scenarios():
    engine = ScenarioEngine(_mock_rag(), MagicMock())
    scenarios = engine.list_scenarios()
    types = {s["type"] for s in scenarios}
    assert "demand_surge" in types
    assert "supplier_failure" in types
    assert "lead_time_increase" in types
    assert "cost_pressure" in types
    assert "custom" in types


def test_run_scenario_offline_mode():
    engine = ScenarioEngine(_mock_rag(offline=True), MagicMock())
    result = engine.run(ScenarioRequest(
        scenario_type="demand_surge",
        variables={"change_pct": 20, "product_category": "electronics"},
    ))
    assert result.offline_mode is True
    assert result.scenario_type == "demand_surge"
    assert result.impact_score == 5.0
    assert len(result.outcomes) >= 1


def test_run_scenario_online_mode():
    rag = _mock_rag(offline=False)
    engine = ScenarioEngine(rag, MagicMock())
    result = engine.run(ScenarioRequest(
        scenario_type="supplier_failure",
        variables={"supplier_name": "Acme Corp", "outage_weeks": 4},
    ))
    assert result.scenario_type == "supplier_failure"
    assert result.narrative == "test narrative"
    assert result.impact_score == pytest.approx(3.5)
    assert result.recommended_actions == ["action 1"]


def test_run_scenario_unknown_type():
    engine = ScenarioEngine(_mock_rag(), MagicMock())
    with pytest.raises(ValueError, match="Unknown scenario type"):
        engine.run(ScenarioRequest(scenario_type="magic_wand", variables={}))


def test_run_scenario_missing_variable():
    engine = ScenarioEngine(_mock_rag(), MagicMock())
    with pytest.raises(ValueError, match="Missing required variable"):
        engine.run(ScenarioRequest(
            scenario_type="demand_surge",
            variables={"change_pct": 10},  # missing product_category
        ))


def test_run_custom_scenario():
    engine = ScenarioEngine(_mock_rag(offline=True), MagicMock())
    result = engine.run(ScenarioRequest(
        scenario_type="custom",
        variables={"question": "What if shipping costs double?"},
    ))
    assert result.scenario_type == "custom"


def test_extract_json_fenced():
    text = 'Some text\n```json\n{"key": "value"}\n```\nmore text'
    assert _extract_json(text) == {"key": "value"}


def test_extract_json_bare():
    assert _extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_no_json():
    assert _extract_json("plain text with no json") == {}


# ── Agent runner ──────────────────────────────────────────────────────────────

from src.agent_runner import AgentRunner, WorkflowRequest


def test_list_workflows():
    runner = AgentRunner(_mock_rag(), MagicMock())
    workflows = runner.list_workflows()
    names = {w["workflow"] for w in workflows}
    assert "investigate_anomaly" in names
    assert "weekly_risk_summary" in names
    assert "propose_mitigations" in names
    assert "supplier_onboarding" in names


def test_execute_workflow_offline():
    runner = AgentRunner(_mock_rag(offline=True), MagicMock())
    run = runner.execute(WorkflowRequest(
        workflow="investigate_anomaly",
        context={"anomaly": "Stockout on SKU-123 at Warehouse EU-2"},
    ))
    assert run.status in ("completed", "partial")
    assert run.workflow == "investigate_anomaly"
    assert len(run.steps) == 4
    assert run.synthesis


def test_execute_workflow_unknown():
    runner = AgentRunner(_mock_rag(), MagicMock())
    with pytest.raises(ValueError, match="Unknown workflow"):
        runner.execute(WorkflowRequest(workflow="unknown_wf", context={}))


def test_execute_workflow_missing_context():
    runner = AgentRunner(_mock_rag(), MagicMock())
    with pytest.raises(ValueError, match="Missing required context"):
        runner.execute(WorkflowRequest(
            workflow="investigate_anomaly",
            context={},  # missing "anomaly"
        ))


def test_execute_workflow_persisted(tmp_path, monkeypatch):
    import src.agent_runner as ar
    monkeypatch.setattr(ar, "_RUN_STORE", tmp_path / "runs.json")
    runner = AgentRunner(_mock_rag(offline=True), MagicMock())
    run = runner.execute(WorkflowRequest(
        workflow="investigate_anomaly",
        context={"anomaly": "Test anomaly"},
    ))
    retrieved = runner.get_run(run.run_id)
    assert retrieved is not None
    assert retrieved.run_id == run.run_id


def test_get_run_not_found(tmp_path, monkeypatch):
    import src.agent_runner as ar
    monkeypatch.setattr(ar, "_RUN_STORE", tmp_path / "runs.json")
    runner = AgentRunner(_mock_rag(), MagicMock())
    assert runner.get_run("nonexistent-id") is None


def test_list_runs_with_filter(tmp_path, monkeypatch):
    import src.agent_runner as ar
    monkeypatch.setattr(ar, "_RUN_STORE", tmp_path / "runs.json")
    runner = AgentRunner(_mock_rag(offline=True), MagicMock())
    runner.execute(WorkflowRequest(workflow="investigate_anomaly", context={"anomaly": "A1"}))
    runner.execute(WorkflowRequest(workflow="propose_mitigations", context={"risk_description": "R1"}))
    anomaly_runs = runner.list_runs(workflow="investigate_anomaly")
    assert all(r["workflow"] == "investigate_anomaly" for r in anomaly_runs)


# ── HITL queue ────────────────────────────────────────────────────────────────

from src.hitl import HITLQueue, ReviewRequest, ReviewDecision


@pytest.fixture
def queue(tmp_path, monkeypatch):
    import src.hitl as hitl_module
    monkeypatch.setattr(hitl_module, "_REVIEW_STORE", tmp_path / "reviews.json")
    return HITLQueue()


def test_submit_creates_pending_item(queue):
    item = queue.submit(ReviewRequest(
        source_type="workflow_run",
        source_id="run-abc",
        title="Weekly Risk Summary",
        content="Some AI-generated content.",
        submitted_by="agent:weekly_risk",
    ))
    assert item.status == "pending"
    assert item.review_id
    assert item.submitted_by == "agent:weekly_risk"


def test_submit_invalid_priority(queue):
    with pytest.raises(ValueError):
        queue.submit(ReviewRequest(
            source_type="scenario",
            source_id="s-1",
            title="t",
            content="c",
            submitted_by="agent",
            priority="super_urgent",
        ))


def test_decide_approve(queue):
    item = queue.submit(ReviewRequest(
        source_type="scenario", source_id="s-1", title="T",
        content="C", submitted_by="agent",
    ))
    updated = queue.decide(item.review_id, ReviewDecision(
        decision="approved", reviewer="analyst@acme.com", comment="LGTM"
    ))
    assert updated.status == "approved"
    assert updated.reviewer == "analyst@acme.com"


def test_decide_reject(queue):
    item = queue.submit(ReviewRequest(
        source_type="scenario", source_id="s-2", title="T",
        content="C", submitted_by="agent",
    ))
    updated = queue.decide(item.review_id, ReviewDecision(
        decision="rejected", reviewer="mgr@acme.com", comment="Incorrect data"
    ))
    assert updated.status == "rejected"


def test_decide_needs_revision(queue):
    item = queue.submit(ReviewRequest(
        source_type="workflow_run", source_id="r-1", title="T",
        content="C", submitted_by="agent",
    ))
    updated = queue.decide(item.review_id, ReviewDecision(
        decision="needs_revision", reviewer="reviewer@acme.com",
        comment="Please re-check supplier data", correction="Fix: use Q4 data"
    ))
    assert updated.status == "needs_revision"
    assert updated.correction == "Fix: use Q4 data"


def test_resubmit_after_revision(queue):
    item = queue.submit(ReviewRequest(
        source_type="scenario", source_id="s-3", title="T",
        content="original", submitted_by="agent",
    ))
    queue.decide(item.review_id, ReviewDecision(
        decision="needs_revision", reviewer="r1", comment="revise"
    ))
    resubmitted = queue.resubmit(item.review_id, "revised content", "agent-v2")
    assert resubmitted.status == "pending"
    assert resubmitted.content == "revised content"


def test_resubmit_on_non_revision_raises(queue):
    item = queue.submit(ReviewRequest(
        source_type="scenario", source_id="s-4", title="T",
        content="C", submitted_by="agent",
    ))
    with pytest.raises(ValueError, match="needs_revision"):
        queue.resubmit(item.review_id, "new content", "agent")


def test_decide_on_approved_raises(queue):
    item = queue.submit(ReviewRequest(
        source_type="scenario", source_id="s-5", title="T",
        content="C", submitted_by="agent",
    ))
    queue.decide(item.review_id, ReviewDecision(decision="approved", reviewer="r"))
    with pytest.raises(ValueError, match="approved"):
        queue.decide(item.review_id, ReviewDecision(decision="rejected", reviewer="r"))


def test_decide_invalid_decision(queue):
    item = queue.submit(ReviewRequest(
        source_type="scenario", source_id="s-6", title="T",
        content="C", submitted_by="agent",
    ))
    with pytest.raises(ValueError, match="Invalid decision"):
        queue.decide(item.review_id, ReviewDecision(decision="maybe", reviewer="r"))


def test_capture_feedback(queue):
    item = queue.submit(ReviewRequest(
        source_type="workflow_run", source_id="r-2", title="T",
        content="C", submitted_by="agent",
    ))
    updated = queue.capture_feedback(item.review_id, "Model missed supplier X", "analyst")
    feedback_events = [h for h in updated.history if h.get("event") == "feedback"]
    assert len(feedback_events) == 1
    assert feedback_events[0]["feedback"] == "Model missed supplier X"


def test_list_items_filter_by_status(queue):
    queue.submit(ReviewRequest(source_type="t", source_id="1", title="T1", content="C", submitted_by="a"))
    item2 = queue.submit(ReviewRequest(source_type="t", source_id="2", title="T2", content="C", submitted_by="a"))
    queue.decide(item2.review_id, ReviewDecision(decision="approved", reviewer="r"))
    pending = queue.list_items(status="pending")
    assert all(i.status == "pending" for i in pending)


def test_queue_stats(queue):
    queue.submit(ReviewRequest(source_type="t", source_id="a", title="T", content="C", submitted_by="a", priority="high"))
    queue.submit(ReviewRequest(source_type="t", source_id="b", title="T", content="C", submitted_by="a", priority="normal"))
    stats = queue.queue_stats()
    assert stats["total"] >= 2
    assert "by_status" in stats
    assert "by_priority" in stats
    assert stats["by_priority"].get("high", 0) >= 1


def test_get_review_not_found(queue):
    assert queue.get("nonexistent-review-id") is None


# ── API integration ───────────────────────────────────────────────────────────

import src.hitl as _hitl_mod
import src.agent_runner as _ar_mod
from fastapi.testclient import TestClient


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    monkeypatch.setattr(_hitl_mod, "_REVIEW_STORE", tmp_path / "reviews.json")
    monkeypatch.setattr(_ar_mod, "_RUN_STORE", tmp_path / "runs.json")
    # Reset singletons so tests get fresh instances pointing to tmp_path
    import src.api_intelligence as ai
    monkeypatch.setattr(ai, "_hitl_queue", None)
    monkeypatch.setattr(ai, "_agent_runner", None)
    monkeypatch.setattr(ai, "_scenario_engine", None)
    from src.main import app
    return TestClient(app)


def test_api_list_packs(api_client):
    resp = api_client.get("/api/intelligence/packs")
    assert resp.status_code == 200
    assert resp.json()["count"] == 4


def test_api_list_scenarios(api_client):
    resp = api_client.get("/api/intelligence/scenarios")
    assert resp.status_code == 200
    assert resp.json()["count"] >= 5


def test_api_run_scenario_offline(api_client):
    resp = api_client.post("/api/intelligence/scenarios/run", json={
        "scenario_type": "demand_surge",
        "variables": {"change_pct": 15, "product_category": "semiconductors"},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["scenario_type"] == "demand_surge"
    assert "narrative" in data
    assert "impact_score" in data
    assert "confidence_interval" in data


def test_api_run_scenario_bad_type(api_client):
    resp = api_client.post("/api/intelligence/scenarios/run", json={
        "scenario_type": "bad_type", "variables": {},
    })
    assert resp.status_code == 400


def test_api_list_workflows(api_client):
    resp = api_client.get("/api/intelligence/workflows")
    assert resp.status_code == 200
    assert resp.json()["count"] >= 4


def test_api_run_workflow_offline(api_client):
    resp = api_client.post("/api/intelligence/workflows/run", json={
        "workflow": "investigate_anomaly",
        "context": {"anomaly": "Late delivery from Supplier X"},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["workflow"] == "investigate_anomaly"
    assert len(data["steps"]) == 4
    assert data["synthesis"]


def test_api_get_workflow_run(api_client):
    post_resp = api_client.post("/api/intelligence/workflows/run", json={
        "workflow": "propose_mitigations",
        "context": {"risk_description": "Single-source risk for critical component A"},
    })
    run_id = post_resp.json()["run_id"]
    get_resp = api_client.get(f"/api/intelligence/workflows/{run_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["run_id"] == run_id


def test_api_workflow_run_not_found(api_client):
    resp = api_client.get("/api/intelligence/workflows/nonexistent-run-id")
    assert resp.status_code == 404


def test_api_hitl_submit_and_list(api_client):
    submit = api_client.post("/api/intelligence/hitl/submit", json={
        "source_type": "workflow_run",
        "source_id": "run-1",
        "title": "Weekly risk summary",
        "content": "AI generated content",
        "submitted_by": "agent",
    })
    assert submit.status_code == 201
    review_id = submit.json()["review_id"]

    lst = api_client.get("/api/intelligence/hitl")
    assert lst.status_code == 200
    ids = [i["review_id"] for i in lst.json()["items"]]
    assert review_id in ids


def test_api_hitl_decide(api_client):
    submit = api_client.post("/api/intelligence/hitl/submit", json={
        "source_type": "scenario",
        "source_id": "s-1",
        "title": "Demand surge analysis",
        "content": "content",
        "submitted_by": "agent",
    })
    review_id = submit.json()["review_id"]
    decide = api_client.post(f"/api/intelligence/hitl/{review_id}/decide", json={
        "decision": "approved",
        "reviewer": "analyst@company.com",
        "comment": "Verified, looks good",
    })
    assert decide.status_code == 200
    assert decide.json()["status"] == "approved"


def test_api_hitl_queue_stats(api_client):
    api_client.post("/api/intelligence/hitl/submit", json={
        "source_type": "t", "source_id": "x", "title": "T", "content": "C", "submitted_by": "a"
    })
    resp = api_client.get("/api/intelligence/hitl/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1


def test_api_pack_query(api_client):
    resp = api_client.post("/api/intelligence/packs/risk/query", json={
        "query": "What are the main supplier risks?",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["pack"] == "risk"
    assert "answer" in data


def test_api_pack_query_not_found(api_client):
    resp = api_client.post("/api/intelligence/packs/nonexistent/query", json={
        "query": "test",
    })
    assert resp.status_code == 404
