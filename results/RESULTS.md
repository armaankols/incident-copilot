Measured offline baselines and live-model runs on synthetic telemetry. Transport is recorded per experiment.

| Run | Transport | Cases | Outcome correct (95% CI) | Errors | Finalization | Total observed API cost | p50 / p95 seconds |
|---|---|---:|---|---:|---|---:|---|
| live-cert_expiry-2026-10-11-2c5ec81643c4 | live LLM + in-memory MCP | 1 | 0.0% (0.0–79.3) | 0 | not recorded | $0.024902 | 19.132095 / 19.132095 |
| live-config-2026-10-11-efc42552331a | live LLM + in-memory MCP | 1 | 100.0% (20.7–100.0) | 0 | not recorded | $0.036508 | 22.930292 / 22.930292 |
| live-fly-memory_leak-2026-10-13-ae9d2aebca07 | live HTTPS / Fly / in-memory MCP | 1 | 100.0% (20.7–100.0) | 0 | model_submission | $0.060967 | 26.397477 / 26.397477 |
| live-slow_dependency-2026-10-11-5fe3b18769bc | live LLM + in-memory MCP | 1 | 100.0% (20.7–100.0) | 0 | not recorded | $0.072066 | 40.251977 / 40.251977 |
| live-smoke-2026-10-11-98d7a0333c47 | live LLM + in-memory MCP | 2 | 100.0% (34.2–100.0) | 0 | not recorded | $0.087672 | 31.311510 / 34.786287 |
| live-traffic_spike-2026-10-11-8c9a12acc1d5 | live LLM + in-memory MCP | 1 | 100.0% (20.7–100.0) | 0 | not recorded | $0.097339 | 45.331751 / 45.331751 |
| live-v4-cert_expiry-2026-10-11-d25c89d17f9b | live LLM + in-memory MCP | 1 | 100.0% (20.7–100.0) | 0 | model_submission | $0.032570 | 22.802807 / 22.802807 |
| live-v4-missing_evidence-2026-10-11-e2dd981ee93f | live LLM + in-memory MCP | 1 | 100.0% (20.7–100.0) | 0 | step_budget | $0.110672 | 39.235019 / 39.235019 |
| live-v4-traffic_spike-2026-10-11-efcbd431f4ec | live LLM + in-memory MCP | 1 | 0.0% (0.0–79.3) | 0 | model_submission | $0.131559 | 56.094510 / 56.094510 |
| live-v5-missing_evidence-2026-10-12-a09d83c85244 | live LLM + in-memory MCP | 1 | 0.0% (0.0–79.3) | 0 | model_submission | $0.062069 | 34.690091 / 34.690091 |
| live-v5-traffic_spike-2026-10-12-2fa0a38e57f9 | live LLM + in-memory MCP | 1 | 0.0% (0.0–79.3) | 0 | model_submission | $0.091092 | 42.657947 / 42.657947 |
| live-v6-missing_evidence-2026-10-12-ec2fe2431647 | live LLM + in-memory MCP | 1 | 0.0% (0.0–79.3) | 0 | model_submission | $0.072745 | 39.605546 / 39.605546 |
| live-v6-traffic_spike-2026-10-12-af571910c196 | live LLM + in-memory MCP | 1 | 0.0% (0.0–79.3) | 0 | correction_limit | $0.083196 | 50.171236 / 50.171236 |
| live-v7-missing_evidence-2026-10-12-b1eb096c5e8a | live LLM + in-memory MCP | 1 | 100.0% (20.7–100.0) | 0 | model_submission | $0.046017 | 23.963900 / 23.963900 |
| live-v7-traffic_spike-2026-10-12-b13344078fec | live LLM + in-memory MCP | 1 | 0.0% (0.0–79.3) | 0 | correction_limit | $0.066144 | 32.630571 / 32.630571 |
| live-v8-edge-healthy_decoy_bad_deploy-2026-10-12-6fe371dfa1ba | live LLM + in-memory MCP | 1 | 100.0% (20.7–100.0) | 0 | model_submission | $0.023173 | 10.136017 / 10.136017 |
| live-v8-edge-healthy_decoy_slow_dependency-2026-10-12-565a7be5c36e | live LLM + in-memory MCP | 1 | 100.0% (20.7–100.0) | 0 | model_submission | $0.069134 | 28.526991 / 28.526991 |
| live-v8-edge-missing_evidence-2026-10-12-e689ff96783b | live LLM + in-memory MCP | 1 | 100.0% (20.7–100.0) | 0 | model_submission | $0.059857 | 26.653090 / 26.653090 |
| live-v8-edge-paraphrased_memory-2026-10-12-535a39be1b0d | live LLM + in-memory MCP | 1 | 100.0% (20.7–100.0) | 0 | model_submission | $0.039318 | 20.815908 / 20.815908 |
| live-v8-edge-paraphrased_traffic-2026-10-12-102febf5812e | live LLM + in-memory MCP | 1 | 100.0% (20.7–100.0) | 0 | model_submission | $0.034189 | 18.473331 / 18.473331 |
| live-v8-edge-recovered_cert_expiry-2026-10-12-14707fd79e76 | live LLM + in-memory MCP | 1 | 100.0% (20.7–100.0) | 0 | model_submission | $0.033831 | 15.390886 / 15.390886 |
| live-v8-edge-recovered_config_error-2026-10-12-b05d34b92e6a | live LLM + in-memory MCP | 1 | 100.0% (20.7–100.0) | 0 | model_submission | $0.027572 | 15.454498 / 15.454498 |
| live-v8-fresh-bad_deploy-2026-10-12-9325ca477558 | live LLM + in-memory MCP | 1 | 100.0% (20.7–100.0) | 0 | model_submission | $0.035465 | 18.609498 / 18.609498 |
| live-v8-fresh-cert_expiry-2026-10-12-c4ff87345fd9 | live LLM + in-memory MCP | 1 | 100.0% (20.7–100.0) | 0 | model_submission | $0.017638 | 10.099435 / 10.099435 |
| live-v8-fresh-config_error-2026-10-12-0ae903125704 | live LLM + in-memory MCP | 1 | 100.0% (20.7–100.0) | 0 | model_submission | $0.025144 | 11.766235 / 11.766235 |
| live-v8-fresh-memory_leak-2026-10-12-25eb65130926 | live LLM + in-memory MCP | 1 | 100.0% (20.7–100.0) | 0 | model_submission | $0.032423 | 17.700555 / 17.700555 |
| live-v8-fresh-slow_dependency-2026-10-12-fe10f352563a | live LLM + in-memory MCP | 1 | 100.0% (20.7–100.0) | 0 | model_submission | $0.064760 | 29.773226 / 29.773226 |
| live-v8-missing_evidence-2026-10-12-6d8be1c17d98 | live LLM + in-memory MCP | 1 | 100.0% (20.7–100.0) | 0 | model_submission | $0.042555 | 22.473473 / 22.473473 |
| live-v8-traffic_spike-2026-10-12-8545540d7b4e | live LLM + in-memory MCP | 1 | 100.0% (20.7–100.0) | 0 | model_submission | $0.053230 | 26.145909 / 26.145909 |
| python312-latest-deploy-d27b85c6db2d | deploy history | 60 | 5.0% (1.7–13.7) | 0 | not applicable | $0.000000 | 0.000001 / 0.000002 |
| python312-mcp-rules-challenge-d2808d804229 | in-memory MCP | 24 | 33.3% (18.0–53.3) | 0 | not applicable | $0.000000 | 0.084101 / 0.144860 |
| python312-mcp-rules-original-349e3b4a5bd7 | in-memory MCP | 60 | 100.0% (94.0–100.0) | 0 | not applicable | $0.000000 | 0.288247 / 0.414055 |
| python312-rules-challenge-77334f82ea35 | direct simulator log search | 24 | 33.3% (18.0–53.3) | 0 | not applicable | $0.000000 | 0.000138 / 0.000960 |
| python312-rules-original-bd66349c44c0 | direct simulator log search | 60 | 100.0% (94.0–100.0) | 0 | not applicable | $0.000000 | 0.001171 / 0.001318 |
| v6-offline-mcp-rules-v2-f9ab8d2c3010 | in-memory MCP | 24 | 33.3% (18.0–53.3) | 0 | not applicable | $0.000000 | 0.115053 / 0.196369 |
| v6-offline-rules-original-a1f4beae8114 | direct simulator log search | 60 | 100.0% (94.0–100.0) | 0 | not applicable | $0.000000 | 0.001242 / 0.001364 |
| v6-offline-rules-v1-85dd41c2f0b1 | direct simulator log search | 24 | 33.3% (18.0–53.3) | 0 | not applicable | $0.000000 | 0.000142 / 0.000983 |
| v6-offline-rules-v2-dadf8db45d5d | direct simulator log search | 24 | 33.3% (18.0–53.3) | 0 | not applicable | $0.000000 | 0.000141 / 0.000980 |
| v7-offline-rules-original-6c983d4b3bfc | direct simulator log search | 60 | 100.0% (94.0–100.0) | 0 | not applicable | $0.000000 | 0.001215 / 0.001420 |
| v7-offline-rules-v1-26568fb2f235 | direct simulator log search | 24 | 33.3% (18.0–53.3) | 0 | not applicable | $0.000000 | 0.000143 / 0.000994 |
| v7-offline-rules-v2-5607de2ad466 | direct simulator log search | 24 | 33.3% (18.0–53.3) | 0 | not applicable | $0.000000 | 0.000144 / 0.001006 |
| v8-offline-rules-original-ccca05c87f33 | direct simulator log search | 60 | 100.0% (94.0–100.0) | 0 | not applicable | $0.000000 | 0.001280 / 0.001382 |
| v8-offline-rules-v1-76a7aece1c0a | direct simulator log search | 24 | 33.3% (18.0–53.3) | 0 | not applicable | $0.000000 | 0.000146 / 0.001034 |
| v8-offline-rules-v2-20c7e2b15ee1 | direct simulator log search | 24 | 33.3% (18.0–53.3) | 0 | not applicable | $0.000000 | 0.000140 / 0.000984 |

Outcome accuracy counts a budget-forced abstention as correct on redacted cases; it does not demonstrate model-selected stopping. Finalization is persisted for new runs or derived from reviewed saved traces; older runs may show not recorded. Latency quantiles describe runs without exceptions; diagnostic misses remain included. Failure elapsed time and observed spend remain in JSON records. API cost is calculated from provider-reported token usage at list prices, not reconciled against an invoice. Structured action compatibility is not a remediation-quality score. These small live smoke runs do not establish reliability; see docs/deployment-live.md for the hosted memory-leak verification, docs/live-v8-edge-cases.md for the prior seven challenge outcomes and remaining presentation limitations, docs/live-v8-fresh-faults.md for the prior five fresh-seed outcomes, docs/live-v8-validation.md for the prior traffic/redacted pair, docs/live-v7-validation.md for prior mixed results, and docs/observation-id-evidence.md for the interface changes.

Retrieval smoke checks (small author-written query set):
- tfidf: 14 queries, recall@1 100.0%, recall@3 100.0%.

Version-specific recovery policy lookup (offline structured reader, not an LLM ablation):

| Retrieval | Exact policies | Correct unknown-version abstentions |
|---|---:|---:|
| no-retrieval | 0/12 | 3/3 |
| tfidf | 12/12 | 3/3 |

Offline replay of the recorded missing-evidence query schedule (not new model behavior):
- Original live schedule: 12 model calls, 49 tool calls.
- New policy replay: 7 scripted responses, 32 MCP executions, 0 cache hits, 2 skipped requests; stopped by tool_limit.
- Zero provider calls in this replay; it does not measure live-model accuracy, cost or stopping behavior.

Offline six-fault evidence gates (template-specific deterministic checks, not LLM accuracy):
- 3528 service/fault assessments across 84 original and correlated-v2 scenarios: 78/78 expected supports accepted, 3450/3450 unsupported pairs rejected, 0 false supports.
- 78 constructed compact submissions accepted; largest 135 UTF-8 bytes. Recorded v6 traffic submission: 1747 bytes; constructed compact traffic submission: 130 bytes. These are payload byte sizes, not measured model token usage.
- Zero provider calls. These checks cover known synthetic fault patterns; they do not prove causality or generalize to arbitrary production faults. Compact submissions are constructed fixtures, not new model responses.

Offline replay through the observation-ID interface (recorded selections with quote fields removed, not new model behavior):
- 8 scripted responses, 16 MCP executions, 2 rejected unsupported submissions; final search/traffic_spike diagnosis with recovery blocked and no action.
- 3/3 server-attached excerpts are exact source substrings; zero provider calls. The original live run remains a recorded diagnostic miss.
