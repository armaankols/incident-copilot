# Incident Copilot

A Python/FastAPI demo that investigates **synthetic incident telemetry** using
Claude tool calls, a LangGraph investigation loop, and an in-memory MCP session.
It compares diagnoses with injected ground truth. No live-model evaluation or
public deployment has been completed. Paid API work is currently paused.

The existing simulator models six fault types across seven services. This is not
a Docker service fault lab. Runbook retrieval uses sparse TF-IDF vectors and
cosine similarity; optional FastEmbed provides dense vectors. Prompt caching is
requested, but cache savings have not been measured.

## Implementation

- The agent discovers MCP tools for health/topology, metric time series, logs,
  release history, and runbooks. The server also supports standalone stdio.
- Validated diagnoses contain an explicit outcome, structured action and target,
  and exact quotations referencing successful retrieved observations. Provenance
  validation does not establish that the evidence supports the diagnosis.
- Budget exhaustion returns `insufficient_evidence` without a forced model guess.
  Model calls, graph steps, tool calls, usage and partial failure traces are distinct.
- Web admission uses atomic SQLite reservations, durable rate limits and bounded
  concurrency. Success, failure and cancellation settle reservations; uncertain
  billing retains the full reservation. This is an application guardrail, not a
  provider billing hard cap. Deployment requires one machine and one worker.
- The UI polls investigation progress and links saved replays. The bundled offline
  replay uses the tailored rule baseline, and does not represent a model run.
- Evaluations checkpoint each record and use unique experiment names, source
  hashes, dataset/prompt versions, case IDs, errors and observed usage.

## Measured results

<!-- RESULTS:START -->
Measured offline baselines on synthetic telemetry. Transport is recorded per experiment.

| Run | Transport | Cases | Outcome correct (95% CI) | Errors | Total observed API cost | p50 / p95 seconds |
|---|---|---:|---|---:|---:|---|
| python312-latest-deploy-d27b85c6db2d | deploy history | 60 | 5.0% (1.7–13.7) | 0 | $0.000000 | 0.000001 / 0.000002 |
| python312-mcp-rules-challenge-d2808d804229 | in-memory MCP | 24 | 33.3% (18.0–53.3) | 0 | $0.000000 | 0.084101 / 0.144860 |
| python312-mcp-rules-original-349e3b4a5bd7 | in-memory MCP | 60 | 100.0% (94.0–100.0) | 0 | $0.000000 | 0.288247 / 0.414055 |
| python312-rules-challenge-77334f82ea35 | direct simulator log search | 24 | 33.3% (18.0–53.3) | 0 | $0.000000 | 0.000138 / 0.000960 |
| python312-rules-original-bd66349c44c0 | direct simulator log search | 60 | 100.0% (94.0–100.0) | 0 | $0.000000 | 0.001171 / 0.001318 |

Outcome accuracy counts a correct abstention on redacted cases. Latency quantiles describe successful runs; failure elapsed time and observed spend remain in JSON records. Structured action compatibility is not a remediation-quality score. No live-model results have been measured.

Retrieval smoke checks (small author-written query set):
- tfidf: 14 queries, recall@1 100.0%, recall@3 100.0%.

Version-specific recovery policy lookup (offline structured reader, not an LLM ablation):

| Retrieval | Exact policies | Correct unknown-version abstentions |
|---|---:|---:|
| no-retrieval | 0/12 | 3/3 |
| tfidf | 12/12 | 3/3 |
<!-- RESULTS:END -->

The original fixtures are easy for seven simulator-tailored log rules: 60/60
correct diagnoses. The weak latest-deploy baseline gets 3/60. The challenge suite
contains six cases each with paraphrased signatures, healthy diagnostic decoys,
historical recovered errors, and redacted evidence. The same rules get 8/24
outcomes correct, including all six required abstentions. These measurements do
not establish how an LLM will perform.

The supplied 14-query retrieval smoke test was independently rerun: TF-IDF
scored 14/14 at recall@1 and recall@3. This small author-written set does not
establish general retrieval quality. Earlier supplied results remain in `results/archive/`.
Structured action compatibility replaces the misleading remediation keyword
score; it does not measure remediation quality or recovery.

## Setup and local checks

Run from a terminal with network access:

```bash
./scripts/setup.sh
.venv/bin/python -m pytest -q tests
.venv/bin/python -m evals.retrieval_eval
.venv/bin/python -m evals.recovery_eval
.venv/bin/python -m uvicorn app.main:app --workers 1
```

Python 3.12.15 and `.venv` are configured. Runtime and development version locks
are generated from the tested installed environment, including transitive
dependencies. These are exact version pins, without wheel hashes. Docker and CI
use those locks; Linux/ARM64 installation and container smoke checks passed.
The setup script can install the locked development environment from a terminal
with network access. Without a model key, the page and bundled replay still work; live
investigations return 503. Export `ANTHROPIC_API_KEY` securely into the server
process; the app does not automatically load `.env`.

The dependency-free subset runs on Python 3.12 (and also passed on Python 3.9):

```bash
python3 -m unittest tests/test_correctness.py -v
python3 -m evals.run_evals --agent baseline --n 60
python3 -m evals.run_evals --agent rules --n 60 --save-traces
python3 -m evals.run_evals --agent rules --suite correlated-v1 --n 24 --save-traces
.venv/bin/python -m evals.run_evals --agent rules-mcp --n 60 --save-traces
python3 scripts/check_benchmarks.py
python3 -m evals.report
```

The full offline suite passed 29 tests, including FastAPI/MCP/LangGraph
integration, evidence validation, partial failure accounting, cancellation
settlement and replay persistence. TF-IDF retrieval checks passed. The local demo now runs with elevated execution
permission. Initial replay and completed-run reload were inspected in Chrome;
manual active-run/error/dropdown checks are pending the user's report. See [verification notes](docs/verification.md).

## Live evaluation and deployment

Paid API calls require an approved budget and configured credentials. Begin with
one or two Haiku smoke cases before a larger same-case RAG/no-RAG comparison.
No budget estimate here is a measured spend result. Save traces and inspect
billing-uncertainty flags before expanding a run.

[Deployment preparation](docs/deployment.md) describes persistent storage,
health checks, single-machine constraints, and the verification steps still
needed. No demo URL or GitHub destination has been established.

## Next experiments

The `recovery-v1` benchmark adds 12 service/version policy cases and three unknown
versions, using an isolated corpus under `runbooks/recovery/`. It checks rollback
compatibility, restart ordering and configuration limits. Its offline reader
extracts structured policies from retrieved chunks and abstains on missing or
conflicting versions. These results measure lookup availability, not LLM recovery
reasoning. Dense retrieval and live-model ablations remain future experiments. A meaningful
remediation approval gate needs simulated action execution followed by recovery
verification. pgvector and real incident corpora remain future work.
