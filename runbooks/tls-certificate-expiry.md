# Runbook: Expired TLS certificate

## Symptoms
A sudden cliff in errors on callers of one service, starting at an exact minute. Callers log TLS handshake failed and x509 certificate has expired with a notAfter timestamp. The target service itself looks quiet: request rate collapses and CPU drops because no traffic reaches it.

## Diagnosis
Distinguish the caller emitting the log from the peer named after "calling". In a peer-verification failure, the peer may own the expired certificate; normal peer application metrics do not establish certificate health because rejected TLS connections may never reach the application. Do not infer ownership solely from the caller's error rate. Search the suspected owner's WARN/INFO logs for local certificate-expiry and renewal records, and use check_certificate to obtain corroborating ownership/expiry evidence. If records conflict or ownership remains unknown (including ambiguous mutual-TLS failures), use insufficient_evidence rather than guessing.

## Remediation
Recommend renewal only for the owner supported by the certificate assessment. Verify issuer, expiry, trust chain and the service-specific rotation procedure, including any required trust-bundle overlap. Confirm the renewal/alerting policy before changing automation; no action is executed by the investigation.
