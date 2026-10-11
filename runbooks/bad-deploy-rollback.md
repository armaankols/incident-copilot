# Runbook: Regression after a bad deploy

## Symptoms
Error rate on one service jumps sharply within minutes of a release. Logs show new unhandled exceptions (NullPointerException, KeyError, TypeError) tagged with the new build version. Callers log 5xx responses from the service. CPU and memory stay roughly normal.

## Diagnosis
Compare the exact minute the error rate rose with deploy history. The culprit is the service whose deploy lands immediately before onset, not necessarily the most recent deploy overall. Confirm the exception text carries the new build version and did not appear before the release.

## Remediation
Identify the previous healthy release from deployment records; do not infer its version by decrementing the current version. Verify database schema and configuration compatibility and the service-specific rollback procedure before recommending a rollback. If a compatible rollback target is unavailable, escalate to the service owner for a recovery plan. After an approved change, verify service and caller error rates and latency against their configured SLOs. Open a ticket with the stack trace; re-deploy only after a fix and a canary stage.
