# Deployment preparation and remaining checks

The application is not deployed. Python 3.12.15 is configured; 26 offline tests
and the required TF-IDF retrieval checks passed. Runtime/development version
locks are generated. Browser verification is pending because the sandbox rejects
local socket binding. Docker and Fly CLIs are unavailable, so no container build
or deployment was attempted. Paid API work remains paused at the user's request.

## Local setup

Run `./scripts/setup.sh` from a terminal with network access to install the
locked environment and run offline checks. The locks contain exact version pins,
without wheel hashes; Linux installation remains unverified. Start with:

```bash
.venv/bin/python -m uvicorn app.main:app --workers 1
```

API credentials must be exported into that process; `.env` is not automatically
loaded. Without credentials, the UI can show the bundled offline replay. Keep
secrets out of chat, scripts and commits.

## Model smoke test

Wait for an explicit API budget. Start with two Haiku cases at concurrency one,
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
recommendations. Quoted evidence is checked for provenance, not semantic support.
IP-based rate limiting trusts `fly-client-ip` only when explicitly enabled on Fly.
Do not enable this trust setting on a directly reachable local server.
