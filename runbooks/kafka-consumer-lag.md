# Runbook: Kafka consumer lag

## Symptoms
Consumer group lag grows steadily, event processing falls behind, stale data appears downstream. Partition rebalances repeat.

## Diagnosis
Compare producer rate to consumer throughput and inspect rebalance frequency and slow message handlers.

## Remediation
Add consumers up to the partition count, fix slow handlers, and tune session timeouts to stop rebalance loops.
