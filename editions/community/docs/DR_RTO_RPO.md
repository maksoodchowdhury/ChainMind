# Disaster Recovery Targets

## Targets

- RTO: 30 minutes
- RPO: 15 minutes

## Recovery Strategy

- Keep deployable artifacts versioned and immutable.
- Maintain rollback path to previous stable release.
- Persist operational stores with optional at-rest encryption controls.

## Backup/Restore Validation

- Daily backup verification for data/ stores.
- Monthly restoration drill in non-production environment.

## Failover Procedure

1. Detect outage and classify severity.
2. Restore latest known-good deployment.
3. Restore persisted stores from backup snapshot if required.
4. Validate health/readiness and business-critical endpoints.
