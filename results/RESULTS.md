Measured offline baselines and live-model runs on synthetic telemetry. Transport is recorded per experiment.

| Run | Transport | Cases | Outcome correct (95% CI) | Errors | Total observed API cost | p50 / p95 seconds |
|---|---|---:|---|---:|---:|---|
| live-cert_expiry-2026-10-11-2c5ec81643c4 | live LLM + in-memory MCP | 1 | 0.0% (0.0–79.3) | 0 | $0.024902 | 19.132095 / 19.132095 |
| live-config-2026-10-11-efc42552331a | live LLM + in-memory MCP | 1 | 100.0% (20.7–100.0) | 0 | $0.036508 | 22.930292 / 22.930292 |
| live-slow_dependency-2026-10-11-5fe3b18769bc | live LLM + in-memory MCP | 1 | 100.0% (20.7–100.0) | 0 | $0.072066 | 40.251977 / 40.251977 |
| live-smoke-2026-10-11-98d7a0333c47 | live LLM + in-memory MCP | 2 | 100.0% (34.2–100.0) | 0 | $0.087672 | 31.311510 / 34.786287 |
| live-traffic_spike-2026-10-11-8c9a12acc1d5 | live LLM + in-memory MCP | 1 | 100.0% (20.7–100.0) | 0 | $0.097339 | 45.331751 / 45.331751 |
| python312-latest-deploy-d27b85c6db2d | deploy history | 60 | 5.0% (1.7–13.7) | 0 | $0.000000 | 0.000001 / 0.000002 |
| python312-mcp-rules-challenge-d2808d804229 | in-memory MCP | 24 | 33.3% (18.0–53.3) | 0 | $0.000000 | 0.084101 / 0.144860 |
| python312-mcp-rules-original-349e3b4a5bd7 | in-memory MCP | 60 | 100.0% (94.0–100.0) | 0 | $0.000000 | 0.288247 / 0.414055 |
| python312-rules-challenge-77334f82ea35 | direct simulator log search | 24 | 33.3% (18.0–53.3) | 0 | $0.000000 | 0.000138 / 0.000960 |
| python312-rules-original-bd66349c44c0 | direct simulator log search | 60 | 100.0% (94.0–100.0) | 0 | $0.000000 | 0.001171 / 0.001318 |

Outcome accuracy counts a correct abstention on redacted cases. Latency quantiles describe successful runs; failure elapsed time and observed spend remain in JSON records. API cost is calculated from provider-reported token usage at list prices, not reconciled against an invoice. Structured action compatibility is not a remediation-quality score. The live smoke runs are too small to establish reliability; see docs/live-smoke.md, docs/live-config-smoke.md and docs/live-remaining-smoke.md for citation checks, failures and recommendation limitations.

Retrieval smoke checks (small author-written query set):
- tfidf: 14 queries, recall@1 100.0%, recall@3 100.0%.

Version-specific recovery policy lookup (offline structured reader, not an LLM ablation):

| Retrieval | Exact policies | Correct unknown-version abstentions |
|---|---:|---:|
| no-retrieval | 0/12 | 3/3 |
| tfidf | 12/12 | 3/3 |
