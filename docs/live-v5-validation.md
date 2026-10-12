# V5 live validation — 2026-10-12

Two investigations authorized under a $1 total cap: original traffic-spike case 5 and correlated-v1 redacted case 18. Both used the same pinned model as every previous live investigation: `claude-haiku-4-5-20251001`. Prompt: `evidence-v5-diagnosis-recovery-stopping`, TF-IDF retrieval and real in-memory MCP transport. There is no automatic Sonnet fallback or escalation; the UI/request or CLI must explicitly choose another model. No recovery actions were executed.

**Neither investigation met its expected diagnostic outcome.** Genuine quotations passed validation, but the model's causal inferences were unsupported.

| Case | Accepted model diagnosis | Accepted recommendation | Model / tool calls | Seconds | Estimated cost |
|---|---|---|---:|---:|---:|
| traffic_spike / seed 5 | inventory / bad_deploy | rollback / inventory | 10 / 21 | 42.66 | $0.091092 |
| missing_evidence / seed 18 | gateway / config_error | restore_config / gateway | 8 / 24 | 34.69 | $0.062069 |

**Combined usage-derived token cost: $0.153161**, below the approved $1 cap. Input/output totals: 115,366 / 7,559. Cache-read/write tokens were zero. Cost uses provider-reported usage at [Anthropic list prices](https://platform.claude.com/docs/en/about-claude/pricing), not invoice reconciliation. Both runs had zero exceptions and no billing uncertainty; that is runtime completion, not diagnostic success. Bounds were 12 model calls, 24,000 input tokens and 1,000 output tokens per call, 32 allowed tool requests, three stagnant rounds and three invalid submissions, with no SDK retries. Worst-case combined token cost at verified rates was $0.84.

## Failure review

- **Traffic spike:** expected search / traffic_spike, with scaling left unverified/blocked or no action proposed. Instead, the model blamed an inventory metrics-client deployment preceding the search traffic increase and selected rollback of inventory. Its citations included the genuine inventory deployment record, search RPS/CPU growth, search autoscaler-limit/load-shedding logs and a blocked search capacity assessment. Those quotes do not establish that the inventory release caused the surge. One quotation error was corrected; the final submission was accepted. The capacity gate did not apply to the final rollback proposal because the model selected a different cause/action.
- **Missing evidence:** expected insufficient_evidence with no root-service or action guess. Instead, the model inferred gateway / config_error from gateway symptoms, flat downstream metrics and the explicit log `upstream requests failing; dependency telemetry unavailable`. It treated missing/frozen telemetry as evidence of a configuration cause without a configuration record or fault-specific error. All four quotations were genuine, and the submission was accepted with restore_config / gateway. There were no validation rejections.

Both ended with termination_reason=model_submission before any stopping bound fired. Neither repeated an identical query (zero cache hits). Traffic used 21 tool requests/executions; missing evidence used 24. The controls do not prevent unsupported conclusions that arrive before their limits.

The accepted recovery_status=recommended labels mean compatible recommendations with policy checks still required; they are not proof of a correct cause or verified safe recovery. Server-generated conservative wording cannot repair an incorrect root/fault inference. Exact-quote provenance, action compatibility and the targeted certificate/capacity checks are insufficient to validate these two diagnoses.

## Measured comparison with v4

The dataset hashes match each corresponding v4 case. Model pin and seeds also match; prompt, schema, tool budgets and validation behavior changed together. These are single stochastic reruns, not a controlled estimate of improvement.

| Case | V4 outcome | V5 outcome | Model calls V4 → V5 | Tool executions V4 → V5 | Seconds V4 → V5 | Cost V4 → V5 |
|---|---|---|---|---|---|---|
| Traffic spike | Model-submitted abstention; no action | Wrong inventory/bad_deploy diagnosis; rollback recommended | 12 → 10 | 21 → 21 | 56.09 → 42.66 | $0.131559 → $0.091092 |
| Missing evidence | Budget-forced abstention; no action | Unsupported gateway/config_error diagnosis; restore_config recommended | 12 → 8 | 49 → 24 | 39.24 → 34.69 | $0.110672 → $0.062069 |

Fewer calls and lower observed costs in these reruns do not demonstrate better correctness or successful early abstention. Neither new run used caching or triggered a server stopping rule. The prior offline schedule replay remains a measure of controller behavior on fixed responses, not proof of new model behavior.

## Next correctness priority

Require affirmative, service-specific evidence for a proposed fault, particularly bad_deploy and config_error. A nearby deployment, caller symptoms, normal-looking metrics or unavailable telemetry alone must not qualify as proof of the cause. Preserve unsupported hypotheses as hypotheses and abstain when diagnostic evidence is insufficient. Add offline regressions using these saved failed submissions before another live comparison or deployment. A stronger model could be evaluated separately with a fresh budget approval; no automatic escalation occurred here.

## Records

The runtime code was unchanged for these tests. 68 offline tests passed in 2.09 seconds, demonstrating implementation regressions pass while live diagnosis correctness remains unresolved. No additional investigations were made to replace the failures.

Full local payload capture: `results/traces/live-v5-validation-payloads-b8e77362401c.jsonl` (ignored by Git; credential headers excluded).
- [live-v5-traffic_spike-2026-10-12-2fa0a38e57f9.json](../results/live-v5-traffic_spike-2026-10-12-2fa0a38e57f9.json) includes source/dataset hashes, usage, diagnosis, recovery status, counters and termination reason. Local full trace: `results/traces/live-v5-traffic_spike-2026-10-12-2fa0a38e57f9.jsonl`.
- [live-v5-missing_evidence-2026-10-12-a09d83c85244.json](../results/live-v5-missing_evidence-2026-10-12-a09d83c85244.json) includes source/dataset hashes, usage, diagnosis, recovery status, counters and termination reason. Local full trace: `results/traces/live-v5-missing_evidence-2026-10-12-a09d83c85244.jsonl`.
