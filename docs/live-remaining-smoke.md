# Remaining-fault live smoke — 2026-10-11

Three Haiku investigations authorized under a $1.50 combined cap. Each used one original synthetic case, TF-IDF retrieval, real in-memory MCP transport and prompt `evidence-v3-policy-remediation`. No recovery actions were executed and no cases were repeated.

| Fault / case | Injected service | Diagnosed service | Outcome | Seconds | Model / tool calls | Estimated cost |
|---|---|---|---|---:|---:|---:|
| slow_dependency / seed 2 | postgres | postgres | Correct | 40.25 | 9 / 20 | $0.072066 |
| cert_expiry / seed 4 | payments | orders | Wrong service | 19.13 | 4 / 11 | $0.024902 |
| traffic_spike / seed 5 | search | search | Correct | 45.33 | 12 / 25 | $0.097339 |

Batch result: **2/3 correct service-and-fault diagnoses**; all three fault types correctly named. **$0.194307** combined token-cost estimate, calculated from provider-reported usage and [Anthropic list prices](https://platform.claude.com/docs/en/about-claude/pricing), not invoice reconciliation. Input/output tokens: **144207 / 10020**. Cache reads/writes were zero. There were no run exceptions or billing-uncertain responses.

Limits were 12 model calls, 24,000 counted input tokens and 1,000 output tokens per call, 180 seconds per investigation, and zero SDK retries. Treating every input token as a five-minute cache write gives a $1.26 combined upper token-cost bound at the verified rates.

## Findings

- **Slow dependency:** correctly identified `postgres`, supported by latency/CPU trends, slow-query/lock-wait logs and caller timeouts. Two submitted diagnoses were rejected for nonexact quotations; the third was accepted with five exact references. Provider prose proposed specific index changes and disabling autovacuum without sufficient verification. The accepted server recommendation instead requires query-plan/runbook investigation before changes and supplies no query change.
- **Certificate expiry:** identified the right fault type but blamed `orders` instead of injected root `payments`. Five citations passed on the first submission. Its quoted log said `orders ERROR TLS handshake failed calling payments: x509: certificate has expired`. The trace attributed certificate ownership to the caller reporting the failure; it treated normal payments application metrics and missing payments error logs as supporting that attribution. That inference was wrong for this simulated case. The server generated certificate-verification advice for the wrongly diagnosed target. Provenance and action/target consistency checks do not establish which service owns the certificate.
- **Traffic spike:** correctly identified `search`, with increased traffic, CPU/latency and load-shedding evidence. One submission was rejected for an invalid field set; the next was accepted with four exact references on model call 12, the last permitted call. The selected action was `scale` even though a cited observation said the autoscaler was at max replicas (12/12). The server policy requires checking permitted limits before changing capacity, but this does not establish that scaling is a viable recovery action in this case. Compatibility grading is not recovery validation.

Across the batch, all 14 final evidence references passed exact-quote validation, including the wrong certificate diagnosis. There were two citation-related rejections and one schema rejection. The observations show why provenance, diagnostic correctness and recovery feasibility need separate assessment.

## Coverage and next correctness work

Across all live smoke runs, there is now one case per simulator fault type: five of six service-and-fault diagnoses were correct. The initial bad-deploy and memory-leak cases used the older prompt/validator; subsequent cases used the updated one. This small mixed-version set is not a controlled comparison or evidence of production reliability. Live abstention and challenge variants remain untested.

Prioritize verified TLS certificate ownership/caller-versus-peer reasoning and action feasibility at capacity limits before deployment. Add offline regression cases for these findings; any live rerun or missing-evidence investigation requires another paid-run approval. Unspent budget from this three-case approval was not used for additional cases.

## Records and verification

- Full local request/response capture: `results/traces/live-remaining-payloads-68617ac43af9.jsonl` (ignored by Git; credential headers excluded).
- 38 offline tests passed in 1.81 seconds. Runtime code was not changed for this batch.
- [live-slow_dependency-2026-10-11-5fe3b18769bc.json](../results/live-slow_dependency-2026-10-11-5fe3b18769bc.json) records configuration, source/dataset hashes, diagnosis and usage. Local full trace: `results/traces/live-slow_dependency-2026-10-11-5fe3b18769bc.jsonl`.
- [live-cert_expiry-2026-10-11-2c5ec81643c4.json](../results/live-cert_expiry-2026-10-11-2c5ec81643c4.json) records configuration, source/dataset hashes, diagnosis and usage. Local full trace: `results/traces/live-cert_expiry-2026-10-11-2c5ec81643c4.jsonl`.
- [live-traffic_spike-2026-10-11-8c9a12acc1d5.json](../results/live-traffic_spike-2026-10-11-8c9a12acc1d5.json) records configuration, source/dataset hashes, diagnosis and usage. Local full trace: `results/traces/live-traffic_spike-2026-10-11-8c9a12acc1d5.jsonl`.
