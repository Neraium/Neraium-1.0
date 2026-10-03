# Neraium 1.0 Production V2 release certification

Certification completed 2026-10-03 00:20 UTC. Result: **PASS; ready for first customer onboarding**.

## Immutable release identity

| Item | Identity |
| --- | --- |
| Source release | `94007976e6a854780541e29681035890ed074bfd` |
| Release tag | `neraium-1.0-production-v2-2026-10-02` |
| API and worker image | `680779862188.dkr.ecr.us-east-2.amazonaws.com/neraium-prod-api@sha256:d57f44d3f1af85d6a6eddfcf29c8b99198a63cd5de58ae21408d7fae90594816` |
| API task definition | `arn:aws:ecs:us-east-2:680779862188:task-definition/neraium-prod-api:338` |
| Worker task definition | `arn:aws:ecs:us-east-2:680779862188:task-definition/neraium-prod-worker:332` |
| Connector executor | EC2 `i-081d0aba82dba64e7`, private endpoint `10.40.32.20:8443`, ECR tag `connector-executor-20261002-2`, digest `sha256:925304f0b5d2dad404a7f632606a24aa5ae9d8327286565de22be5c17807988a` |
| Connector authority | Task definitions reference the production executor authentication secret ARN; the instance user data references the authentication and TLS secret ARNs. Values are intentionally omitted. |
| Controlled egress | Network Firewall policy `neraium-prod-v2-connector-egress-policy`, strict TLS SNI allowlist for the approved synthetic host and required AWS service hosts, default established application layer drop; stateless IP deny rule attached. |
| Rollback reference | API `neraium-prod-api:337`, worker `neraium-prod-worker:331`, prior digest `sha256:d696b79737b8aab4554dbe9e48bee18100dacef59b2f5bd9a2f6c0eca81fe052`. Database rollback is forward fix only. |

The image retains build marker `6743ad49d904b474799620c48493c2590ddd1e43` because it was built before the closeout commit. The release SHA includes the closeout overlay and deployment configuration. The running image's `runtime_postgres.py`, `connector_execution.py`, and `apply_telemetry.py` SHA-256 values matched those files at the release SHA: `fb7bbc1de388da0a5063b41c6cea19d388788866ef40a8145e21f7f326b0b4e5`, `0f4138b94f3fe7b42a256acfc483edaf64af85a465e07faefa30591cae2620c7`, and `a9a0c1d19d0c55cedda0f3649f6ab03c44d4818761131a87ad13a5` respectively.

## Migration and privilege ledger

Production runtime PostgreSQL read confirmed exactly these entries, in order, and verified their schemas: `002_create_telemetry_connection_tables`, `003_seed_telemetry_canonical_signal_concepts_v1`, `004_extend_telemetry_ingestion_runtime`, `005_persist_canonical_analysis_results`, `006_preserve_telemetry_source_representation`, `007_create_relationship_temporal_state`, `008_create_relationship_lineage_v2_artifacts`, `009_create_endpoint_analysis_executions_v2`, `010_allow_same_concept_physical_endpoints`.

The runtime identity is `neraium_telemetry_runtime`. An initial read-only probe found that it had inherited `INSERT`, `UPDATE`, and `DELETE` on `telemetry.schema_migrations`. The migration identity `neraium_telemetry_migration` executed `REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON telemetry.schema_migrations FROM neraium_telemetry_runtime`. A fresh runtime task then confirmed `SELECT` remains granted, all four ledger write privileges and telemetry schema `CREATE` are denied, and the role has no superuser, create database, or create role attributes. The migration ledger and persisted execution remained intact. `tests/test_telemetry_runtime_grants.py` records this privilege contract for environments with `NERAIUM_TEST_TELEMETRY_RUNTIME_DSN`.

## Customer-like synthetic acceptance

All application requests used `https://app.neraium.com/api` with a real session cookie and workspace selection. Synthetic account and facility workspaces were created only for certification. The approved source was API Gateway `bfzcudq5o2` backed by Neraium Lambda `neraium-prod-v2-synthetic-https-smoke`; its final code SHA-256 is `e8BhABDKMfnW/X+Fh4N/Oh86Jg5MenJod989kiHazq8=`. The 40-observation-per-tag handler used for the passing ingestion is preserved at [synthetic-40-handler.py](neraium-1.0-production-v2-2026-10-02/synthetic-40-handler.py), SHA-256 `b0030aa1fb13a90c101530fb22fb0b33d8f38bf9850a5e160640cf5dc266f374`. The final 80-observation-per-tag handler is preserved at [synthetic-80-handler.py](neraium-1.0-production-v2-2026-10-02/synthetic-80-handler.py), SHA-256 `6d5a5f44a8ec5bc728abe7d6e10ab1c621f833c0eca3f2bdb1bd8b9afac7d731`. No customer telemetry or source credentials were used.

| Check | Result |
| --- | --- |
| Login, workspace and facility authorization | PASS |
| Approved HTTPS connection, isolated validate/discover execution | PASS |
| Worker ingestion, PostgreSQL persistence, V2 analysis | PASS: run `62081a70-3ac1-4c6c-9245-00f772e9af1d`, 80 accepted observations |
| Same-concept endpoint identity | PASS: two distinct physical endpoint IDs, one canonical flow concept, one relationship |
| Customer result list/detail and evidence | PASS: one listed result; detail returned 80 observation lineage records with `lineage_verified=true` |
| DB result row | PASS: `telemetry-endpoint-execution.v2`, 595791 result bytes, one relationship reference |
| Unauthenticated and foreign workspace | PASS: 401 and 404 respectively |
| Wrong connection, run, execution reference | PASS: 404, 404, and 422 respectively |
| Tampered authority | PASS in focused authority and result regression suites |
| Unavailable executor | PASS fail-closed behavior in focused connector regression suite; no live executor outage induced |
| Dynamic credential writes and response exposure | PASS: write rejected 409; canary absent from connection, list, detail, and error responses |
| Controlled egress and dynamic secret writes | PASS: firewall READY, allowlist and deny policy attached; API/worker task settings enable controlled egress and disable dynamic writes |
| Rolling API restart and persisted retrieval | PASS: new healthy API task on revision 338; same detail response SHA-256 and verified lineage after fresh login, with no analysis rerun |

Acceptance execution reference: `telemetry-endpoint-execution.v2:10e7a6ab7525950a34494782c701516f707791e9d2894c40d9370f7010659402`. Result digest: `telemetry-endpoint-result.v2:3bb3fc3d9ff8da1c3dae00108ebbe44de4abd615984ca9953b90b3e1639a56d8`. Customer detail HTTP body SHA-256 before and after restart: `a74680170172552f1da330d7457344d91686181223e5c1be9e6efc59e630b458`. Synthetic ZIP archive SHA-256 values: 40-per-tag `055dfc0433a32b5a7dd3cf232930183f9aedaa0b0634aba911a728bac2c1a8dd`, 80-per-tag `7bc0610010ca31f9d6fd7f8587837f3a1f3a260e4c7a726877df3d9221daceaf`.

Focused local regression suites: **77 passed, 3 skipped** for the V2 product, connector, authorization, migration, and V1 analysis paths; **150 passed, 4 failed, 1 skipped** for the additional authority, result, route, and window paths. The frontend `TelemetryConnectionsWorkspace` component suite passed **7 tests**, including verified V2 list selection and detail retrieval. PostgreSQL skips require optional local DSNs; live production DB probes verified the deployed ledger, grant, and result path. The four failures are confined to the retired legacy CSV connector upload route's error body. It returns the required `410` status and does not execute legacy connector activity, but its upload error wrapper replaces the expected structured retirement detail with a generic import error. All four failures reproduced in an isolated clean checkout of release SHA `94007976`; they are not caused by unrelated dirty files and do not affect the supported customer V2 path. V1 analysis and result compatibility tests passed.

Known limitation: the first synthetic connector run encountered retryable executor `502` responses and `network_retry_exhausted`. Subsequent validation and ingestion succeeded; later validation of the larger 160-record synthetic response succeeded three times. The failed attempts did not bypass scope, egress, credential, or persistence controls. This is recorded for operations follow-up and was not reproduced as a continuing customer-path failure.

The synthetic connection was disabled and the synthetic account deactivated after certification. The revoked session returned `401`. The unrelated dirty worktree files were left untouched.
