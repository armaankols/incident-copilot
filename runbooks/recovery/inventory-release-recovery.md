# Runbook: inventory release-specific recovery

Synthetic policy fixtures. These instructions apply only to the stated version.

## inventory v1 recovery policy
Inventory v1 configuration release reduced its client pool; restore 20 connections per replica within the global limit of 100.

Approval is required before any action. The following structured policy defines exact order and limits:

```json
{"policy_id": "inventory-v1-pool", "service": "inventory", "version": "v1", "action": "restore_config", "steps": ["set_pool_max", "canary_one_replica", "verify_connection_wait"], "limits": {"pool_max_per_replica": 20, "global_connection_limit": 100}}
```

## inventory v2 recovery policy
Inventory v2 configuration release reduced its client pool; shared database quota now requires 8 connections per replica and a global limit of 40.

Approval is required before any action. The following structured policy defines exact order and limits:

```json
{"policy_id": "inventory-v2-pool", "service": "inventory", "version": "v2", "action": "restore_config", "steps": ["set_pool_max", "canary_one_replica", "verify_connection_wait"], "limits": {"pool_max_per_replica": 8, "global_connection_limit": 40}}
```
