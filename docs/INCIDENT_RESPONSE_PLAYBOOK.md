# Incident Response Playbook

## Severity Levels

- SEV-1: User-impacting outage or data integrity risk
- SEV-2: Major degradation with workaround
- SEV-3: Minor degradation

## Immediate Actions

1. Declare incident and assign Incident Commander.
2. Capture current system state from /health, /ready, /metrics/operational.
3. Freeze non-essential deployments.
4. If needed, execute rollback.

## Communication

- Internal updates every 15 minutes for SEV-1.
- Stakeholder update includes impact, ETA, and mitigation in progress.

## Recovery Checklist

1. Confirm SLO status healthy.
2. Verify ingestion and query paths.
3. Validate no authz/audit regressions.
4. Close incident and schedule postmortem.
