# V8 live validation — 2026-10-12

Two Haiku investigations used the new observation-ID interface and met their
expected diagnostic outcomes: search/traffic_spike with no recovery action, and
model-submitted abstention on missing evidence. Both completed with **zero
validation rejections and zero output truncations**.

Model: `claude-haiku-4-5-20251001`, prompt:
`evidence-v8-observation-id-submission`, TF-IDF retrieval, real in-memory MCP.
Runtime revision: `d32b6626a6c49ba379c6444716560744a01b902b`. No model switch,
replacement investigation, SDK retry or recovery execution occurred.

| Case | Accepted final outcome | Model / MCP calls | Seconds | Usage-derived token cost |
|---|---|---:|---:|---:|
| original traffic_spike / seed 5 | search / traffic_spike; action=null | 7 / 20 | 26.15 | $0.053230 |
| correlated-v2 redacted / seed 18 | Model-submitted insufficient_evidence | 6 / 20 | 22.47 | $0.042555 |

Combined usage-derived cost: **$0.095785**. Provider-reported input/output totals:
**74,345 / 4,288**. Cache-read/write tokens: **0 / 0**. All 13 captured response
usages were reconciled with saved per-run totals. Both runs had no runtime errors
or billing uncertainty. Costs use verified
[Anthropic list prices](https://platform.claude.com/docs/en/about-claude/pricing),
not invoice reconciliation. The isolated batch ledger settled at $0.095785 after
rounding. No additional paid investigations were made in this batch.

## Per-test budget authorization

The user approved this two-test batch and gave standing authorization for API
tests costing **up to $0.50 per test** from now on. Tests within a verified
conservative per-test token-cost bound can proceed without another API-budget
confirmation in this collaboration. A higher or unverified bound requires approval.
This preference is also recorded in `docs/verification.md` for continuation.

Each current test's calculated maximum token cost was **$0.42**, checked before
creating the provider client. The two-case batch's calculated maximum was $0.84,
within its $1 approval. Bounds were unchanged: 12 model calls per test, 24,000
input and 1,000 output tokens per call, 32 tool requests, three invalid submissions,
three output truncations, three stagnant rounds, 180-second run timeout, 45-second
provider timeout and zero SDK retries. These are application/token bounds;
usage-derived costs are not reconciled account invoices.

## Traffic result

Expected: search/traffic_spike, keeping a supported cause while scaling is blocked
or no recovery action is verified.

The model retrieved a supported search/traffic_spike assessment at `obs-9`, search
RPS at `obs-11`, and blocked search capacity at `obs-18`. Other hypotheses received
unknown assessments: search/slow_dependency, inventory/bad_deploy and search/
config_error. It submitted one six-field diagnosis, selecting exactly those
three successful observation IDs:

```json
{"status":"diagnosed","root_cause_service":"search","fault_type":"traffic_spike","evidence":["obs-9","obs-11","obs-18"],"action":null,"target":null}
```

The server attached these actual source excerpts:

- `obs-9`: `"status": "supported"`
- `obs-11`: `search.rps last 60m: min=153.6 mean=650.5 max=1010.9 latest=991.0`
- `obs-18`: `"status": "blocked"`

All three are exact substrings of their selected observations. The validator
accepted search/traffic_spike without a rejection. No rollback or scaling action
was proposed in the final input or recommended by the server. The result's
recovery_status is **unverified**, meaning no action was verified; the underlying
capacity assessment is blocked. Null recovery fields preserve the correct cause.
The action-compatibility grader gives no action credit for a null action; it is
separate from diagnostic correctness.

Termination was **model_submission**, rather than a system stopping bound. The
submitted JSON was **148 UTF-8 bytes**. The largest provider response was **472
output tokens**, and the final response used 277 output tokens. The model used
seven of 12 allowed calls and 20 of 32 tool requests, with zero cache hits.

## Redacted-evidence result

Expected: model-submitted insufficient_evidence, no guessed service/fault/action.

The snapshot retained gateway symptoms while dependency telemetry/release history
was unavailable. Seven tool results contained explicit UNAVAILABLE markers.
Gateway capacity, slow-dependency, traffic-spike, deployment, configuration,
certificate and memory-leak assessments all returned unknown.

On call six, the model submitted a six-field abstention with an empty evidence
array and null cause/action fields. The validator accepted it on its first
submission. There was no auth/slow_dependency guess like v6, and no corrective
rejection was needed. This was **model_submission**, not a budget-forced outcome.
The submitted JSON was **120 UTF-8 bytes**. Its complete provider response used
**598 output tokens**, which was the largest in the run and included model text.
The model used six of 12 allowed calls and 20 of 32 tool requests, with zero cache
hits. No recovery recommendation was made.

## Comparison and limits

Each dataset hash matches its corresponding v7 case. Model pin and token/call
bounds also match. The reference schema, prompt and server excerpt handling changed
together; this is one stochastic rerun per case, not a controlled reliability study.

| Case | V7 final outcome | V8 final outcome | Calls V7 → V8 | MCP executions V7 → V8 | Validation rejections V7 → V8 | Token cost V7 → V8 |
|---|---|---|---|---|---|---|
| Traffic | Forced abstention after citation/support rejections | Correct search/traffic_spike, no verified action | 8 → 7 | 16 → 20 | 3 → 0 | $0.066144 → $0.053230 |
| Redacted | Model-submitted abstention | Model-submitted abstention | 6 → 6 | 23 → 20 | 0 → 0 | $0.046017 → $0.042555 |

Both v7 and v8 had zero output truncations in these corresponding runs. The traffic
case used more MCP executions under v8 despite fewer model calls. Neither caching
nor an early server stopping rule contributed to these results.

These two expected outcomes verify the exercised live paths, including ID-only
submission and server-attached provenance. They do not establish generalization,
reliable recovery advice, or performance on other seeds/faults under v8. At completion of this batch, the other
five original fault types remained untested live with this interface. The subsequent
[fresh-seed follow-up](live-v8-fresh-faults.md) records those five cases; larger
repeated/held-out suites remain untested live. No recovery action has been executed or its effect measured.

The runtime code was unchanged during this batch. Its prior offline verification
was **158 tests passed in 3.17 seconds**, including migrated-response replay and
all six narrow synthetic fault assessments; Docker/CI checks passed. Prior live
failures and grades were preserved rather than replaced with these reruns.

## Records

- [Traffic result](../results/live-v8-traffic_spike-2026-10-12-8545540d7b4e.json)
- [Redacted result](../results/live-v8-missing_evidence-2026-10-12-6d8be1c17d98.json)

The records include runtime/source/dataset hashes, configuration, standing per-test
approval, token bounds, usage, diagnostics, counters, termination and reviewed
raw ID-only submissions/server excerpts.

Local full payload capture: `results/traces/live-v8-validation-payloads-7386b991207f.jsonl`.
Full local traces use each result stem plus `.jsonl` in `results/traces/`.
Credential headers are excluded; full payloads/traces remain ignored by Git.
