# Initial Fly deployment verification — 2026-10-13

This records the initial deployment at `incident-copilot-armaankols.fly.dev`.
The subsequent [name migration](name-migration.md) moved it to
[incident-copilot.fly.dev](https://incident-copilot.fly.dev/) and retired the old app.
The measurements and original resource identifiers below remain unchanged.
One authorized hosted Haiku investigation correctly diagnosed orders/memory_leak,
returned the OOMKilled excerpt, and stopped on a model submission. It had zero
validation rejections, truncations, runtime errors or billing uncertainty.
This single synthetic smoke case does not establish reliability or recovery effectiveness.

## Deployment

- Personal Fly organization, `sjc` region.
- One machine: `08034d7bd172d8`, shared CPU, 1 CPU, 1024 MB RAM.
- One encrypted 1 GB volume: `vol_r68q10897ywgo2j4`, mounted at `/data`.
- One Uvicorn worker running as UID 10001; database owner UID 10001.
- Python 3.12.15; packaged runtime SHA-256 verified against local files over SSH.
- Image `registry.fly.io/incident-copilot-armaankols:354393a`, tested locally on Linux AMD64.
  Uploaded index digest: `sha256:6e4002e72521c807d583bfcccda6e82a37c4ca2fcfa7cd90273c27d577ed2c47`.
  Deployed AMD64 manifest: `sha256:e15380d62e331f590334d0c852260ac2ac99f34b541c17b45a45b150ff08372b`.
- Existing server key staged through secret-import stdin, stored as a Fly secret.
  It is excluded from image context, repository and verification records.
- No remote build machine, second application machine, paid add-on or dedicated IPv4 was provisioned.

HTTPS GET checks returned **200** for `/healthz`, `/`, `/static/demo.js`,
`/api/config` and `/api/replay`. Health reported the server key configured.
Fly deployment checks and DNS verification passed.

The user approved a **$0.50/day public API budget**, separate from standing
**$0.50/test development approval**, and a **monitored $10/month hosting target**
after discussing manual billing checks near $8. Hosting has no enforced bill cap
or automated cutoff. Hosting spend has not been reconciled against an invoice.

## Hosted Haiku smoke

Model: `claude-haiku-4-5-20251001`; prompt:
`evidence-v8-observation-id-submission`; TF-IDF retrieval; in-memory MCP.
The app selected seed **75014** for the requested original memory-leak fault.
To reproduce its scenario, call `generate(75014, 'memory_leak')`; this is a direct
scenario seed, not the evaluation CLI's base-seed argument.

| Measurement | Result |
|---|---|
| Expected / accepted cause | orders / memory_leak |
| Finalization | model_submission |
| Model / MCP calls | 8 / 19 |
| Tool requests | 19 |
| Agent latency | 26.397477 seconds |
| Input / output tokens | 50,892 / 2,015 |
| Cache-read / write tokens | 0 / 0 |
| Usage-derived cost | $0.060967 |
| Validation rejections / truncations | 0 / 0 |
| Exact evidence excerpts | 3 / 3 |
| Recovery | Controlled restart recommended; not executed |

Cost is calculated from server-captured provider usage using
[Anthropic list prices](https://platform.claude.com/docs/en/about-claude/pricing),
verified on 2026-10-13. It is not a reconciled invoice. Aggregate usage was
reconciled with cost; individual provider request/response payloads were not
captured from this hosted run. Local full returned trace is ignored by Git.
The $0.42 conservative token bound was checked before issuing the request.

The selected log observation contained:

```text
13:27:00 orders ERROR container terminated: OOMKilled (exit code 137)
13:50:00 orders ERROR rejected malformed request body (400) on /v1/profile
```

The returned excerpt was the earlier **OOMKilled** line, rather than the later
malformed-request error. The other citations were the orders memory summary and
its supported fault assessment. All three are exact substrings of selected
successful tool results. This exercises the corrected excerpt path on a new seed;
it does not establish arbitrary source relevance or general causality.

[Measured result](../results/live-fly-memory_leak-2026-10-13-ae9d2aebca07.json).
[View the saved hosted investigation](https://incident-copilot.fly.dev/?run=ae9d2aebca074348a6bae644f4993245).
Viewing this replay does not start a new model investigation.

## Budget and persistence checks

A Sonnet request returned **429**, because its conservative reservation exceeds
this daily cap. A second Haiku request immediately after the accepted run also
returned **429** for insufficient unreserved funds. Neither probe created another
run. These are actual hosted admission checks, not offline ledger fixtures.

After completion, SSH inspection measured **zero active reservations** and
**$0.060967** charged in the application ledger. The machine was then restarted.
The saved result remained byte-equivalent after canonical JSON comparison, and
`/api/config` retained the rounded charge **$0.061** and daily cap **$0.50**.
The server did not make another provider call to serve that replay.

With no web requests during the observation window, the machine was observed
**stopped 269.019 seconds** after the last HTTP request. Machine state was polled
every 15 seconds, so this is an observation time, not the exact shutdown instant.
The next HTTPS health request returned **200 in 3.698 seconds**, and the saved
replay and rounded $0.061 charge remained unchanged after wakeup. These are one
observed stop/wake cycle, not a latency guarantee. See
[deployment-verification.json](deployment-verification.json).
Automatic stopping follows HTTP traffic. Closed-browser background investigations
have not been protected by a job-aware idle mechanism or tested in that condition.
Completed-run persistence is separate from interrupted in-flight work; unsettled
reservations remain held until reviewed.

## Updates

GitHub pushes run offline CI; they do not automatically publish a release.
Routine updates build a new image, push it and redeploy to this same app/URL with
`--ha=false`, reusing the existing volume and secrets. Deploy between investigations.
See the tested workflow and manual hosting-budget procedure in
[deployment and operations](deployment.md).
