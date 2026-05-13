# Operations Runbook

## Deployment Modes

- Canary: use .github/workflows/canary-deploy.yml
- Blue/Green: use .github/workflows/blue-green-deploy.yml

## Standard Deploy Steps

1. Run tests and quality gates.
2. Build container image.
3. Deploy to staging and run smoke checks.
4. Promote using canary or blue/green.
5. Monitor /metrics/operational and /metrics/slo-status.

## Rollback

Use rollback helper:

```bash
./scripts/rollback.sh <target_ref>
```

## SLO Breach Response

1. Trigger check: POST /alerts/slo/check
2. If breached, switch traffic to previous stable release.
3. Open incident ticket and attach request/error metrics.
4. Run post-incident review and corrective action tracking.
