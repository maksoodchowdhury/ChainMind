"""Enterprise platformization APIs: tenancy, connectors, governance, and control plane."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.billing import build_chargeback_report, get_pricing, set_pricing
from src.extensions import (
    get_active_extensions,
    list_extensions,
    register_extension,
    set_active_extension,
)
from src.integration_fabric import (
    configure_connector,
    create_cdc_job,
    list_connectors,
    list_events,
    list_sync_jobs,
    publish_event,
    run_connector_sync,
)
from src.model_registry import list_models, register_model, set_workload_strategy
from src.policy_engine import evaluate_model_usage, evaluate_residency, load_policies
from src.tenant_control import get_usage, list_tenants, set_quota

router = APIRouter(prefix="/api/platform", tags=["platform"])


class TenantQuotaRequest(BaseModel):
    daily: int
    monthly: int


class ConnectorConfigRequest(BaseModel):
    enabled: bool


class ConnectorSyncRequest(BaseModel):
    trigger: str = "manual"


class EventRequest(BaseModel):
    event_type: str
    payload: dict


class CDCJobRequest(BaseModel):
    connector: str
    schedule_cron: str


class ModelRegisterRequest(BaseModel):
    alias: str
    provider: str
    model: str
    active: bool = False


class WorkloadStrategyRequest(BaseModel):
    query_class: str
    target_alias: str = Field(alias="model_alias")


class PricingRequest(BaseModel):
    usd_per_request: float
    usd_per_ingestion_event: float
    usd_per_storage_doc: float


class ExtensionRegisterRequest(BaseModel):
    name: str
    ext_type: str
    description: str = ""
    entrypoint: str = "builtin"


class ExtensionActivateRequest(BaseModel):
    slot: str
    name: str | None = None


@router.get("/tenants")
async def tenants_overview() -> dict:
    return {"tenants": list_tenants()}


@router.get("/tenants/{tenant_id}/usage")
async def tenant_usage(tenant_id: str) -> dict:
    return get_usage(tenant_id)


@router.put("/tenants/{tenant_id}/quota")
async def tenant_quota(tenant_id: str, body: TenantQuotaRequest) -> dict:
    entry = set_quota(tenant_id, daily=body.daily, monthly=body.monthly)
    return {"tenant_id": tenant_id, "quota": entry.get("quota")}


@router.get("/connectors")
async def connectors() -> dict:
    return list_connectors()


@router.put("/connectors/{name}")
async def configure(name: str, body: ConnectorConfigRequest) -> dict:
    return {"connector": name, **configure_connector(name, enabled=body.enabled)}


@router.post("/connectors/{name}/sync")
async def sync(name: str, body: ConnectorSyncRequest) -> dict:
    return run_connector_sync(name, trigger=body.trigger)


@router.post("/events/webhook")
async def webhook_event(body: EventRequest) -> dict:
    evt = publish_event(body.event_type, body.payload)
    return {"status": "accepted", "event": evt}


@router.get("/events")
async def events(limit: int = 100) -> dict:
    return {"events": list_events(limit=limit)}


@router.post("/cdc/jobs")
async def cdc_job(body: CDCJobRequest) -> dict:
    return create_cdc_job(body.connector, schedule_cron=body.schedule_cron)


@router.get("/sync/jobs")
async def sync_jobs() -> dict:
    return {"jobs": list_sync_jobs()}


@router.get("/governance/policies")
async def policies() -> dict:
    return load_policies()


@router.get("/governance/residency/check")
async def residency_check(region: str) -> dict:
    return evaluate_residency(region)


@router.get("/governance/model-usage/check")
async def model_usage_check(tenant_id: str, uses_external_model: bool = True) -> dict:
    return evaluate_model_usage(tenant_id, uses_external_model=uses_external_model)


@router.get("/control-plane/models")
async def models() -> dict:
    return list_models()


@router.post("/control-plane/models")
async def add_model(body: ModelRegisterRequest) -> dict:
    return register_model(body.alias, provider=body.provider, model=body.model, active=body.active)


@router.post("/control-plane/workload-strategy")
async def workload_strategy(body: WorkloadStrategyRequest) -> dict:
    return {"workload_strategy": set_workload_strategy(body.query_class, body.target_alias)}


@router.get("/contracts")
async def schema_contracts() -> dict:
    return {
        "contracts": [
            {"name": "QueryRequest", "path": "/api/query/", "version": "v1"},
            {"name": "ScenarioRunRequest", "path": "/api/intelligence/scenarios/run", "version": "v1"},
            {"name": "WorkflowRunRequest", "path": "/api/intelligence/workflows/run", "version": "v1"},
        ]
    }


@router.get("/billing/pricing")
async def billing_pricing() -> dict:
    return {"pricing": get_pricing()}


@router.put("/billing/pricing")
async def billing_pricing_set(body: PricingRequest) -> dict:
    pricing = set_pricing(
        usd_per_request=body.usd_per_request,
        usd_per_ingestion_event=body.usd_per_ingestion_event,
        usd_per_storage_doc=body.usd_per_storage_doc,
    )
    return {"pricing": pricing}


@router.get("/billing/chargeback")
async def chargeback(month: str | None = None) -> dict:
    return build_chargeback_report(month=month)


@router.get("/extensions")
async def extensions(ext_type: str | None = None) -> dict:
    return {"extensions": list_extensions(ext_type=ext_type), "active": get_active_extensions()}


@router.post("/extensions")
async def extensions_register(body: ExtensionRegisterRequest) -> dict:
    return register_extension(
        body.name,
        ext_type=body.ext_type,
        description=body.description,
        entrypoint=body.entrypoint,
    )


@router.post("/extensions/activate")
async def extensions_activate(body: ExtensionActivateRequest) -> dict:
    return {"active": set_active_extension(body.slot, body.name)}
