# Six-fault evidence checks and compact submission — 2026-10-12

The v6 live traffic investigation lost its correct proposed cause after two
1,000-token output truncations and a citation failure. The redacted case accepted
an unsupported auth/slow_dependency diagnosis. This implementation addresses both
failure paths offline. Historical live results and grades remain unchanged; no
new provider calls were made.

## Evidence requirements for every fault

`memory_leak`, `slow_dependency` and `traffic_spike` now require an authentic,
cited `check_fault(service, fault_type)` assessment with status `supported` for
the exact diagnosed service/fault. The checks apply even when action and target
are null. Deployment/configuration faults retain `check_change`; certificate
expiry retains `check_certificate`. Every diagnosed fault therefore requires a
trusted diagnostic assessment. Capacity remains a separate recovery check.

The new helper reads logs, metric series, source coverage and snapshot time.
It never reads injected root/fault labels. Missing or malformed data, incomplete
coverage, stale signatures, wrong-service records and absent corroboration leave
the assessment unknown.

| Fault | Affirmative records | Metric corroboration |
|---|---|---|
| Memory leak | Local OOM termination, restart at its timestamp, recent GC/heap pressure | Memory growth before the OOM and subsequent regrowth with continuing pressure; recent plateau after regrowth is allowed |
| Slow dependency | Repeated current local slow-query or worker-saturation records, plus a current caller timeout naming that service | Local latency rises substantially above the earlier baseline |
| Traffic spike | Repeated current local admission/load-shedding records | Local request-rate increase with CPU saturation, increased errors and latency |

These are narrow synthetic patterns. The baseline is the first 30 samples within
the snapshot's last 120 minutes; the current comparison uses the last five.
Slow-dependency latency must be at least three times baseline and at least 250ms
higher. Traffic needs at least three times baseline RPS, median CPU at least 70%,
an error-rate increase of at least one percentage point and latency at least twice
baseline. Memory uses 20-minute growth segments (at least 150MB and 16 rising
steps), an observed restart at OOM, subsequent regrowth and median recent memory
at least 1.5 times baseline. These thresholds describe the simulator, rather than
production SLOs or recovery settings. They do not prove causality or distinguish
all real causes of memory pressure, slow queries or excess traffic.

A runbook containing similar JSON cannot forge a check: the validator requires
an observation produced by the named MCP tool, the correct service/fault and a
citation to that observation. An unknown/conflicting assessment cannot be omitted
in favor of another supported observation for the same service/fault.

## Smaller final submissions

The model-facing schema requires six fields: `status`, `root_cause_service`,
`fault_type`, `evidence`, `action`, `target`. Model-written remediation is removed
from that schema. The server continues generating recommendation text. Older
clients can still supply the former remediation field; its content is ignored
and never used in accepted advice.

Evidence is limited to three references, each with an exact contiguous quote of
at most 240 characters. The prompt asks for one short investigation-update
sentence and direct final tool submission without preceding prose. A brief
assessment-status excerpt is enough to reference a trusted assessment. Long
metric series or JSON objects are unnecessary. Exact-match citation integrity
remains enforced; the old invalid traffic quote remains invalid.

A valid constructed traffic submission is:

```json
{"status":"diagnosed","root_cause_service":"search","fault_type":"traffic_spike","evidence":[{"observation_id":"obs-1","quote":"\"status\": \"supported\""}],"action":null,"target":null}
```

This example requires a real, supported `check_fault` result at `obs-1`. It is
185 UTF-8 bytes in compact serialization, compared with 1,747 bytes for the saved
v6 final traffic input. Bytes are not tokens. This demonstrates a smaller fixture,
not that a live model will follow the format or fit every response within the cap.

## Output truncation handling

A provider response with `stop_reason=max_tokens` is preserved as a truncated
response in the trace. Every tool call in that response is closed with corrective
feedback; none is executed or accepted as a diagnosis, including a seemingly
complete call appearing before a truncated trailing block. Truncation increments
`output_truncations`, while ordinary schema/citation/evidence failures increment
`validation_rejections`. Usage and model calls are still counted.

Three truncated responses stop the investigation with `termination_reason=output_limit`.
The existing three-invalid-submission limit remains separate. All responses count
against the existing 12-call bound. The API allowance remains 1,000 output and
24,000 input tokens per call, with zero SDK retries. Budget reservations and price
assumptions were not increased. The UI shows truncation events and their stopping
reason. Live effects and manual browser behavior have not been measured.

## Measured offline verification

- Full suite: **130 passed in 2.99 seconds**.
- Saved auth guess: rejected with genuine shortened quotations and an unknown
  auth/slow_dependency assessment. No recovery action bypasses that requirement.
- Scripted real MCP/graph correction: two truncated submission shapes followed by
  a compact supported traffic submission complete in four scripted calls and one
  MCP execution, with two truncations and zero invalid-submission rejections.
  The scripted final correction is prescribed, not a new model response.
- Repeated truncation stops after three scripted calls with no MCP execution;
  an earlier two-call global budget still terminates after two.
- Six-fault matrix: **3,528** service/fault assessments across **84** scenarios
  (60 original plus 24 correlated-v2): **78/78** expected supports accepted,
  **3,450/3,450** unsupported pairs rejected, **0** false supports.
- All **78** constructed compact submissions pass the validator; largest payload
  **193 UTF-8 bytes**. These are fixtures, not measured model output/token counts.
- Tailored rule baseline: **60/60** original, **8/24** challenge outcomes in v1 and
  v2, including six correct redacted abstentions per challenge suite.
- TF-IDF smoke: **14/14** recall@1/@3. Policy lookup: **12/12** exact policies with
  TF-IDF versus **0/12** without retrieval; both **3/3** unknown-version abstentions.
- Historical query-schedule replay remains seven scripted responses, 32 MCP
  executions and termination at the tool limit, with zero provider calls.
- The updated Linux ARM64 image passed five HTTP route checks (200), the missing-key
  live endpoint check (503), UID 10001 execution and ledger/replay restart persistence.
  Measurements are in `docs/container-verification-v7.json`; no public deployment occurred.
- Python compilation and JavaScript syntax checks passed. Browser interaction
  has not been manually rechecked in this pass.

The matrix covers known simulator and paraphrase templates and uses injected
labels only to score the assessments. It is not an LLM accuracy benchmark or
production generalization evidence. The earlier two-fault matrix is preserved in
`results/archive/evidence-v6.json`; current results and source/data/fixture hashes
are in `results/evidence.json`. The public traffic fixture contains synthetic
submission/log records only, without credentials or conversation payloads.

Reproduce with:

```bash
.venv/bin/python -m pytest -q tests
.venv/bin/python -m evals.evidence_eval
.venv/bin/python -m evals.stopping_eval
.venv/bin/python -m evals.retrieval_eval
.venv/bin/python -m evals.recovery_eval
.venv/bin/python -m evals.run_evals --agent rules --n 60
.venv/bin/python -m evals.run_evals --agent rules --suite correlated-v1 --n 24
.venv/bin/python -m evals.run_evals --agent rules --suite correlated-v2 --n 24
.venv/bin/python scripts/check_benchmarks.py
.venv/bin/python -m evals.report
```

Subsequent live Haiku validation returned a correct model-submitted redacted
abstention and a traffic miss caused by citation/support rejections, with zero
output truncations in either run. See [live-v7-validation.md](live-v7-validation.md).
Further paid runs require approval. No automatic model switch was introduced.
