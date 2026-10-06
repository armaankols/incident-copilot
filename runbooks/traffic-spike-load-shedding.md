# Runbook: Traffic spike saturating capacity

## Symptoms
Requests per second at an edge service rise several times above normal. CPU saturates near 100 percent, latency and error rate climb, 429 and 503 responses appear. Logs show the autoscaler at max replicas and the rate limiter shedding load. Downstream request rates rise too.

## Diagnosis
Confirm inbound request rate rose well above baseline at the entry service and that latency followed, rather than the reverse. Look for a top talker client responsible for most traffic.

## Remediation
Raise the autoscaler maximum or scale out manually, apply a per-client rate limit or block the abusive client, and enable load shedding for non-critical routes.
