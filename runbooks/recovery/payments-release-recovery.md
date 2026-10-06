# Runbook: payments release-specific recovery

Synthetic policy fixtures. These instructions apply only to the stated version.

## payments v2 recovery policy
Payments v2 memory exhaustion; drain pending authorizations before restarting one replica.

Approval is required before any action. The following structured policy defines exact order and limits:

```json
{"policy_id": "payments-v2-restart", "service": "payments", "version": "v2", "action": "restart", "steps": ["drain_inflight_payments", "restart_one_replica", "verify_ledger_consistency"], "limits": {"parallel_restarts": 1}}
```

## payments v3 recovery policy
Payments v3 memory exhaustion; the new leader lease must be released before draining and restarting.

Approval is required before any action. The following structured policy defines exact order and limits:

```json
{"policy_id": "payments-v3-restart", "service": "payments", "version": "v3", "action": "restart", "steps": ["release_leader_lease", "drain_inflight_payments", "restart_one_replica", "verify_ledger_consistency"], "limits": {"parallel_restarts": 1}}
```
