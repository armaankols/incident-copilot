# Diagnosis/recovery separation and stopping — 2026-10-12

The v4 traffic run could identify search/traffic_spike in proposed diagnoses but could not submit a supported recovery action; its final abstention discarded the cause. The redacted run queried unavailable telemetry until the model-call limit. These changes address both without new paid model calls. Historical live outcomes and hashes are unchanged.

## Diagnosis and recovery

A diagnosed outcome can now retain root service, fault and exact evidence with action=null and target=null. The server adds recovery_status and recovery_reason; the model cannot supply those output fields. Recovery is reported separately as recommended, blocked, unverified or unavailable. Recommendation availability does not prove that an action is safe or authorized to execute.

If a structurally valid diagnosis proposes scaling, the capacity gate still checks the diagnosed service and cited tool provenance. Missing, conflicting, uncited or blocked headroom removes the action/target and substitutes conservative server advice while preserving the diagnosis. No alternative action is guessed. Invalid quotations, incompatible actions and wrong recovery targets remain errors. Certificate ownership/expiry remains a diagnosis requirement even when no renewal is proposed, so null recovery cannot bypass that check.

The existing grader already scores service/fault independently from compatible recovery actions. A correct diagnosed outcome with no action earns diagnosis credit but no action-compatibility credit. The UI presents recovery availability and the reason investigation ended separately from the cause.

## Bounded investigation

- Identical successful queries, including equivalent omitted/default parameters, reuse their original observation IDs within the fixed synthetic snapshot. Errors are not cached. Recorded tool executions, attempted requests and cache hits are separate counters.
- Three consecutive rounds without new successful tool output stop the graph. Fresh output resets that counter; a repeated result with changed query arguments still contributes no new information.
- Three invalid submissions stop further correction rounds. Accepted diagnosis submissions take precedence over stopping, including a server-normalized diagnosis with unavailable recovery.
- At most 32 non-submission tool requests are allowed per investigation. An oversized response batch can contain additional attempted requests, which are counted and closed with skipped tool results without execution. No tools execute after a diagnosis is accepted in that same response batch.
- The existing 12-model-call bound remains. Each call receives remaining model/query/correction budgets. Stopping does not make an extra forced model call or infer a diagnosis.

New results persist termination_reason, configured limits and execution/cache/rejection counters. Summaries distinguish model-submitted abstention from server-forced abstention and count correct diagnoses without recovery. The report uses those fields automatically for new experiments; historical experiments retain their original records or derived trace reviews. Prompt version: evidence-v5-diagnosis-recovery-stopping.

## Measured offline checks

- 68 tests passed in 2.29 seconds. Checks include preserving a cause with null recovery, independent grading, certificate ownership with no action, removal of blocked scaling, default-aware caching and citable cached observations, reset on new output, correction limits, oversized tool batches and finalization-origin accounting.
- In a scripted repeated-query check, four model responses caused one MCP execution and three cache hits, then stopped for stagnation without another model call.
- The previous missing-evidence run's recorded tool-use schedule was exported into a credential-free fixture: 12 responses and 49 queries. Offline replay under the new policy consumed seven scripted responses and executed 32 MCP calls; two further requests in the last batch were skipped at the tool limit. There were zero cache hits in this schedule, so its reduction came from the query bound, not caching. This is not a new model investigation or evidence of a live cost/accuracy improvement.
- TF-IDF recall@1 and recall@3 remained 14/14; optional FastEmbed was absent. Existing benchmark fixture checks, recorded-query replay checks, Python compilation and JavaScript syntax validation passed. The new UI labels were not manually browser-verified.

Replay artifact: [stopping.json](../results/stopping.json). Reproduce offline with `python -m evals.stopping_eval`; CI runs it alongside existing checks. Source and fixture hashes are saved with the artifact. Only tool-use blocks were exported; provider prose and credential headers are excluded.

## Limits

Exact references establish provenance, not semantic correctness of every inferred cause. These stopping limits trade completeness for bounded investigation: a legitimate case needing more queries or corrections may abstain earlier. Caching assumes the fixed simulator snapshot and would require a freshness policy for changing live telemetry. No recovery is executed, and live model effects on diagnosis, latency, tokens, cost or spontaneous stopping remain unmeasured.
