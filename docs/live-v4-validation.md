# Operational-gate live validation — 2026-10-11

Three investigations authorized under a $1.50 total cap: rerun original certificate case 4, rerun original traffic case 5, and test correlated-v1 redacted case 18. Model `claude-haiku-4-5-20251001`, prompt `evidence-v4-operational-checks`, TF-IDF runbook retrieval and real in-memory MCP transport. No recovery actions were executed. Each case ran once under this approval.

| Case | Accepted outcome | Finalization | Seconds | Model / tool calls | Estimated cost |
|---|---|---|---:|---:|---:|
| cert_expiry / seed 4 | Correct payments / cert_expiry; renew_certificate | model_submission | 22.80 | 5 / 14 | $0.032570 |
| traffic_spike / seed 5 | Insufficient evidence; diagnostic miss; no action | model_submission | 56.09 | 12 / 21 | $0.131559 |
| missing_evidence / seed 18 | Expected insufficient evidence; no action | step_budget | 39.24 | 12 / 49 | $0.110672 |

**Total usage-derived token cost: $0.274801**, from provider-reported tokens and [Anthropic list prices](https://platform.claude.com/docs/en/about-claude/pricing); not invoice reconciliation. Cumulative input/output tokens: 210,221 / 12,916. Cache reads/writes were zero. No run exceptions or billing-uncertain responses occurred. Bounds remained 12 model calls, 24,000 counted input tokens and 1,000 output tokens per call, 180 seconds per investigation, and no SDK retries: at the verified rates, worst-case combined token cost was $1.26.

## Trace findings

- **Certificate:** correctly diagnosed payments instead of the caller orders. It called check_certificate(payments), obtained expiry_supported, and cited that assessment along with peer-verification errors and caller/gateway metrics. Four evidence references passed on the first submission; no validation rejections. The accepted server recommendation targets payments and requires rotation-policy verification. This is one successful rerun; it does not establish a general improvement rate.
- **Traffic spike:** repeatedly proposed scale for search even though check_capacity(search) reported blocked. Five submissions were rejected: two quotation errors, two blocked-scaling proposals, and one invalid abstention that retained a service/fault guess. On model call 12 it submitted a valid insufficient_evidence outcome with five exact references, null service/fault/action/target, and no accepted scaling recommendation. The server blocked the incompatible action, but this remains a diagnostic miss under ground truth because traffic_spike/search could be diagnosed. It was a model-submitted abstention on the final allowed call, not the automatic budget fallback.
- **Missing evidence:** after 49 tool calls across 12 model calls, the model never submitted a diagnosis or abstention. The graph's budget fallback returned insufficient_evidence with no guess and no action. This is a correct system-level outcome for the redacted case, not evidence that the model independently recognizes when to stop. No validation rejections occurred because nothing was submitted.

The batch has two expected outcomes under the existing grader (certificate and redacted fallback), but only one accepted positive diagnosis. The grader counts a budget-forced abstention as correct on redacted cases. Finalization origin is now recorded in a post-run `trace_review` field and displayed separately in the report, so that model-submitted and forced abstentions are distinguishable. Source/dataset hashes, usage, diagnoses and grade fields remain those recorded by the original run; prior experiments were not modified.

## Next work

Separate evidence-backed diagnosis from recovery-action availability so blocked scaling does not force loss of an otherwise supported diagnosis. Reduce repeated tool queries and provide an explicit stopping path when evidence cannot be obtained; improve targeted feedback when a submission fails several checks. Follow-up changes were implemented and verified offline; see [diagnosis-stopping.md](diagnosis-stopping.md). These live outcomes are preserved and not regraded. Any additional live validation requires another paid-run approval.

These findings defer deployment validation work. They do not establish production reliability or verified recovery. Single-case before/after reruns change the prompt, available tools and validator together, so they cannot isolate the effect of one change.

## Records

- Full local payload capture: `results/traces/live-v4-validation-payloads-cd1bd4933ead.jsonl` (ignored by Git; credential headers excluded).
- Offline suite: 53 tests passed in 3.33 seconds. Runtime code was not changed for these three investigations.
- [live-v4-cert_expiry-2026-10-11-d25c89d17f9b.json](../results/live-v4-cert_expiry-2026-10-11-d25c89d17f9b.json) contains measured results and derived trace review. Local full trace: `results/traces/live-v4-cert_expiry-2026-10-11-d25c89d17f9b.jsonl`.
- [live-v4-traffic_spike-2026-10-11-efcbd431f4ec.json](../results/live-v4-traffic_spike-2026-10-11-efcbd431f4ec.json) contains measured results and derived trace review. Local full trace: `results/traces/live-v4-traffic_spike-2026-10-11-efcbd431f4ec.jsonl`.
- [live-v4-missing_evidence-2026-10-11-e2dd981ee93f.json](../results/live-v4-missing_evidence-2026-10-11-e2dd981ee93f.json) contains measured results and derived trace review. Local full trace: `results/traces/live-v4-missing_evidence-2026-10-11-e2dd981ee93f.jsonl`.
