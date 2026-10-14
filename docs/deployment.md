# Deployment and operations

The demo is deployed at [incident-copilot.fly.dev](https://incident-copilot.fly.dev/)
in the personal Fly organization. It uses one shared CPU/1 GB machine in `sjc`,
one encrypted 1 GB persistent volume, HTTPS, one non-root worker, and idle
stop/start. The server key is stored as a Fly secret. GitHub pushes run offline
CI; deployment is a separate explicit action.

The access gate and request security controls were deployed on 2026-10-13 as
`registry.fly.io/incident-copilot:security-b50ba7df752b`. Production checks verified
both paid endpoints reject missing access, the signed cookie unlocks access,
over-budget authenticated requests are denied without model calls, oversized
bodies and validation-input reflection are blocked, and supplied IP headers do
not create spoofed visitor quotas. The same machine/volume, two existing runs,
two replay payloads and $0.090678 of charges were preserved. See
[security verification](security-verification.json). No paid test was made.

The audit follow-up is deployed from committed runtime `07abd54` as
`registry.fly.io/incident-copilot:07abd54`. It disables unsafe slash redirects,
redacts MCP/legacy trace errors, separates health-probe quotas, and fixes explicit
low-credit and cross-midnight accounting. All 219 offline tests, frontend checks,
runtime CI and the exact AMD64 container checks passed. Live checks preserved
the original access link, both credentials, machine/volume, ledger rows and replay
payloads. No provider calls or new model reservations were made. See
[follow-up verification](security-fixes-verification.json).

The public API budget is $0.50/day across visitors, separate from standing
$0.50-per-test development authorization. The day resets at midnight Pacific
(`America/Los_Angeles`), including daylight saving transitions. The UI labels the
Pacific accounting date and reset boundary. Haiku's conservative per-run reservation
is $0.42; Sonnet exceeds the daily cap and is denied before provider calls. This
can reject new investigations before actual spend reaches $0.50, because each
run must fit its worst-case reservation. The application ledger uses reported
usage, not reconciled provider invoices. Saved replays remain available.

The user approved a monitored $10/month Fly hosting target after clarification
that it is not a hard cap. Check actual month-to-date billing manually; near $8,
disable automatic startup and stop the machine if pausing for the rest of the
month. Storage/stopped-rootfs charges continue. No automated billing monitor or
cutoff exists. See [authorization](deployment-authorization.json).

The hosted Haiku memory-leak investigation correctly diagnosed orders, with zero
rejections/truncations and $0.060967 usage-derived cost. Five HTTPS routes passed;
Sonnet and concurrent-budget probes returned 429. The replay and charged amount
survived a machine restart and idle stop/wake. Idle stop was observed after
269.019 seconds without web traffic; the wake health request took 3.698 seconds. See [live verification](deployment-live.md) and
[measured record](deployment-verification.json). Prior local tests passed 171 cases;
local AMD64/ARM64 and GitHub CI container checks also passed. These tests do not
establish production reliability or recovery effectiveness.

Fly's [trial terms](https://docs.fly.io/about/free-trial), checked on 2026-10-13,
state that trial machines stop after five minutes. That can confound the initial
idle-stop observation; it does not independently verify idle behavior on a paid
account. The trial lasts seven days or two shared VM hours, whichever comes first;
adding a credit card ends the trial immediately.

The UI loads the labeled offline sample by default. Past investigations lists
completed saved hosted results, including saved failures, newest first with
20 results per page. The read-only `GET /api/runs` endpoint accepts `limit` (1–50)
and `offset` (nonnegative), and exposes summary fields without visitor hashes,
reservation amounts or full traces. Active or interrupted runs without saved
results are excluded. Historical local benchmark files are not imported into
the hosted database. Existing `?run=...` links take priority over the sample.

## Local setup

Run `./scripts/setup.sh` from a terminal with network access to install the
locked environment and run offline checks. The locks contain exact version pins,
without wheel hashes; Linux/ARM64 installation was verified by a local container build; Linux/AMD64 is covered by CI after push. Start with:

```bash
.venv/bin/python -m uvicorn app.main:app --workers 1 --no-proxy-headers --limit-concurrency 32
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

The account/app/volume are established. The initial deployment used these steps:

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

Confirmed insufficient-credit rejections release only unused model reservations;
previously reported usage stays charged. Ambiguous failures retain the worst-case
reservation. Cross-midnight runs are conservatively charged to their Pacific
settlement day, and active holds count across days.

The Pacific-day upgrade migrates legacy UTC accounting dates once, atomically,
and retains their originals in `legacy_utc_days`. It uses admission time, the
recorded UTC settlement day and migration time to bound the possible settlement
time; ambiguous Pacific dates require operator review before startup can proceed.
Preflight a private database backup with the new code before deployment. Charges,
other reservation fields and raw replays remain unchanged. Do not roll back to
UTC-only code against a migrated ledger: it would use the wrong accounting days.
Restore the matching pre-migration backup only if no newer runs would be lost;
otherwise use a reviewed accounting migration.

The web app exposes no remediation execution. Structured actions are only
recommendations. Accepted recommendation text is generated from conservative
server policies; model prose is replaced, including on insufficient-evidence
outcomes. Action/fault compatibility and target/service consistency are validated.
Evidence IDs resolve to exact source excerpts, and each cause requires a matching
fault-specific MCP assessment. Individual excerpts can still lack diagnostic
relevance; these narrow synthetic checks do not establish general causality. Deployment-specific
recovery plans still require verified versions and service-policy checks.
IP-based rate limiting trusts `fly-client-ip` only when explicitly enabled on Fly.
It also requires a verified socket peer in `TRUSTED_PROXY_CIDRS`; Uvicorn proxy
header rewriting must remain disabled. Do not enable this trust setting on a
directly reachable local server. See [request and access controls](security-controls.md)
for body limits, persistent HTTP quotas, and public error sanitization.

## Initial preflight — historical record

Fly CLI 0.4.116 login was verified against the personal organization, which had
zero existing apps. `fly.toml` now proposes `incident-copilot-armaankols` in `sjc`,
one shared CPU with 1 GB RAM, one 1 GB volume, HTTPS, and idle auto-stop. Strict Fly
configuration validation passed. The $0.50/day application API budget was approved by the user on 2026-10-13.
Hosting budget approval was subsequently granted on 2026-10-13. Its offline admission check accepted a
$0.42 Haiku reservation and rejected Sonnet with 429 before any provider call.
The UI still lists both models; Sonnet cannot fit this proposed daily cap.

Official Fly and Buildx binaries were downloaded into ignored `.bootstrap/` and
their GitHub release digests were verified. The initial legacy Docker cross-build
failed; Buildx 0.38.0 built the Linux AMD64 image successfully. The deployment
image `registry.fly.io/incident-copilot-armaankols:354393a` passed local HTTP, UID
10001, missing-key rejection and ledger/replay persistence checks. At preflight the registry
tag was local only and no Fly resources existed. The app/image/volume/machine
were subsequently published on 2026-10-13.
See [preflight record](deployment-preflight.json) and
[deployment-image verification](container-verification-deploy.json).

The completed initial deployment sequence was: create the app in `personal`, create
`copilot_data` at 1 GB in `sjc`, stage the existing server key through secret-import
stdin, authenticate Docker to Fly, push the verified image, and deploy with
`--image registry.fly.io/incident-copilot-armaankols:354393a --ha=false`. Verify a
single machine/volume, HTTPS health/replay, one budgeted Haiku request, admission
behavior and ledger/replay persistence across restart. No remote builder is needed.

Hosting is usage-billed, including compute/storage and transfer; a monthly target
is not an enforced Fly bill cap. Current pricing references:
[resource pricing](https://docs.fly.io/about/pricing),
[cost management](https://docs.fly.io/about/cost-management). No hosting spend has
been measured in this preparation.

## Hosting target controls

The user approved $0.50/day for public API usage on 2026-10-13, and asked how a
$10/month hosting target would be enforced. Hosting approval was then granted after the manual-check/non-enforced-cap explanation.
See [deployment authorization](deployment-authorization.json).

Fly's current [cost-management documentation](https://docs.fly.io/about/cost-management)
states there is no billing ceiling or native billing alert. Fixed resource counts
(one machine/volume), idle stopping, shared IPs and no paid add-ons constrain the
base cost; they do not cap bandwidth or the final invoice. A manual billing check
and pausing the service near $8 would provide headroom, but is not implemented
automation or a guaranteed $10 limit. Pausing must disable auto-start as well as
stop the machine; storage and stopped-machine rootfs still incur charges. A hard
$10 requirement needs a host with an enforced spending cap. No monitoring or
automatic hosting cutoff has been deployed or measured.

## Current name and preserved data

The user-selected name `incident-copilot` is deployed at
[incident-copilot.fly.dev](https://incident-copilot.fly.dev/). The old app was
retired after snapshot restoration, identical ledger/replay fingerprints, matching
API-key digests and six HTTPS checks. One run, one replay and $0.060967 of charges
were preserved; no new LLM calls were made. Current machine is `7843e61a994648`,
current encrypted 1 GB volume is `vol_4m3mklle2q5n32zv`. The daily API cap remains
$0.50. See [migration verification](name-migration.md). Historical initial
deployment records below keep their original names and resource identifiers.

## Updating the app

Edit locally, run relevant tests, commit the code and build a fresh tagged Linux
AMD64 image. On this Mac the verified standalone Buildx binary is in ignored
`.bootstrap/`; Docker with a normally installed Buildx plugin can use
`docker buildx build` instead. After local tests and container verification:

```bash
COPILOT_DEPLOY_TAG=$(git rev-parse --short HEAD)
.bootstrap/docker-buildx/buildx-v0.38.0.darwin-arm64 build --builder colima --platform linux/amd64 --load -t "registry.fly.io/incident-copilot:${COPILOT_DEPLOY_TAG}" .
.bootstrap/flyctl/flyctl auth docker
docker push "registry.fly.io/incident-copilot:${COPILOT_DEPLOY_TAG}"
.bootstrap/flyctl/flyctl deploy --config fly.toml --image "registry.fly.io/incident-copilot:${COPILOT_DEPLOY_TAG}" --ha=false
```

Deploy between investigations: replacing the single machine's process may
interrupt active runs, and their unsettled reservations remain held. Completed
replays and budget data reside on the existing volume; do not create a new volume
or second machine for a routine update. Secrets remain configured. Verify HTTPS
health, the deployed image and persisted data afterward. The public URL stays the
same. Database/schema changes require their own migration review.

The current idle mechanism follows HTTP traffic, not background-job activity.
Closed-browser investigations may be interrupted by idle stopping; that case has
not been verified or protected by a job-aware idle mechanism. Keep this limitation
separate from the completed-run persistence checks.
