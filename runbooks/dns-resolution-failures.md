# Runbook: DNS resolution failures

## Symptoms
Intermittent errors with NXDOMAIN or temporary failure in name resolution across many services at once. Failures are not tied to one deploy.

## Diagnosis
Check the cluster DNS pods, query latency, and recent changes to resolver configuration.

## Remediation
Restart or scale the cluster DNS deployment, and fix the resolver configuration.
