# Local verification — updated 2026-10-06

Working directory: `/Users/armaankolsawala/IdeaProjects/incident-copilot`.
No Git repository or applicable AGENTS.md was found. Original source/review
copies remain outside this workspace.

Python 3.12.15 is installed at `/opt/homebrew/bin/python3.12`; `.venv` is ready.
The user installed dependencies from a terminal outside the restricted shell.
`requirements.lock` pins 72 runtime packages; `requirements-dev.lock` pins 76
packages, including the development dependencies. Locks have no wheel hashes.
No API requests or deployment have been made; paid API work is paused.

Measured on Python 3.12.15:

- `python -m pytest -q tests`: 26 passed (2.14 seconds on the latest run).
- `python -m pip check`: no broken requirements.
- `python -m evals.retrieval_eval`: TF-IDF recall@1 and recall@3 both 14/14;
  optional FastEmbed skipped because it is not installed.
- `python -m compileall -q copilot app evals tests scripts`: exit 0.
- `python scripts/check_benchmarks.py`: exit 0.

The tests exercise real in-memory MCP transport and the LangGraph loop, forged
citation rejection, exhausted-budget abstention without an extra model call,
usage/trace preservation after model failure, cancellation settlement and saved
background replays. A 30-case parity check compares rule predictions and call
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
from the current report. The app reached startup, but socket binding at `127.0.0.1:8000` failed with
`operation not permitted`. Browser verification, Linux dependency installation
and container builds remain pending. Docker/Fly CLIs and deployment account
access are not configured. In-process HTTP tests passed; they do not substitute
for a browser or deployed-system check.
