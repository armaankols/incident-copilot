# Certificate ownership and replica headroom — 2026-10-11

The live certificate investigation confused the caller reporting a TLS failure with its peer; the traffic-spike investigation recommended scaling while the autoscaler was already at its maximum. The original live records and outcome scores remain unchanged.

## Changes

Two new MCP tools return structured, log-backed assessments. They consume simulator logs and its current clock, never the injected root-service or fault labels. They make no network probes and execute no recovery actions.

- `check_certificate(service)` requires a service-local certificate-expiry notice plus recent caller errors verifying that peer. The latest local forecast must indicate expiry at or before the scenario clock. Missing corroboration yields `unknown`; inconsistent forecasts or a later recorded renewal yield `conflicting`. Caller errors alone and normal application metrics do not establish certificate ownership or health.
- `check_capacity(service)` reads the latest service-specific autoscaler observation from the last five minutes. At/above the maximum yields `blocked`; an explicit below-limit snapshot yields `headroom`; missing, stale or invalid telemetry yields `unknown`; inconsistent snapshots at the same timestamp yield `conflicting`. A later blocked observation overrides an older available snapshot. Headroom does not establish infrastructure permissions, resource availability or downstream capacity.

The agent records the MCP tool that produced each successful observation. The diagnosis validator accepts certificate renewal only when the diagnosed target has a cited `expiry_supported` certificate assessment; it accepts scaling only with a cited `headroom` capacity assessment. Text from a runbook or another tool cannot impersonate these checks. A negative/conflicting assessment cannot be omitted from citations to evade the gate. Unknown evidence leaves those actions unverified: the model can investigate a compatible alternative or abstain. At the call limit, the graph returns insufficient evidence without another model call.

The prompt and TLS/traffic runbooks explain caller-versus-peer reasoning, normal application metrics during failed TLS verification, and capacity limits. Prompt version is `evidence-v4-operational-checks`. Malformed-diagnosis feedback now identifies missing and unexpected fields. Server-generated conservative recommendation prose remains in place.

## Measured offline verification

- 53 tests passed in 2.08 seconds. New checks cover caller/peer ownership, absent/stale/future evidence, renewed or conflicting certificates, latest/contradictory capacity observations, tool provenance, required citations, target matching and conflicting check omission.
- Scripted investigations through real MCP/LangGraph rejected a caller-based certificate diagnosis and accepted a supported peer; rejected scaling at the limit and accepted a compatible rate-limit recommendation; exhausted unknown ownership into abstention with no extra model call. These are scripted integration checks, not live model diagnoses or recovery executions.
- Both public saved failure payloads were rejected when supplemented with fresh assessments of their proposed targets: `orders` ownership was unknown and `search` headroom was blocked. This check uses saved quoted fragments and freshly generated original-case telemetry, not replayed live model responses.
- TF-IDF recall@1 and recall@3 remained 14/14; optional FastEmbed was skipped because it is absent. Existing benchmark fixture checks and compilation passed.

No paid API calls were made during implementation. Subsequent authorized live validation is recorded in [live-v4-validation.md](live-v4-validation.md): certificate ownership was correct, blocked scaling was rejected, and stopping/diagnostic-completion problems remained. Effects on general live diagnosis accuracy or retry rates remain unmeasured. These narrow parsers recognize this demo's telemetry formats; unrecognized formats remain unknown and must not be treated as evidence of health or available capacity. They do not constitute production certificate verification or a complete recovery-feasibility assessment. Other fault diagnoses still rely on exact-quote provenance and the model's inference; a compatible alternative action still requires service-policy verification before execution.
