# Runbook: Memory leak and OOM kills

## Symptoms
Memory usage climbs steadily and never plateaus. Garbage collection pauses grow longer, heap above 90 percent. Latency and CPU rise gradually as GC thrashes. The container is terminated with OOMKilled exit code 137 and restarts, then memory climbs again. Restart counter increases.

## Diagnosis
Plot memory over the last hour: a linear ramp and repeated OOM kills support a memory-leak hypothesis. A nearby release or caching change is a correlation; an unbounded in-process cache or memoization is a possible mechanism, not an established fact without heap or implementation evidence. Check deploy history and collect that evidence before asserting the mechanism.

## Remediation
Consider a controlled restart for temporary relief after checking redundancy, drain requirements and the service-specific procedure. Capture a heap dump before restarting if possible. Consider a rollback only after verifying a previous healthy release and schema/configuration compatibility; do not invent a rollback version. If heap or implementation evidence confirms unbounded cache growth, investigate eviction or size limits before redeployment. Verify service and caller error rates and latency after any approved change.
