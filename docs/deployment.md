# Deployment preparation and remaining checks

The application is not deployed. Python 3.12.15 and locked dependencies are ready;
the latest local suite passed 171 tests in 3.25 seconds. Linux ARM64 container
verification passed HTTP, non-root execution and budget/replay persistence checks
(`container-verification-v8.json`); CI also covers Linux AMD64. Browser checks were
reported working by the user on 2026-10-06.

Twenty-nine authorized Haiku smoke investigations completed across prompt versions.
The seven latest selected edge cases met expected outcomes: six correct diagnoses
and one model-selected missing-evidence abstention, with zero rejections or
truncations. The assessment-backed excerpt fix repairs the recorded memory log
selection. Generic supplemental source selections can still display generic
excerpts. These small tests do not establish production reliability or recovery
effectiveness. See [latest live validation](live-v8-edge-cases.md).

The updated local container passed HTTP, non-root execution and persistent
ledger/replay checks; see `container-verification-excerpt.json`. The user requested
these edge-case tests before deployment; they are complete. Broader repeated-seed
challenge and recovery experiments remain follow-up work. Account/destination
access and hosting budget are still needed before public deployment.

All six fault types now require matching MCP assessments, missing telemetry is
explicit, and diagnostic cause is separate from recovery recommendations. Standing
API-test authorization is up to $0.50 per test, with a verified conservative bound
required before each test. Deployment account/destination access is still needed.

## Local setup

Run `./scripts/setup.sh` from a terminal with network access to install the
locked environment and run offline checks. The locks contain exact version pins,
without wheel hashes; Linux/ARM64 installation was verified by a local container build; Linux/AMD64 is covered by CI after push. Start with:

```bash
.venv/bin/python -m uvicorn app.main:app --workers 1
```

API credentials must be exported into that process; `.env` is not automatically
loaded. Without credentials, the UI can show the bundled offline replay. Keep
secrets out of chat, scripts and commits.

## Container verification

```bash
docker build -t incident-copilot:local .
python scripts/container_smoke.py --image incident-copilot:local
```

The check creates uniquely named test resources, verifies HTTP and missing-key
rejection, confirms PID 1 runs as UID 10001, writes a synthetic ledger charge and
replay, then verifies both survive restart. It also makes the mount root owned by
root to test volume initialization. The entrypoint fixes ownership of the data
directory and drops root before starting Uvicorn. It does not change existing
file owners; restore database files with UID 10001 ownership. The smoke check
removes only its own container and volume. Results are recorded in
`container-verification.json`; the test charge is not provider spending.

## Model smoke test

Use the standing $0.50-per-test approval only when a verified conservative bound
fits it; request approval for a higher or unverified bound. Run Haiku at concurrency one,
inspect trace evidence IDs, response usage, provider errors and observed cost.
Token counting precedes each Messages request; automatic provider retries are
disabled. Each run permits 12 model calls, 24,000 input tokens per call, 1,000
output tokens per call and 180 seconds overall. These are application limits;
timeouts can leave provider charges without a usage response. The web ledger
charges the entire reservation for uncertain runs. Eval JSON reports observed
usage and flags billing uncertainty rather than inventing an exact charge.

Then compare RAG and no-RAG on identical case IDs, within the approved budget.
The challenge cases are versioned transformations of synthetic fixtures, not
real-world incidents or a blind external test set.

## Fly.io

Account access and a destination name are still needed. After local checks and
model smoke tests pass:

1. Set a unique app name in `fly.toml`, create that app in the chosen account.
2. Create a persistent volume named `copilot_data` in `sjc`.
3. Configure `ANTHROPIC_API_KEY` securely as a Fly secret.
4. Build and deploy with `fly deploy --ha=false`, then `fly scale count 1`.
5. Verify HTTPS `/healthz`, the offline replay, one authorized live request,
   concurrent admission, and ledger/replay persistence across restart.

Run exactly one machine and one worker. SQLite reservations coordinate processes
on a single persistent local database, but each Fly machine's separate volume
would create independent budgets. Multiple machines require a shared transactional
store (for example PostgreSQL) before scaling. Live polling is process-local;
completed replays persist in SQLite. Stop/start can interrupt a background run.
Unsettled reservations survive restarts and count against admission indefinitely;
review provider billing before manually settling any orphaned reservation.
Never blindly release a hold because its process stopped.

The web app exposes no remediation execution. Structured actions are only
recommendations. Accepted recommendation text is generated from conservative
server policies; model prose is replaced, including on insufficient-evidence
outcomes. Action/fault compatibility and target/service consistency are validated.
Evidence IDs resolve to exact source excerpts, and each cause requires a matching
fault-specific MCP assessment. Individual excerpts can still lack diagnostic
relevance; these narrow synthetic checks do not establish general causality. Deployment-specific
recovery plans still require verified versions and service-policy checks.
IP-based rate limiting trusts `fly-client-ip` only when explicitly enabled on Fly.
Do not enable this trust setting on a directly reachable local server.
