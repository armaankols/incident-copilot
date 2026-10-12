# Local verification — updated 2026-10-12

Working directory: `/Users/armaankolsawala/IdeaProjects/incident-copilot`.
The initial inspection found no Git repository or applicable AGENTS.md. Git is
now initialized and tracks `armaankols/incident-copilot` on GitHub. Original source/review
copies remain outside this workspace.

Python 3.12.15 is installed at `/opt/homebrew/bin/python3.12`; `.venv` is ready.
The user installed dependencies from a terminal outside the restricted shell.
`requirements.lock` pins 72 runtime packages; `requirements-dev.lock` pins 76
packages, including the development dependencies. Locks have no wheel hashes.
Twenty-two authorized live smoke investigations completed by 2026-10-12. No deployment
has been performed. Standing API-test approval for this collaboration is up to
$0.50 per test (user instruction, 2026-10-12). Before each test, verify a conservative
token-cost bound; proceed without another API-budget confirmation within $0.50,
and ask if the test requires a higher or unverified bound.

Measured on Python 3.12.15:

- `python -m pytest -q tests`: 158 passed (2026-10-12; 3.17 seconds).
- `python -m pip check`: no broken requirements.
- `python -m evals.retrieval_eval`: TF-IDF recall@1 and recall@3 both 14/14;
  optional FastEmbed skipped because it is not installed.
- `python -m compileall -q copilot app evals tests scripts`: exit 0.
- `python scripts/check_benchmarks.py`: exit 0.

The tests exercise real in-memory MCP transport and the LangGraph loop, forged
citation rejection, exhausted-budget abstention without an extra model call,
usage/trace preservation after model failure, cancellation settlement and saved
background replays. A 54-case parity check compares rule predictions and call
counts through direct log search and real MCP transport.

The regression checks cover atomic admission from independent SQLite connections,
restart persistence, concurrency and rate limits, uncertain and partial settlement,
malformed/forged diagnosis evidence, abstention, unknown model prices and failure
summary accounting. At $1.99 spent against $2, 20 concurrent $0.25 reservations
admitted zero requests. These are ledger checks, not end-to-end HTTP load tests.

Measured offline baselines were reproduced on Python 3.12.15:

| Baseline | Dataset | Correct | Notes |
|---|---|---:|---|
| Latest deploy | Original | 3/60 | Service and fault |
| Tailored log rules | Original | 60/60 | Direct simulator log search |
| Same log rules | correlated-v1 | 8/24 | Includes six correct redacted-evidence abstentions |
| Same rules over MCP | Original | 60/60 | Real in-memory client/server transport |
| Same rules over MCP | correlated-v1 | 8/24 | Six required abstentions correctly returned |

Each experiment saves configuration, source hash, records and elapsed times under
`results/`. Subsequent code changes do not retroactively change those run hashes.
Previously supplied results are preserved under `results/archive/` and excluded
from the current report. The local app now runs with elevated execution permission. Chrome displayed the
initial offline replay and evidence controls, and restored a completed scripted
run from its saved URL. The user reported active-run reload, partial error traces and dropdown checks
working on 2026-10-06 using the offline fixture on port 8002. That fixture has no
provider adapter and deliberately fails after an observation.

Docker CLI and Colima were installed through Homebrew. The Linux/ARM64 container
built from pinned runtime dependencies. The isolated smoke check verified:

- HTTP 200 for health, HTML, JavaScript, configuration and the bundled replay.
- HTTP 503 for investigations without API credentials.
- Uvicorn/PID 1 runs with UID 10001.
- A synthetic $0.10 ledger charge and saved replay survive restart.
- A root-owned mount directory is repaired on startup before privileges drop.

The test resources were removed. The image fingerprint and platform are in
`container-verification.json`. No provider spending occurred during the container checks.

The versioned recovery lookup benchmark returned 12/12 exact policies with
TF-IDF and 0/12 without retrieval. Both modes correctly abstained on all three
unknown versions. This is an offline structured-reader ablation over small,
author-written synthetic fixtures; it is not a live-model comparison.

Live-model smoke results, token usage, citation retries and qualitative limitations
are recorded in [live-smoke.md](live-smoke.md). Latest offline test run: 158 passed
in 3.17 seconds on 2026-10-12. Recommendation/citation checks are recorded in
[recommendation-grounding.md](recommendation-grounding.md).

The updated prompt/validator was exercised on one live configuration-error case:
correct orders/config_error diagnosis, five exact citations, zero rejected
submissions, 22.93 seconds, $0.036508 token-cost estimate. See
[live-config-smoke.md](live-config-smoke.md) for scope and limitations.

The remaining three fault types were tested live: slow_dependency and traffic_spike
were correctly diagnosed; cert_expiry named the right type but blamed orders
instead of payments. Batch token-cost estimate: $0.194307. All six fault types now
have one live smoke case, with five correct service-and-fault diagnoses across
mixed prompt versions. See [live-remaining-smoke.md](live-remaining-smoke.md) for
retry counts, capacity-limit caveats and next correctness work.

Certificate ownership and scaling headroom now have log-backed MCP assessment
gates. Both saved failure payloads are rejected under the new gates, and scripted
MCP/graph corrections and unknown-evidence abstention passed offline. See
[operational-checks.md](operational-checks.md). No new paid calls were made;
live effects remain unmeasured.

Prompt-v4 live validation returned a correct payments certificate diagnosis, a
model-submitted traffic abstention after blocked scaling proposals, and a
budget-forced abstention on missing evidence. Token-cost estimate: $0.274801.
See [live-v4-validation.md](live-v4-validation.md) for the distinction between
model and system outcomes and the remaining diagnosis/stopping issues.

Diagnosis/recovery separation and bounded investigation were checked offline on
2026-10-12. Recorded-query replay consumed seven scripted responses and 32 tool
executions instead of completing the original 12-response / 49-query schedule.
This is not a new model result; no paid calls were made. See
[diagnosis-stopping.md](diagnosis-stopping.md).

The v5 traffic and redacted live checks both failed their expected outcomes:
wrong inventory/bad_deploy and unsupported gateway/config_error diagnoses were
accepted with genuine quotes. Both ended via model submission; no stopping rule
triggered. Combined token-cost estimate: $0.153161. See
[live-v5-validation.md](live-v5-validation.md) for evidence-validation limitations.

Explicit collection availability and release-linked change assessments passed
offline regressions: 91 tests and 1,176 deterministic assessment pairs. See
[change-evidence.md](change-evidence.md). The updated local image also passed the
container smoke; see `container-verification-v6.json`.

V6 live validation still missed both expected outcomes: traffic submissions named
search/traffic_spike but hit output truncation and a citation error, forcing an
abstention; the redacted case guessed auth/slow_dependency using gateway evidence.
Combined usage-derived token cost: $0.155941, under the approved $1 cap. No action
was recommended. See [live-v6-validation.md](live-v6-validation.md).

V7 adds diagnostic assessments for memory leaks, slow dependencies and traffic
spikes, a six-field compact final schema, and separate output-truncation handling.
All 130 tests passed in 2.99 seconds. The expanded six-fault matrix accepted 78/78
supported pairs and rejected 3,450/3,450 unsupported pairs, with zero provider calls.
See [fault-gates-compact.md](fault-gates-compact.md) for limits and measurements.

V7 live validation returned an expected model-submitted abstention on redacted
evidence, while the traffic case still ended in a forced abstention after two
citation rejections and one unsupported-cause rejection. Both had zero output
truncations and no accepted action recommendation. Combined usage-derived token
cost: $0.112161, under the new approved $1 cap. See
[live-v7-validation.md](live-v7-validation.md) for measured limits and remaining work.

V8 replaces model quote copying with observation-ID selection and server-attached
exact excerpts. The migrated v7 traffic schedule accepts search/traffic_spike with
blocked scaling in eight scripted responses/16 MCP executions; both unsupported
inventory rollback proposals remain rejected. No provider calls were made. See
[observation-id-evidence.md](observation-id-evidence.md) for measurements and limits.

Latest observation-ID verification: 158 tests passed in 3.17 seconds, including
malformed-service input handling. No paid provider calls were made in this pass.

V8 live validation passed both expected diagnostic outcomes: search/traffic_spike
with null recovery fields, and model-submitted abstention on redacted evidence.
Both had zero validation rejections and truncations. Per-test usage-derived costs
were $0.053230 and $0.042555, within the standing $0.50-per-test authorization.
See [live-v8-validation.md](live-v8-validation.md) for source evidence and limits.

Fresh-seed v8 follow-up: five original cases at seeds 1000–1004 all returned the
correct service/fault with model-selected finalization, zero rejections/truncations
and $0.175430 combined token cost. All 25 response usages and 15 evidence excerpts
were reconciled. One memory log excerpt displays an unrelated later error despite
a supported diagnostic assessment; improve excerpt relevance next. See
[live-v8-fresh-faults.md](live-v8-fresh-faults.md). Local tests in this pass: 158
passed in 3.48 seconds; fixture thresholds passed. No recovery was executed.

Assessment-backed excerpt fix: 171 tests passed in 3.25 seconds. Revalidating five
saved submissions changed only the memory log excerpt to the exact OOMKilled
record; all five diagnoses/recovery fields stayed unchanged and all 15 excerpts
match their sources. Evidence matrix and migrated replay passed without provider
calls. See [excerpt-verification.json](excerpt-verification.json). User requested
edge-case live tests before deployment after initially considering deferral.
