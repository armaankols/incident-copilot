# Runbook: search release-specific recovery

Synthetic policy fixtures. These instructions apply only to the stated version.

## search v1 recovery policy
Search v1 traffic burst; autoscaling is allowed up to 6 replicas.

Approval is required before any action. The following structured policy defines exact order and limits:

```json
{"policy_id": "search-v1-traffic", "service": "search", "version": "v1", "action": "scale", "steps": ["scale_within_quota", "verify_queue_depth"], "limits": {"max_replicas": 6}}
```

## search v2 recovery policy
Search v2 traffic burst; shed excess requests first because the contracted replica quota is only 3.

Approval is required before any action. The following structured policy defines exact order and limits:

```json
{"policy_id": "search-v2-traffic", "service": "search", "version": "v2", "action": "rate_limit", "steps": ["shed_excess_traffic", "scale_within_quota", "verify_queue_depth"], "limits": {"max_replicas": 3}}
```
