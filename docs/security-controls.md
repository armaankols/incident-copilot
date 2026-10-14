# Request and access controls

The HTTP request guard accepts at most 8 KiB of body data, including chunked
requests and requests with misleading Content-Length headers. Body reads have
a ten-second deadline. Both paid routes check the signed access session before
JSON parsing. Field lengths are bounded; validation errors omit submitted values.

Request quotas use the existing persistent SQLite database and an atomic
transaction. Each fixed UTC minute allows 240 requests per visitor, 1,200 requests
globally, and 20 access exchanges per visitor. Rejections include Retry-After.
The quotas allow one-second investigation polling and persist across process
restarts. Only the current minute's counters are retained; visitor keys are IP
hashes. These controls require the same single-machine/shared-database constraint
as the model budget. The Docker command limits simultaneous HTTP connections/tasks
to 32. Application quotas do not impose a hosting billing ceiling.

GET/HEAD `/healthz` uses an independent per-visitor quota of 240/minute. Public
global/visitor quota exhaustion cannot consume the health allowance. Body limits
and the Uvicorn connection/task limit still apply. Automatic trailing-slash
redirects are disabled: `/api/access/` returns 404 with no Location header, so
TLS termination cannot turn an access-token POST into an HTTP redirect.

Fly-Client-IP is used only with TRUST_FLY_PROXY=1, a Fly runtime, and an immediate
socket peer in TRUSTED_PROXY_CIDRS. Duplicate, malformed or comma-separated values
fall back to the socket address. IPv6 identities are canonicalized before hashing.
Uvicorn's automatic proxy-header rewriting is disabled so X-Forwarded-For cannot
replace the socket peer before the guard runs.

The allowlist in fly.toml is the measured IPv4 Fly ingress peer of the existing
machine, not a blanket private-network range. Public services must remain only
Fly's HTTP/TLS handlers on ports 80 and 443. Reverify the peer and header overwrite
behavior after changing the machine/network/ingress. A changed or untrusted peer
falls back to its socket address; visitors can then share a quota until the
allowlist is reverified. Organization administrators and processes inside the
machine remain trusted. Do not enable Fly header trust on local previews.

Investigation and unexpected transport failures return a generic error with a
reference ID. Application diagnostics log that ID and the exception class, without
the exception message, submitted token or traceback. Older replay error fields
are sanitized when served; their stored payloads are preserved.

MCP responses marked `isError` are also replaced with generic reference errors
before reaching model context or traces. Historical error-prefixed tool results
are redacted on saved/running response reads without mutating persisted payloads
or in-memory progress. Successful synthetic evidence remains readable.

Only an explicit Anthropic 400 `invalid_request_error` identifying insufficient
credit is classified as a confirmed rejection. It returns a friendly temporary
unavailability message and releases the unused reservation while retaining usage
from earlier successful calls. Unknown 400s, server failures, timeouts and
disconnects still retain the conservative reservation. SDK retries remain off.

The daily budget resets at midnight in `America/Los_Angeles`, following Pacific
daylight saving time. The config response reports the accounting date, timezone,
next reset timestamp and spend from the same date snapshot.

The hosted $0.50 value is a start threshold, not a strict final-spend ceiling.
Admission atomically checks existing charges plus all active holds against the
threshold, without adding the proposed new hold to that comparison. A run can
start at $0.49 and finish above $0.50; no further runs start at or above $0.50.
The proposed run's maximum must still fit the nominal daily limit, keeping Sonnet
blocked at its existing bound. Concurrency and visitor quotas remain enforced.
An active hold can block another start until its reported usage is settled.

Active model reservations count across all Pacific days. A run spanning midnight is
conservatively charged in full to its settlement day, including any earlier-day
usage, so it cannot vanish from that day's admission total. Repeated settlement
cannot move an old charge. A one-time, atomic migration converts legacy UTC days
only when admission time, the recorded UTC settlement day and migration time
identify a single possible Pacific date. Ambiguous history blocks migration for
review. Original UTC days remain in `legacy_utc_days`; charges, reservations and
raw replay payloads are preserved. A durable timezone marker prevents remigration.

The access-link design remains a shared possession-based gate, not user accounts.
The token is configured as a Fly secret and must not be committed or baked into an
image. Both paid endpoints still apply the durable investigation budget, hourly
run quota, and concurrency limits after access validation. Production verification
can use the over-budget Sonnet selection to check admission without model calls.
