# Runbook: Connection pool exhaustion after configuration change

## Symptoms
A service starts returning 503 errors with logs such as connection pool exhausted, timed out waiting for connection. Latency jumps because requests queue for a connection. CPU stays flat or drops. The database itself looks healthy.

## Diagnosis
Check deploy history for a configuration change shortly before onset, for example a smaller pool size or shorter timeouts. The service startup log prints the loaded configuration, compare pool max with the previous value.

## Remediation
Revert the configuration change to the previous pool size and timeouts, then redeploy. Add a config validation check and a canary for pool settings.
