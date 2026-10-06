# Runbook: Disk full

## Symptoms
Writes fail with no space left on device. Services crash on log writes. Disk usage above 95 percent.

## Diagnosis
Find the largest directories and unrotated log files on the node.

## Remediation
Delete or rotate old logs, expand the volume, and add disk usage alerts.
