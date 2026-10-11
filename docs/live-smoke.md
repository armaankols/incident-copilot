# Live smoke — 2026-10-11

Two investigations authorized under a $1 combined cap. Model: `claude-haiku-4-5-20251001`.
Original synthetic simulator cases, seeds 0 and 1, TF-IDF runbook retrieval, real in-memory MCP transport.
This is a smoke check, not evidence of generalization to production incidents.

| Case | Injected service / fault | Result | Model calls | Tool calls | Seconds | Input tokens | Output tokens | Estimated cost |
|---|---|---|---:|---:|---:|---:|---:|---:|
| Seed 0 | auth / bad_deploy | Correct service and fault | 6 | 11 | 27.84 | 27747 | 2792 | $0.041707 |
| Seed 1 | payments / memory_leak | Correct service and fault | 6 | 15 | 34.79 | 27925 | 3608 | $0.045965 |

Combined token cost estimate: **$0.087672**. No failed runs or billing-uncertain runs. Provider reported zero cache-write and cache-read tokens. Costs use [Anthropic list prices](https://platform.claude.com/docs/en/about-claude/pricing): $1/million input and $5/million output; these are usage-derived estimates, not invoice reconciliation.

Limits were 12 calls per investigation, 24,000 counted input tokens per call, 1,000 output tokens per call, 180 seconds per investigation, and no SDK retries. At the verified rates, treating every input token as a 5-minute cache write gives a $0.84 upper token-cost bound for both investigations.

## Evidence and recommendation review

- Seed 0: 2 diagnosis attempts were rejected for nonexact evidence quotes. The accepted diagnosis contained 5 exact quotes from successful observations.
- Seed 1: 2 diagnosis attempts were rejected for nonexact evidence quotes. The accepted diagnosis contained 4 exact quotes from successful observations.

All nine final citation references passed provenance validation. Exact quotations do not prove that the inferred explanation or recommended recovery is correct. Both recommendations passed the existing action/service compatibility grader; no remediation was executed.

Qualitative trace review found unsupported specificity: the memory-leak recommendation assumed the previous stable version was `v3.1.8` and asserted an unbounded memoization implementation; those details were not established by the retrieved telemetry. The bad-deploy recommendation attributed the exception to the metrics migration more strongly than the retrieved correlation supports. These limitations are not captured by the current compatibility score.

Next correctness work: make uncertain mechanisms explicit, obtain a verified rollback target or state that it must be checked, and improve citation-error feedback. Any further live validation requires a new paid-run approval.

Raw structured results: [`live-smoke-2026-10-11-98d7a0333c47.json`](../results/live-smoke-2026-10-11-98d7a0333c47.json). Local full trace: `results/traces/live-smoke-2026-10-11-98d7a0333c47.jsonl` (ignored by Git).
Dataset SHA-256: `a9d9597934386340bffaac1c745e8dbbde69178604caca6485d49bd361faf616`.
Source SHA-256 at run time: `651d81fed98e9a8f2ef408c778de66f267d76328491236c0c16b5a8a0e04a64d`.
