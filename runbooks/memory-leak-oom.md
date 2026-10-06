# Runbook: Memory leak and OOM kills

## Symptoms
Memory usage climbs steadily and never plateaus. Garbage collection pauses grow longer, heap above 90 percent. Latency and CPU rise gradually as GC thrashes. The container is terminated with OOMKilled exit code 137 and restarts, then memory climbs again. Restart counter increases.

## Diagnosis
Plot memory over the last hour: a linear ramp that began after a release points at a leak introduced by that release, often an unbounded in-process cache or memoization. Check deploy history for changes that added caching shortly before the ramp began.

## Remediation
Restart the affected pods to buy time, then roll back the release that introduced the cache or fix the unbounded growth (add eviction or a size limit). Capture a heap dump before restarting if possible.
