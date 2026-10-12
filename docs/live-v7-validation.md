# V7 live validation — 2026-10-12

Two Haiku investigations ran under a new **$1 total approval**, using the same
pinned model as all prior live runs: `claude-haiku-4-5-20251001`. Prompt:
`evidence-v7-all-faults-compact-submission`, TF-IDF retrieval, real in-memory MCP.
Runtime revision: `9b44702c5205ccc0903d5ecd0fccb0da84e7fb5b`. No replacement
investigations, SDK retries, model switching or recovery execution occurred.

**The redacted case passed; the traffic case remained a diagnostic miss.**
Both received complete model submissions without output truncation. Evidence
validation blocked an unsupported inventory rollback. Citation errors still
prevented acceptance of the later correct traffic hypothesis.

| Case | Final outcome | Model / MCP calls | Validation rejections | Truncations | Seconds | Usage-derived cost |
|---|---|---:|---:|---:|---:|---:|
| original traffic_spike / seed 5 | System-forced abstention, correction_limit; miss | 8 / 16 | 3 | 0 | 32.63 | $0.066144 |
| correlated-v2 redacted / seed 18 | Model-submitted insufficient_evidence; expected outcome | 6 / 23 | 0 | 0 | 23.96 | $0.046017 |

Combined usage-derived token cost: **$0.112161**, below the approved $1 cap.
Provider-reported input/output totals: **86,246 / 5,183**. Cache-read/write tokens:
**0 / 0**. The isolated batch ledger settled at $0.112161. Both runs had no runtime
exceptions or billing uncertainty. Cost uses verified
[Anthropic list prices](https://platform.claude.com/docs/en/about-claude/pricing),
not invoice reconciliation. No additional paid calls were made after these runs.

Bounds remained 12 model calls per run, 24,000 input and 1,000 output tokens per
call, 32 tool requests, three invalid submissions, three output truncations,
three stagnant rounds, 180-second run timeout and 45-second provider timeout,
with no SDK retries. The calculated maximum token cost for the two runs was
$0.84. Both had zero cache hits; requests equalled MCP executions.

## Traffic failure review

Expected: search/traffic_spike, with scaling blocked or no action verified.

The agent obtained an unknown inventory/bad_deploy assessment at `obs-11`, a
supported search/traffic_spike assessment at `obs-12`, and a blocked search
capacity assessment at `obs-13`. Inventory/traffic_spike also returned unknown.
These checks did not force the model to choose the supported cause immediately.

The agent made three complete six-field submissions:

1. **Inventory/bad_deploy, rollback inventory.** Only one of its three quotations
   was exact. A flattened RPS/assessment excerpt at `obs-12` failed exact-substring
   validation; the validator stopped before checking fault support.
2. **Inventory/bad_deploy, rollback inventory.** All three quotations were exact,
   but the required inventory change assessment was unknown. The diagnostic gate
   rejected this submission, so the unrelated rollback was not recommended.
3. **Search/traffic_spike, scale search.** The load-shedding excerpt from `obs-12`
   was exact, but both metric excerpts combined metric names with samples that
   were not contiguous substrings. The validator rejected the first invalid
   metric quotation and reached the three-invalid-submission limit.

The server therefore returned `insufficient_evidence`, termination_reason=
`correction_limit`. This remains a diagnostic miss; it was neither a correct
accepted diagnosis nor a model-selected abstention. No action was recommended.
The largest provider response was **560 output tokens**. Submitted JSON inputs
were **490, 483 and 444 UTF-8 bytes**, respectively; all contained the six required
fields and at most three quotations. No output limit was reached.

An offline edited-payload check replaced the two invalid metric excerpts in the
third submission with genuine observed metric headers. The current validator then
accepted search/traffic_spike and removed scaling with recovery_status=blocked.
This isolates the remaining citation problem and verifies recovery normalization
for that edited input. It is not another model response or a live success, and the
saved live outcome/grade remains unchanged.

## Redacted-evidence result

Expected: model-submitted `insufficient_evidence`, with no guessed cause/action.

The model saw explicit unknown dependency health and unavailable collection
coverage. Ten tool results contained an UNAVAILABLE marker. Gateway assessments
for slow_dependency, traffic_spike, memory_leak, bad_deploy and config_error all
returned unknown; the gateway capacity assessment also returned unknown.

On call six, the model submitted `insufficient_evidence`, null service/fault/action/
target and an empty evidence array. The validator accepted it without a rejection.
Termination was **model_submission**, rather than a server budget or stopping rule.
It used six of 12 allowed calls and 23 of 32 allowed tool requests. No unsupported
dependency diagnosis or recovery recommendation was accepted.

The final JSON input was **120 UTF-8 bytes**; its complete provider response used
**576 output tokens**, including model text. That was the largest response in this
run. The model's prose still contributes to output usage despite the compact JSON.

## Comparison and remaining work

Both datasets match their corresponding v6 hashes: original seed 5 and
correlated-v2 redacted seed 18. The model pin and token/call bounds also match.
Prompt, evidence gates, submission schema and truncation handling changed together.
These are one stochastic investigation per case, not a controlled reliability study.

| Case | V6 final outcome | V7 final outcome | Calls V6 → V7 | MCP executions V6 → V7 | Truncations V6 → V7 | Token-cost estimate V6 → V7 |
|---|---|---|---|---|---|---|
| Traffic | Forced abstention after truncation/citation failures | Forced abstention after citation/support failures | 9 → 8 | 19 → 16 | 2 → 0 | $0.083196 → $0.066144 |
| Redacted | Unsupported auth/slow_dependency accepted | Model-submitted abstention | 9 → 6 | 25 → 23 | 1 → 0 | $0.072745 → $0.046017 |

Zero truncations in these two runs and the redacted success are measured outcomes,
not proof that the changes solve all cases. The traffic model continued proposing
an unsupported cause after receiving an unknown assessment, then failed to quote
its supported alternative correctly. Additional scenarios/repetitions remain
untested under v7; no paid repetitions were made to replace this failure.

The next change should make evidence references easier to submit correctly while
retaining provenance and fault gates: let the model select observation IDs and
have the server attach exact excerpts from the trusted observations. This removes
manual copying/formatting as a failure source without accepting unsupported
service/fault combinations. Add offline regressions before further paid tests.
No such interface change was made during this batch.

The runtime code was unchanged for these tests. Its prior offline verification
was **130 tests passed in 2.99 seconds**, with successful Docker/CI checks. Those
implementation checks remain separate from the mixed live outcomes. Further
paid tests require a new budget approval.

## Records

- [Traffic result](../results/live-v7-traffic_spike-2026-10-12-b13344078fec.json)
- [Redacted result](../results/live-v7-missing_evidence-2026-10-12-b1eb096c5e8a.json)

Both save source/dataset hashes, runtime revision, configuration, diagnosis,
grading, usage, counters, termination and reviewed assessment/submission summaries.
All 14 captured response usages were reconciled with the saved per-run totals.
Prior live results and grades are preserved.

Local full payload capture: `results/traces/live-v7-validation-payloads-01293770f24c.jsonl`.
Full local run traces use the result stem plus `.jsonl` in `results/traces/`.
Credentials and headers are excluded from capture; these full payloads/traces
are ignored by Git.
