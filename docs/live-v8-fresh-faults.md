# V8 fresh-seed fault validation — 2026-10-12

Five sequential Haiku investigations correctly identified the injected service and
fault on their first final submission. All stopped with `model_submission`, with
zero validation rejections, output truncations, runtime errors or billing uncertainty.
These are five synthetic smoke cases, not an estimate of production reliability.

Model: `claude-haiku-4-5-20251001`; prompt:
`evidence-v8-observation-id-submission`; TF-IDF retrieval; real in-memory MCP.
Runtime revision: `65fcbbcff674df2fc7874906cb2ee82cd1c1ea30`.
Code was unchanged during the batch. Seeds 1000–1004 were absent from previous
saved live runs, but use the same original simulator templates. They are not an
independent fault corpus. No Sonnet switch, SDK retry or replacement test occurred.

| Case / seed | Accepted service / fault | Recommended action | Model / MCP calls | Seconds | Usage-derived cost |
|---|---|---|---:|---:|---:|
| bad_deploy / 1000 | auth / bad_deploy | None | 5 / 12 | 18.61 | $0.035465 |
| memory_leak / 1001 | orders / memory_leak | restart | 5 / 12 | 17.70 | $0.032423 |
| slow_dependency / 1002 | payments / slow_dependency | None | 8 / 19 | 29.77 | $0.064760 |
| config_error / 1003 | payments / config_error | None | 4 / 10 | 11.77 | $0.025144 |
| cert_expiry / 1004 | auth / cert_expiry | renew_certificate | 3 / 6 | 10.10 | $0.017638 |

Total usage-derived cost: **$0.175430**.
Provider-reported input/output tokens: **138,165 / 7,453**;
cache-read/write tokens: **0 / 0**.
All **25** captured response usages reconcile with the five saved totals. There
were **59** MCP executions and **60** requests, including one cache hit in the
slow-dependency investigation. The isolated ledger settled at $0.175430.
Costs use [Anthropic list prices](https://platform.claude.com/docs/en/about-claude/pricing),
verified on 2026-10-12; they are not reconciled invoices.

## Evidence and recovery review

Each final submission contained three observation IDs. All **15/15** server-attached
excerpts are exact substrings of the selected successful observations. Every
accepted cause cited the matching service/fault assessment with a supported status
(`expiry_supported` for the certificate case). No wrong-cause submission was made.

- Bad deployment: cited auth's supported release-linked assessment, a local build
  exception and gateway's auth failures. No rollback version or action was proposed.
- Memory leak: cited orders' supported fault assessment and memory summary;
  the assessment contains OOM, recent GC pressure, rising memory and restart evidence.
  A controlled restart was recommended, with service-policy checks still required.
- Slow dependency: cited payments' supported assessment, its saturated worker pool
  and orders' timeout calling payments. A repeated request used the cached observation.
  No action was proposed.
- Configuration error: cited payments' supported release/configuration assessment,
  connection-pool exhaustion and error-rate summary. No configuration values were
  invented as recovery instructions; no action was proposed.
- Certificate expiry: cited auth's ownership/expiry assessment and gateway impact
  metrics. Certificate renewal was recommended, with rotation procedure and policy
  verification still required.

`recovery_status` was `recommended` for restart and renewal, and `unverified` for
all three null-action diagnoses. Neither recommendation was executed, and no
recovery effect was measured. Action compatibility is separate from diagnosis
accuracy and does not establish that a recommendation is safe to execute.

**Observed excerpt limitation:** memory evidence `obs-9` includes an OOMKilled
record followed by an unrelated malformed-request error. The server's latest-line
selection displays the later malformed-request record, even though `obs-10`
independently provides the required memory-leak support. Its excerpt is exact but
poorly chosen for explaining this diagnosis. Source provenance alone does not
ensure relevance; improve log excerpt selection before presenting this as polished
diagnostic evidence. The current result and raw selection are preserved.

## Scope and next checks

Together with the [prior traffic/redacted pair](live-v8-validation.md), v8 now has
seven live smoke investigations meeting their expected diagnostic outcomes:
one per original fault type plus one missing-evidence case. Only the new five
cases use seeds 1000–1004; this is not a balanced repeated-seed benchmark.
Misleading telemetry and paraphrased/recovered-log variants remain to be tested
live under v8. These should follow the excerpt improvement, before public deployment.

Standing authorization is **up to $0.50 per test**. Before creating each provider
client, this batch checked the **$0.42/test** conservative token bound: 12 calls,
24,000 input and 1,000 output tokens per call, charging all input at the 5-minute
cache-write rate. Five tests have a $2.10 calculated maximum; the isolated ledger
cap was $2.50. The run timeout was 180 seconds, provider timeout 45 seconds,
with zero SDK retries. No extra paid investigations were made.

Offline checks in this pass: **158 tests passed in 3.48 seconds** and benchmark
fixture checks passed. Previous Docker verification remains recorded in
`container-verification-v8.json`; no new container test or public deployment was
performed in this batch. Deployment account access is still needed.

## Records

- [bad_deploy, seed 1000](../results/live-v8-fresh-bad_deploy-2026-10-12-9325ca477558.json)
- [memory_leak, seed 1001](../results/live-v8-fresh-memory_leak-2026-10-12-25eb65130926.json)
- [slow_dependency, seed 1002](../results/live-v8-fresh-slow_dependency-2026-10-12-fe10f352563a.json)
- [config_error, seed 1003](../results/live-v8-fresh-config_error-2026-10-12-0ae903125704.json)
- [cert_expiry, seed 1004](../results/live-v8-fresh-cert_expiry-2026-10-12-c4ff87345fd9.json)

Each result includes source/dataset hashes, runtime revision, budget approval,
limits, usage, finalization, raw model submissions and reviewed exact excerpts.
Local full payload capture:
`results/traces/live-v8-fresh-faults-payloads-1e08230fa5a9.jsonl`.
Full local traces use each result stem plus `.jsonl` in `results/traces/`.
Credentials and headers are excluded; payloads and full traces are ignored by Git.
