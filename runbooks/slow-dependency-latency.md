# Runbook: Slow dependency causing upstream timeouts

## Symptoms
Callers log timeouts calling one downstream service. The downstream service shows high latency and high CPU while request rate is normal. Database symptoms: slow query warnings, sequential scans, lock waits. Service symptoms: thread pool saturation and growing queue depth.

## Diagnosis
Find the service where latency rose first and where traffic did not change. Errors in callers are symptoms, not the cause. For databases, inspect slow query logs and lock waits such as autovacuum holding locks.

## Remediation
For a database, kill long-running queries, add the missing index, or reschedule the maintenance job holding locks. For a service, scale out replicas and increase the thread pool while investigating the slow code path.
