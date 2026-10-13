# Live-demo access

The new gate and navy/cream UI are implemented locally; deployment remains on
hold for user review. The existing hosted build still allows budgeted live runs
without this access gate. No production access token has been configured yet.

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
- “Oops! You don’t have agent access. Hint: check Armaan’s portfolio or résumé.”

Without access, clicking the button focuses the notice and makes no live-run
request. Authorized visitors also need a configured server model and available
budget. Both `POST /api/runs` and `POST /api/investigate` verify the signed session
before admission or SDK creation. Expired, modified and revoked sessions return
401, and cross-origin browser requests return 403. Public reads remain available.
API responses use `Cache-Control: no-store` so access status is not cached.

Configure a randomly generated `DEMO_ACCESS_TOKEN` of at least 32 characters in
the server environment (a Fly secret for deployment). A missing/short token closes
the gate. Changing the token revokes existing sessions and links. The token must
not be committed to source code or embedded in shipped frontend files. A preview
fixture token is local-only and must not be reused for deployment.

Anyone possessing a valid access link can unlock the demo. Publishing one on a
public README makes it publicly copyable; this gate does not verify a visitor’s
referring site or identity. Keep the existing daily budget, per-visitor rate limits
and concurrency controls. Unlock requests make no model calls. The standing
public API cap remains $0.50/day; the local 50% budget fixture is not provider spend.

Before the next deployment, configure a fresh production token securely, verify
both modes and both paid endpoints, and provide the resume/portfolio access link.
Deployment remains a separate action after local visual review. Do not publish
the preview link as the production access link.
