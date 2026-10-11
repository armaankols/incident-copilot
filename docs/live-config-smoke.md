# Configuration-error live smoke — 2026-10-11

One new Haiku investigation authorized under a $0.50 cap. Original synthetic case index 3 (seed 3), with a configuration fault in `orders`. This was a new fault type, not a repeat of the previous bad-deploy or memory-leak cases. Model: `claude-haiku-4-5-20251001`; prompt: `evidence-v3-policy-remediation`; TF-IDF runbook retrieval and real in-memory MCP transport.

## Measured result

| Measurement | Result |
|---|---|
| Service / fault | orders / config_error; both correct |
| Selected action / target | restore_config / orders; compatible |
| Elapsed time | 22.93 seconds |
| Model / tool calls | 6 / 13 |
| Input / output tokens | 26603 / 1981 |
| Cache-write / cache-read tokens | 0 / 0 |
| Usage-derived token cost | $0.036508 |
| Citation validation | 5 exact references; 0 rejected submissions |
| Run errors / billing uncertainty | None / false |

Cost uses provider-reported tokens and [Anthropic list rates](https://platform.claude.com/docs/en/about-claude/pricing), not invoice reconciliation. Limits were 12 model calls, 24,000 counted input tokens and 1,000 output tokens per call, 180 seconds per investigation, and no SDK retries; worst-case token cost at those rates was $0.42.

The model retrieved the `orders` deployment/configuration record (`db.pool.max=5`, timeout 3000ms), repeated connection-pool exhaustion logs, gateway upstream errors and time-series evidence. The accepted service and fault matched injected ground truth. No recovery action was executed.

The provider proposed restoring the previous pool size or increasing it. The server replaced that prose with its conservative configuration policy: compare the active configuration with a verified healthy configuration, confirm compatibility and the rollback procedure, and check configured SLOs after an approved change. No configuration revision or replacement pool size was verified or supplied in the accepted recommendation.

Unlike the prior two smoke runs, this case submitted all quotations correctly on its first diagnosis attempt. These runs use different cases and prompt/validator versions: this is not a controlled before/after comparison and does not establish a lower retry rate or improved general accuracy. Live coverage is now one case each for bad_deploy, memory_leak and config_error; slow_dependency, cert_expiry and traffic_spike remain untested with a live model.

## Reproduction and records

The harness now supports selecting an offset without running earlier cases. The equivalent paid command is:

```sh
.venv/bin/python -m evals.run_evals --agent llm --suite original --seed 0 --case-offset 3 --n 1 --concurrency 1 --max-steps 12 --save-traces
```

Load the local credentials into that process first. This command makes paid API calls and is not part of offline CI; repeating it requires another budget approval.

- [Structured result](../results/live-config-2026-10-11-efc42552331a.json) includes configuration, diagnosis, usage and source/dataset hashes.
- Full local trace: `results/traces/live-config-2026-10-11-efc42552331a.jsonl` (ignored by Git).
- Full local request/response payloads: `results/traces/live-config-payloads-ecf2b2871211.jsonl` (ignored by Git; no credential headers captured).
- Offline verification after adding case selection: 38 tests passed in 2.04 seconds; benchmark fixture checks passed. Selection tests verify that offset 3 selects only the intended configuration case and preserves the original telemetry.

No other paid investigation was run under this approval.
