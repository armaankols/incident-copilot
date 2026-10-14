# Live-demo access

The access gate and request security controls were deployed on 2026-10-13 to
the existing machine and volume. A fresh production access token is configured
as a Fly secret. Both paid endpoints reject unauthenticated requests with 401;
authorized over-budget probes return 429 before model calls. Existing ledger
rows, replay payloads and charges were preserved. See
[verification](security-verification.json) and [controls](security-controls.md).

The ordinary URL shows the offline sample and public saved investigations.
A special link has this form:

```
https://incident-copilot.fly.dev/#access=TOKEN
```

The frontend removes the fragment before sending the token in the JSON body of
`POST /api/access`. A successful exchange sets a two-hour, HttpOnly, SameSite=Strict
cookie scoped to `/api`; it is Secure on non-localhost deployments. The signed
cookie contains an expiry, random nonce and HMAC, without the link token. Visiting
the ordinary URL in the same browser after unlocking retains access until the
session expires. Use a private window to preview the no-access message.

Both modes use the same button and styling. Visitors see one of:

- “Thanks for checking out Armaan’s profile. You have agent access!”
- “Oops! You don’t have agent access. Hint: click in from Armaan’s portfolio or résumé.”

Without access, clicking the button focuses the notice and makes no live-run
request. Authorized visitors also need a configured server model and available
budget. Both `POST /api/runs` and `POST /api/investigate` verify the signed session
before admission or SDK creation. Expired, modified and revoked sessions return
401, and cross-origin browser requests return 403. Public reads remain available.
API responses use `Cache-Control: no-store` so access status is not cached.

Configure a randomly generated `DEMO_ACCESS_TOKEN` of at least 32 characters in
the server environment (a Fly secret for deployment). A missing/short token closes
the gate. Changing the token revokes existing sessions and links. The owner has
approved publishing the production access link in the README for portfolio
visitors. Keep it out of runtime source and shipped frontend files. A preview
fixture token is local-only and must not be reused for deployment.

Anyone possessing a valid access link can unlock the demo. Publishing one on a
public README makes it publicly copyable; this gate does not verify a visitor’s
referring site or identity. Keep the existing daily budget, per-visitor rate limits
and concurrency controls. Unlock requests make no model calls. The standing
public API start threshold is $0.50/day, resetting at midnight Pacific. A final
run may finish above that amount; new starts stop once the threshold is reached.
Active holds still count for concurrent admission. The local 50% budget fixture
is not provider spend.

The production portfolio/resume link is stored locally in the ignored,
owner-readable `.bootstrap/demo-access-link.txt` and deliberately published under
“Open live demo with agent access” in the README. It is not included in the app
image. Use that link rather than the preview fixture link.
Routine deployments preserve the production token; rotate it deliberately when
revoking existing links and sessions. Repeat access and budget checks after updates.
