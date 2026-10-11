# Recommendation grounding — 2026-10-11

The two Haiku smoke investigations produced correct service/fault diagnoses but included unsupported recommendation details and required exact-quote corrections. This follow-up changes future investigations; original live result files and run hashes are preserved.

## Changes

- Accepted recommendation prose comes from conservative server policies keyed by validated action and target. The model still selects those fields, but its submitted free-form remediation is replaced without mutating the recorded response. Recommendations identify prerequisite checks, do not name a release version, and make no claim about an implementation mechanism.
- Rollback advice requires checking a previous healthy release in deployment records and schema/configuration compatibility. All advice remains a recommendation; no action is executed. Abstentions receive standard missing-evidence advice rather than provider recovery instructions.
- Incompatible fault/action combinations and targets other than the diagnosed root service are rejected. This is a restricted simulator policy, not a general solution for incidents requiring recovery actions on another service.
- Citation errors identify the failing observation and explain how to copy an exact contiguous excerpt. Unknown IDs list successful observations. Rejected submissions can be corrected within the existing call budget.
- Prompt `evidence-v3-policy-remediation` distinguishes correlation from established mechanisms, prohibits inferred rollback versions and invented thresholds, and explains corrected resubmission. Bad-deploy and memory-leak runbooks now include the same cautions. Model notes are labeled unverified in the UI.

## Measured offline verification

- 36 tests passed in 1.97 seconds, including adversarial unsupported-version advice, incompatible actions, wrong targets, abstention advice, source-specific citation feedback, and correction through the real graph/MCP transport.
- TF-IDF retrieval recall@1 and recall@3 remained 14/14; optional FastEmbed was skipped because it is absent.
- Existing benchmark fixture checks passed.
- Both saved live diagnoses were revalidated against their original local observations offline: all nine accepted citations and both selected actions were retained, while free-form advice was replaced. No new model response was generated and the saved live experiments were not modified.

No additional paid API calls were made. Changes to live accuracy, latency, cost and citation retry frequency remain unmeasured. Exact quotation validates provenance; it does not establish semantic support for the diagnosis. Conservative advice requires service-policy verification and does not provide a verified deployment-specific recovery plan.
