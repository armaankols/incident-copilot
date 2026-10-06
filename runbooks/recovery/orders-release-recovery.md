# Runbook: orders release-specific recovery

Synthetic policy fixtures. These instructions apply only to the stated version.

## orders v3 recovery policy
Checkout exceptions after a release; orders v3 uses a compatible database schema.

Approval is required before any action. The following structured policy defines exact order and limits:

```json
{"policy_id": "orders-v3-rollback", "service": "orders", "version": "v3", "action": "rollback", "steps": ["verify_schema_compatibility", "rollback_previous_release", "verify_checkout"], "limits": {"rollback_allowed": true}}
```

## orders v4 recovery policy
Checkout exceptions after a release; orders v4 already migrated the database schema and rollback is prohibited.

Approval is required before any action. The following structured policy defines exact order and limits:

```json
{"policy_id": "orders-v4-rollforward", "service": "orders", "version": "v4", "action": "rollforward", "steps": ["disable_checkout_flag", "deploy_forward_fix", "verify_checkout"], "limits": {"rollback_allowed": false}}
```
