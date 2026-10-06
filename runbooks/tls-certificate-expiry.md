# Runbook: Expired TLS certificate

## Symptoms
A sudden cliff in errors on callers of one service, starting at an exact minute. Callers log TLS handshake failed and x509 certificate has expired with a notAfter timestamp. The target service itself looks quiet: request rate collapses and CPU drops because no traffic reaches it.

## Diagnosis
The service named in the handshake error owns the expired certificate, not the callers reporting errors. Search logs of that service for certificate expiry warnings, often disabled auto-renewal.

## Remediation
Renew or rotate the certificate on the affected service immediately, then re-enable the auto-renewal job and add an expiry alert at 14 days.
