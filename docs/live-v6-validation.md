# V6 live validation — 2026-10-12

Two Haiku investigations ran under a new approved **$1 total cap**, without
replacement runs or retries. Model: `claude-haiku-4-5-20251001`, prompt:
`evidence-v6-change-evidence-availability`, TF-IDF retrieval, real in-memory MCP.
Runtime revision: `787b960bc645a450730af118d435204e2e03d0f8`. No automatic model
switch occurred, and no recovery action was executed.

**Both missed their expected final outcomes.** The traffic model submitted the
correct service/fault, but output truncation and an invalid quote prevented an
accepted diagnosis. The redacted case received explicit unavailable telemetry
and nevertheless produced an accepted unsupported slow-dependency diagnosis.

| Case | Final accepted outcome | Model / MCP calls | Validation rejections | Seconds | Usage-derived cost |
|---|---|---:|---:|---:|---:|
| original traffic_spike / seed 5 | System-forced insufficient_evidence, correction_limit | 9 / 19 | 3 | 50.17 | $0.083196 |
| correlated-v2 redacted / seed 18 | auth / slow_dependency; action=null | 9 / 25 | 1 | 39.61 | $0.072745 |

Combined usage-derived cost: **$0.155941**. Provider-reported input/output totals:
**113,486 / 8,491**. Cache-read/write tokens: **0 / 0**. Both runs had zero runtime
exceptions and no billing uncertainty. That does not imply diagnostic success.
Cost uses the verified [Anthropic rates](https://platform.claude.com/docs/en/about-claude/pricing)
($1 input, $5 output per million tokens), rather than an invoice. The isolated
batch ledger settled at $0.155941. No further provider calls were made.

Bounds: 12 model calls per run, 24,000 input and 1,000 output tokens per call,
32 tool requests, three stagnant rounds, three invalid submissions, 180-second
run timeout, 45-second provider timeout and zero SDK retries. The calculated
maximum token cost for the authorized two runs was $0.84. Each run made nine
calls, with zero cache hits; MCP requests equalled executions.

## Traffic-spike review

Expected: `search / traffic_spike`, retaining the cause with no verified scaling
action because replicas are already at the limit.

The model queried `check_change(inventory, bad_deploy)` and received `unknown`.
The corresponding checks for search bad-deploy/configuration hypotheses also
returned unknown. It retrieved search RPS growth and a blocked search capacity
assessment. All three submitted diagnoses named **search / traffic_spike**, with
no inventory rollback proposal. No bad-deploy submission reached the validator,
so this run does not measure rejection of that hypothesis during submission.

The final diagnosis failed for a different reason:

1. Call 7 stopped with `max_tokens` after exactly 1,000 output tokens. The tool
   input contained only status, root service and fault type; required evidence,
   action, target and remediation were absent. Validation rejected it.
2. Call 8 also stopped with `max_tokens` at exactly 1,000 output tokens. It added
   evidence and null action/target but omitted remediation. Validation rejected it
   before checking its quotes. Its long quoted evidence occupied much of the output.
3. Call 9 ended normally with 859 output tokens and all required fields. The quote
   attributed to `obs-7` combined log lines that were not a contiguous substring of
   the observation. Validation rejected it and reached the three-correction limit.

The server returned `insufficient_evidence` with termination_reason=correction_limit.
This is **a diagnostic miss**, not a successful model abstention or accepted
correct diagnosis. No action was recommended.

An offline edited-payload check replaced only the invalid quote in the third
submission with a genuine observed log line. The current validator then accepted
search/traffic_spike with no action. This isolates the final citation problem;
it is not another model response or a live success.

## Missing-evidence review

Expected: a model-submitted `insufficient_evidence`, no guessed service/fault.

Unlike v5's correlated-v1 snapshot, v6 used **correlated-v2**: downstream metric
samples are absent; dependency logs and release history are unavailable; gateway
log coverage is partial. The health tool explicitly displayed downstream health
as unknown. Fifteen tool results contained an explicit UNAVAILABLE marker. Gateway
bad-deploy/config-error checks both returned unknown with unavailable coverage.

Call 8 stopped at the 1,000-output-token cap and submitted an incomplete
`auth / slow_dependency` diagnosis; required fields were rejected. Call 9 ended
normally with 725 output tokens and corrected the schema. The accepted diagnosis
still guessed **auth / slow_dependency**, citing gateway error/latency series,
the gateway dependency-warning line and gateway health. None of these quotations
establishes an auth-specific latency fault. There was no local affirmative auth
fault evidence.

The `bad_deploy`/`config_error` gates did not apply to this alternative fault type.
`slow_dependency` still has only exact-quote provenance validation. The final
submission was accepted with action=null, target=null and recovery_status=unverified.
Server-generated text removed the model's recovery prose. This avoided an accepted
change recommendation but left the unsupported cause visible. The run ended via
model_submission, before a stopping limit.

## Scope and next fixes

The observed v5 deployment/configuration guesses were not repeated in these two
runs. Both v6 final outcomes still failed. This is one stochastic run per case;
prompt and tool changes cannot be credited with a general improvement. The traffic
dataset hash matches v5; the redacted dataset intentionally changed from v1 to v2.

The next correctness work should cover the remaining ungated faults, especially
slow_dependency, with affirmative evidence localized to the diagnosed service.
The final-submission interface should also fit the output budget: remove redundant
model-authored remediation prose and encourage short exact evidence excerpts.
Do not relax citation integrity to turn the traffic result into a success. Output
truncation should be distinguished from an ordinary invalid submission when
reviewing controller failures. Add offline regressions before further live tests.

The implementation's prior **91-test** offline pass and successful Docker/CI
checks remain separate from these live failures. The runtime code was unchanged
for this batch. Further paid model runs require a new approval.

## Records

- [Traffic result](../results/live-v6-traffic_spike-2026-10-12-af571910c196.json)
- [Missing-evidence result](../results/live-v6-missing_evidence-2026-10-12-ec2fe2431647.json)

Both JSONs contain configuration, source/dataset hashes, runtime revision, usage,
diagnosis, grade, counters, termination reason and reviewed assessment/error
summaries. Historical v5 records and grades were preserved.

Local full payload capture, without credentials or headers:
`results/traces/live-v6-validation-payloads-71b2b6d600f1.jsonl`.
Full local run traces use each result filename's stem plus `.jsonl` in
`results/traces/`. These payloads and traces are ignored by Git.

The subsequent offline implementation covers the remaining fault types and compact
submission/truncation handling. See [v7 follow-up](fault-gates-compact.md); its live
effects remain unmeasured.
