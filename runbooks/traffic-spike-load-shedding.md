# Runbook: Traffic spike saturating capacity

## Symptoms
Requests per second at an edge service rise several times above normal. CPU saturates near 100 percent, latency and error rate climb, 429 and 503 responses appear. Logs show the autoscaler at max replicas and the rate limiter shedding load. Downstream request rates rise too.

## Diagnosis
Confirm inbound request rate rose well above baseline at the entry service and that latency followed, rather than the reverse. Look for a top talker client responsible for most traffic.

## Remediation
Use check_capacity before recommending scale. A service at its replica limit has no verified headroom; do not assume permission or resources to raise that limit or scale manually. Unknown or conflicting capacity also leaves scaling unverified. Consider policy-checked per-client rate limiting or load shedding for non-critical routes, verifying protected traffic classes and permitted thresholds first. If no compatible recovery action can be supported, abstain and consult the service owner. No action is executed by the investigation.
