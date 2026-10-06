# Runbook: auth release-specific recovery

Synthetic policy fixtures. These instructions apply only to the stated version.

## auth v1 recovery policy
Auth v1 expired certificate; rotate the leaf before reloading TLS.

Approval is required before any action. The following structured policy defines exact order and limits:

```json
{"policy_id": "auth-v1-tls", "service": "auth", "version": "v1", "action": "renew_certificate", "steps": ["rotate_leaf_certificate", "reload_tls", "verify_handshake"], "limits": {"bundle_required": false}}
```

## auth v2 recovery policy
Auth v2 expired certificate; stage the dual trust bundle before replacing the leaf and reloading TLS.

Approval is required before any action. The following structured policy defines exact order and limits:

```json
{"policy_id": "auth-v2-tls", "service": "auth", "version": "v2", "action": "renew_certificate", "steps": ["stage_dual_trust_bundle", "rotate_leaf_certificate", "reload_tls", "verify_handshake"], "limits": {"bundle_required": true}}
```
