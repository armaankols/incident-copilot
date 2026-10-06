# Runbook: Regression after a bad deploy

## Symptoms
Error rate on one service jumps sharply within minutes of a release. Logs show new unhandled exceptions (NullPointerException, KeyError, TypeError) tagged with the new build version. Callers log 5xx responses from the service. CPU and memory stay roughly normal.

## Diagnosis
Compare the exact minute the error rate rose with deploy history. The culprit is the service whose deploy lands immediately before onset, not necessarily the most recent deploy overall. Confirm the exception text carries the new build version and did not appear before the release.

## Remediation
Roll back the service to the previous version immediately, then open a ticket with the stack trace. Re-deploy only after a fix and a canary stage.
