# V8 edge-case live validation — 2026-10-12

Seven sequential Haiku investigations met their expected diagnostic outcomes:
six correct service/fault diagnoses and one model-submitted abstention on missing
telemetry. All seven stopped with `model_submission` and had zero validation
rejections, output truncations, runtime errors or billing uncertainty.

Model: `claude-haiku-4-5-20251001`; prompt:
`evidence-v8-observation-id-submission`; TF-IDF retrieval; real in-memory MCP.
Runtime revision: `3d13369` (full revision in each result). This includes the
assessment-backed log-excerpt fix. Runtime code was unchanged during this batch.
No Sonnet switch, SDK retry, replacement test or recovery execution occurred.

## Cases and measured outcomes

All cases use `correlated-v2`, base seed 2, with one selected case per original
fault type plus missing evidence. The seven scenario seeds were absent from prior
saved live runs. Case selection was fixed before the batch:

- Paraphrased signatures: memory leak and traffic spike.
- Healthy-service decoys: bad deployment and slow dependency. These add a recent
  INFO diagnostic-drill message to a healthy service; they are mild decoys.
- Recovered historical errors: configuration error and certificate expiry. These
  add an older ERROR diagnostic-drill message to a healthy service; the actual
  root fault remains active. They do not represent recovery of the true root fault.
- Missing telemetry: gateway symptoms remain, dependency telemetry and deployment
  history are explicitly unavailable; expected outcome is insufficient_evidence.

| Variant / seed | Accepted outcome | Recommended action | Model / MCP calls | Seconds | Usage-derived cost |
|---|---|---|---:|---:|---:|
| paraphrase / 2001 | search / memory_leak | None | 6 / 12 | 20.82 | $0.039318 |
| paraphrase / 2005 | search / traffic_spike | None | 5 / 13 | 18.47 | $0.034189 |
| healthy_decoy / 2006 | search / bad_deploy | rollback | 4 / 7 | 10.14 | $0.023173 |
| healthy_decoy / 2008 | postgres / slow_dependency | None | 9 / 17 | 28.53 | $0.069134 |
| recovered_error / 2015 | inventory / config_error | restore_config | 4 / 11 | 15.45 | $0.027572 |
| recovered_error / 2016 | inventory / cert_expiry | renew_certificate | 5 / 13 | 15.39 | $0.033831 |
| redacted / 2018 | insufficient_evidence | None | 8 / 25 | 26.65 | $0.059857 |

Combined usage-derived token cost: **$0.287074**. Provider-reported input/output
totals: **229,824 / 11,450**. Cache-read/write tokens: **0 / 0**. All **41** captured
response usages reconcile with saved per-run totals. There were **98** MCP
executions/requests and zero cache hits. The largest response used **545** output
tokens, below the 1,000-token response limit. The isolated ledger settled at
$0.287074. Costs use [Anthropic list prices](https://platform.claude.com/docs/en/about-claude/pricing)
verified on 2026-10-12, not reconciled invoices.

## Evidence and stopping review

Each of the six diagnoses cited a matching service/fault assessment with supported
status (`expiry_supported` for certificate expiry). All **16/16** attached excerpts
are exact substrings of selected successful observations. There were no rejected
wrong-service or wrong-fault proposals, and no final guesses on the redacted case.
The missing-evidence investigation stopped voluntarily on call eight, before the
12-call cap, rather than by a forced stopping rule.

The healthy-decoy cases correctly identified search/bad_deploy and postgres/
slow_dependency, while the recovered-error cases correctly identified inventory/
config_error and inventory/cert_expiry. The traffic case retained search/
traffic_spike with null recovery fields after a blocked capacity assessment.
Rollback, configuration restoration and certificate renewal were conservative
server-generated recommendations. Their versions, execution plans and recovery
effects were not verified; no change was executed.

**Remaining presentation limitation:** the paraphrased memory case correctly
selected search's supported fault assessment and memory summary, but its third
selected observation is a gateway log with a generic successful-retry excerpt.
The matching memory assessment has no record in that particular gateway
observation, so the fallback remains a recent actual line. The excerpt fix repairs
the earlier OOM-versus-unrelated-error selection when a matching record is present;
it does not make arbitrary supplemental model source selections fault-specific.
This did not bypass the required diagnostic assessment.

## Scope and deployment

These seven selected synthetic cases are a small smoke batch, not the full
24-case challenge suite, repeated-seed reliability testing, or production incidents.
The paraphrases and diagnostic gates share known simulator vocabulary. No causal
intervention or recovery execution was measured. Previous failures remain recorded.

Standing authorization was **up to $0.50 per test**. Each test's verified conservative
bound was **$0.42**: 12 calls, 24,000 input and 1,000 output tokens per call, pricing
all input as 5-minute cache writes. The seven-case calculated maximum was $2.94;
the isolated ledger cap was $3.50. Provider timeout was 45 seconds, run timeout
180 seconds, zero SDK retries. No additional paid investigations were made.

Offline checks after the excerpt change: **171 tests passed in 3.25 seconds**;
3,528 narrow service/fault assessments and the migrated-reference replay passed.
Revalidating the five previous live submissions changed only the memory log excerpt
to OOMKilled, preserved all diagnoses/recovery fields, and kept 15/15 exact source
excerpts, with zero provider calls. See [excerpt verification](excerpt-verification.json).

The updated Linux ARM64 image passed five HTTP routes, missing-key rejection
(503), UID 10001 execution, persistent ledger/replay checks and root-owned mount
initialization. See [container verification](container-verification-excerpt.json).
No public deployment has occurred. Deployment account/destination access and
hosting budget are still required. The user requested these edge-case tests before
deployment; broader challenge/recovery experiments can follow deployment.

## Records

- [correlated-v2/paraphrase/2001](../results/live-v8-edge-paraphrased_memory-2026-10-12-535a39be1b0d.json)
- [correlated-v2/paraphrase/2005](../results/live-v8-edge-paraphrased_traffic-2026-10-12-102febf5812e.json)
- [correlated-v2/healthy_decoy/2006](../results/live-v8-edge-healthy_decoy_bad_deploy-2026-10-12-6fe371dfa1ba.json)
- [correlated-v2/healthy_decoy/2008](../results/live-v8-edge-healthy_decoy_slow_dependency-2026-10-12-565a7be5c36e.json)
- [correlated-v2/recovered_error/2015](../results/live-v8-edge-recovered_config_error-2026-10-12-b05d34b92e6a.json)
- [correlated-v2/recovered_error/2016](../results/live-v8-edge-recovered_cert_expiry-2026-10-12-14707fd79e76.json)
- [correlated-v2/redacted/2018](../results/live-v8-edge-missing_evidence-2026-10-12-e689ff96783b.json)

Records include source/dataset hashes, full runtime revision, approved bounds,
usage, counters, finalization, raw ID-only submissions and reviewed excerpts.
Local full payload capture:
`results/traces/live-v8-edge-cases-payloads-2c68299a49ab.jsonl`.
Full traces use each result stem plus `.jsonl` in `results/traces/`.
Credentials and headers are excluded; full payloads/traces are ignored by Git.
