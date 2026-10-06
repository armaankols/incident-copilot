# Runbook: postgres release-specific recovery

Synthetic policy fixtures. These instructions apply only to the stated version.

## postgres v14 recovery policy
Postgres v14 slow query on the primary; concurrent index creation is allowed.

Approval is required before any action. The following structured policy defines exact order and limits:

```json
{"policy_id": "postgres-v14-query", "service": "postgres", "version": "v14", "action": "optimize_query", "steps": ["create_index_concurrently", "verify_query_plan"], "limits": {"index_creation_allowed": true}}
```

## postgres v15 recovery policy
Postgres v15 slow reads on a hot standby; index creation is prohibited here, route reads to the primary first.

Approval is required before any action. The following structured policy defines exact order and limits:

```json
{"policy_id": "postgres-v15-query", "service": "postgres", "version": "v15", "action": "reroute_reads", "steps": ["route_reads_to_primary", "verify_replication_lag", "verify_query_plan"], "limits": {"index_creation_allowed": false}}
```
