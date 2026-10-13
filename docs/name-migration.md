# Name migration — 2026-10-13

The current demo URL is [incident-copilot.fly.dev](https://incident-copilot.fly.dev/).
The user selected `incident-copilot` after a read-only Fly availability check.
The old app `incident-copilot-armaankols` has been retired.

The existing machine was already stopped. Its automatic startup was disabled and
API budget temporarily set to zero, then it was started solely for read-only data
inspection. No active reservations were present. It was stopped before creating
a volume snapshot, preventing changes while the database was copied.

Snapshot `vs_yG1JoQj1Vb5ZuOjyG10owaK` restored into the new encrypted 1 GB
`copilot_data` volume. The existing verified image was copied to the replacement
registry without a rebuild; image digest and packaged source fingerprint stayed
unchanged. API-secret metadata digests matched between apps; values were not
printed or committed.

Before retirement, verification measured:

- **Identical logical database SHA-256** across both `runs` and `replays` tables.
- **1 run row and 1 saved replay**, with the replay payload hash unchanged.
- **$0.060967 charged**, preserved exactly; no active reservations.
- **$0.50/day** restored API budget, configured server key, and Sonnet rejected
  with **429** before provider calls.
- **200** on six HTTPS routes, including the migrated saved-run endpoint.
- One shared CPU/1024 MB machine in `sjc`, one encrypted 1 GB volume, UID 10001,
  one worker, database owner UID 10001, and unchanged runtime source fingerprint.

The original app was destroyed only after those checks passed. A final check found
only `incident-copilot` in the personal organization, one volume attached to the
replacement, and HTTPS health still returning 200. The old URL is retired; no
redirect service remains running. Temporary resource overlap occurred during the
migration; its hosting charge has not been reconciled against an invoice.

**No additional LLM calls were made by the migration checks.** No application
logic, model pin, token bounds or daily API budget changed. Prior live-model results
remain historical records of the original deployment and are not regraded.

New machine: `7843e61a994648`; new volume: `vol_4m3mklle2q5n32zv`.
Registry image: `registry.fly.io/incident-copilot:354393a`.
The source snapshot and the original machine/volume identifiers are retained in
[measured migration record](migration-verification.json).

[View the migrated saved investigation](https://incident-copilot.fly.dev/?run=ae9d2aebca074348a6bae644f4993245)
without starting another model request. Routine updates now use the new app and
registry name; see [deployment operations](deployment.md).

Hosting remains a monitored $10/month target with manual billing checks near $8,
not a hard bill cap or automated cutoff. Idle stop/start remains configured; the
previous deployment's measured stop/wake cycle is historical, not a new timing
measurement on this machine. Closed-browser background investigations still lack
job-aware idle protection.
