# Deployment/configuration evidence and telemetry availability

The two v5 live failures were accepted guesses despite genuine quoted evidence.
The traffic-spike run blamed an inventory release using search-service symptoms.
The redacted run inferred a gateway configuration error from gateway symptoms and
fabricated flat downstream metrics. Historical live JSON records and grades are
preserved; this change has not been tested with a live provider.

## Observable availability

`Scenario.telemetry_availability` describes collection coverage independently of
hidden fault/service labels. MCP health, metrics, log search and release-history
tools expose missing coverage explicitly. Unavailable metrics return no numeric
samples. Partial log searches can return retained records with a coverage warning;
no matches under incomplete coverage do not establish service health. Operational
checks return unknown when their required log/release sources are unavailable.

`correlated-v2` keeps the challenge variants and seeds, but its six redacted cases
retain only gateway metrics and one gateway warning. Downstream metrics/logs and
release history are unavailable; gateway log coverage is partial. The dataset hash
includes this availability metadata. `correlated-v1` remains selectable with its
historical numeric data, so its old experiments remain reproducible. The recorded
stopping replay deliberately continues using its original v1 dataset.

## Diagnostic gate

A diagnosed `bad_deploy` or `config_error` now requires an authentic, cited
`check_change(service, fault_type)` observation with status `supported` for the
same service and fault. A missing, unknown, conflicting, mismatched or uncited
assessment rejects the diagnosis. Setting action and target to null does not
bypass the gate. The model receives corrective feedback and can gather evidence
or submit `insufficient_evidence` within the existing budgets.

The helper reads only observable release records, logs, collection coverage and
the snapshot time. It never reads the injected root/fault labels.

- For `bad_deploy`, the latest unambiguous release must match the build in repeated
  service-local ERROR exception records. It recognizes the simulator's original
  and paraphrased handler-exception forms. At least two distinct failure times and
  a failure in the last five minutes are required.
- For `config_error`, a configuration-load record must match the latest release.
  Repeated local pool-exhaustion failures must match its pool limit and timeout,
  including a failure in the last five minutes. A later unrecognized configuration
  load leaves the assessment unknown.

An unrelated deployment, generic caller error, old recovered error or missing
source cannot meet these requirements. This is a narrow synthetic assessment;
it does not prove release causality, identify a code defect, establish that a pool
setting is intrinsically wrong, or cover arbitrary production configuration errors.
Certificate ownership retains its existing diagnostic gate. Memory leak, slow
dependency and traffic spike still use the existing citation validation without
an equivalent fault-specific assessment. Replica headroom remains a separate
recovery check: a supported traffic diagnosis can retain its cause while scaling
is blocked.

## Measured offline results (2026-10-12)

- Full suite: **91 passed in 2.80 seconds**.
- Both saved v5 unsupported diagnoses are rejected using their real quoted
  fragments, with and without recovery actions. These are payload regressions,
  not model reruns.
- Real MCP/LangGraph scripted tests reject a gateway configuration guess then
  accept an abstention; reject the inventory release guess then accept the search
  traffic diagnosis with blocked scaling. Scripted responses prescribe the model's
  next move and do not measure its ability to correct itself.
- Deterministic evidence matrix: **1,176 assessments** across **84 scenarios**
  (60 original + 24 correlated-v2), **26/26** expected supported pairs accepted,
  **1,150/1,150** unsupported pairs rejected, **0** false supports. Source/data
  hashes and individual assessments are in `results/evidence.json`. Labels score
  the gate in the evaluation only; this is not agent diagnosis accuracy.
- Tailored keyword baseline: **60/60** original outcomes and **8/24** challenge
  outcomes in both v1 and v2. Direct and real MCP v2 results agree. Six of the
  eight challenge successes are required abstentions.
- TF-IDF smoke: **14/14** recall@1 and recall@3. Recovery policy lookup: **12/12**
  exact policies with TF-IDF versus **0/12** without retrieval; both **3/3** unknown
  version abstentions. These are offline lookup checks.
- Historical v1 query-schedule replay: **7 scripted responses**, **32 MCP executions**,
  **0 cache hits**, **2 skipped requests**, stopping at the tool limit. No new model
  behavior is measured.

The updated Linux ARM64 Docker image also passed the offline deployment smoke:
five HTTP routes returned 200, the live endpoint returned 503 without credentials,
the server ran as UID 10001, and ledger/replay data survived a restart with a
root-owned mount. Measurements are in `docs/container-verification-v6.json`.
This verifies a local image; no public deployment has been completed.

All checks above made **zero provider calls**. Live Haiku validation of the new
prompt/tool requirements remains outstanding and requires another paid-run approval.

Reproduce from the repository's Python 3.12 environment:

```bash
.venv/bin/python -m pytest -q tests
.venv/bin/python -m evals.evidence_eval
.venv/bin/python -m evals.run_evals --agent rules --n 60
.venv/bin/python -m evals.run_evals --agent rules --suite correlated-v1 --n 24
.venv/bin/python -m evals.run_evals --agent rules --suite correlated-v2 --n 24
.venv/bin/python -m evals.run_evals --agent rules-mcp --suite correlated-v2 --n 24
.venv/bin/python -m evals.retrieval_eval
.venv/bin/python -m evals.recovery_eval
.venv/bin/python -m evals.stopping_eval
.venv/bin/python scripts/check_benchmarks.py
.venv/bin/python -m evals.report
```
