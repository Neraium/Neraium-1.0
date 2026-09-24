# S08 final disposition

**S08: FIXED.** The user-authorized separation of raw internal forensic evidence from customer failure presentation resolves the earlier deferral. The earlier INCOMPLETE decision below is historical and superseded by this final S08 closeout.

Root cause: data.py failure capture stores original exceptions in `errors` and `data_conditions`; evidence-store readers/annotations retained them, and customer endpoints/renderers consumed the same record. The problem was reuse of the forensic representation, not the retention of original evidence.

Complete trace and prospective view contract: [raw/s08-final/TRACE_AND_CONTRACT.md](raw/s08-final/TRACE_AND_CONTRACT.md), frozen before implementation. Runtime DB `evidence_runs.payload_json` and JSON mirrors remain unchanged. Historical rows need no sanitization migration. Failure constructors normally omit analytical hashes; imported/other records can be hash-bound, so no stored fields or digests are rewritten.

Customer view: `backend/app/core/failure_evidence_presentation.py:customer_evidence_view` allowlists terminal failure presentation. Category comes from the existing upload-error vocabulary in `data_conditions`; static explanation appears in `errors`/`historical_fact`. Safe status, run/reference IDs, valid timestamps and digest references remain. Unknown/free-text/nested fields, paths, SQL, credentials, source filenames and notes copied from internal failures are excluded. Digests reference the original stored artifact, not this projection. Completed analytical evidence passes through unchanged.

Covered boundaries: `/api/evidence/runs`, `/runs/{run_id}`, `/latest`, `/runs/{run_id}/integrity`; `/export/{run_id}` JSON/CSV/Markdown; `/package/{run_id}` JSON/PDF; interpretation input; returned audit-tag/feedback/status records; embedded failed evidence on latest-upload transport paths. There is no recursive sanitization of canonical result/evidence objects. Ordinary endpoints return the customer view even for an admin caller.

Internal forensic view: `GET /api/evidence/runs/{run_id}/forensic` requires an authenticated administrator in every environment, enforces existing workspace-scoped DB lookup, rejects nonfailed records, records a safe audit event and inherits no-store headers. It returns the exact stored record inside `internal_forensic_failure.v1`; no annotation, legacy import or historical rewriting. Anonymous/forged-development-role, viewer/operator and cross-workspace accesses are rejected. Authorized administrators are explicitly trusted with forensic detail; restrict that role and storage access in deployment.

Frontend ObservationCenter/EngineeringReasoning/Replay evidence reads and EvidencePackageExport/InvestigationOutcome consumers use the same existing endpoints and response schema. No frontend change or new dependency. Current S08 customer exposure is closed; this is not a fresh general security audit or a claim that all unrelated application risks disappeared.


---

## Earlier closeout record (retained historical evidence)

# Four finding traces and dispositions

- S07 HIGH, CONFIRMED_INFORMATION_EXPOSURE: auth.py read_auth_me/login/read_auth_sessions returned auth_store.get_session_record/list_sessions raw session_id, the same bearer used by get_user_by_session and logout cookies. Frontend authApi.js relies on credentialed cookies and stores an email marker; GovernanceAdminWorkspace revokes sessions by email. There is no separate refresh endpoint. FIXED at router presentation using SHA-256 management handles; single-session revoke resolves the handle server-side. Cookie HttpOnly/Secure/SameSite properties and storage unchanged. Hashing tokens at rest is DEFERRED_WITH_REASON: separate storage migration, outside JSON exposure closeout.
- S08 MEDIUM, CONFIRMED_INFORMATION_EXPOSURE: data.py error builders include technicalMessage/exception_type, with str(exc) from storage/enqueue failures; status, stream and latest transport summaries propagate these. Historical ingestion and connectors/csv/upload return exception-derived HTTP details. FIXED through an error-only APIRoute and transport-envelope presentation. Known static error categories remain useful; arbitrary exception text is omitted. Successful/canonical/evidence results are never traversed. Protected failure artifacts remain raw: identity-preserving migration/redaction is DEFERRED_WITH_REASON. Data-router exception logging retains event/class without exception text/traceback; general log retention/redaction remains a deployment limitation.
- S13 MEDIUM, CONFIRMED_EXPLOITABLE: evidence_store.build_evidence_export_csv quotes CSV syntax but accepts user source_name; evidence.py export_evidence_run serves it as text/csv. FIXED exclusively in CSV response presentation with quoted cells and apostrophe prefix for formula introducers and leading control characters. Raw service records, JSON, numerical evidence and source bytes remain unchanged. Spreadsheet re-import/re-saving can discard escaping; consumers must treat raw evidence as data.
- S14 MEDIUM, CONFIRMED_INFORMATION_EXPOSURE: health.py public /api/health and /api/ready returned runtime paths, configuration and readiness internals; verbose readiness added source/session details. main.py /health and / exposed internal worker state. FIXED with minimal status/service and admin-only verbose readiness. Existing /api/startup-status, /api/routes/debug and /api/observability/* are ADMIN_ONLY through require_admin_role; audit routes are reviewed separately below. /docs, /redoc and /openapi.json expose interface schemas (PUBLIC_SAFE), not customer data. Development/test deliberately relaxed authentication remains deployment responsibility; production/staging must be selected.

No analytical/evidence producer changes are authorized. Ranking, source identity, canonical replay, Measurable Consequence, retired Aletheia and optimization stack are frozen to the baseline.

## Final dispositions and exact remaining path

| Finding | Final disposition | Scope |
|---|---|---|
| S07 session JSON | FIXED | Login, me and admin list use non-authenticating management handles; revoke supports handles. Cookie bearer remains HttpOnly. At-rest token hashing is a separate deferred storage migration. |
| S08 upload errors | DEFERRED_WITH_REASON, partially fixed | Ordinary upload HTTP errors, historical intake errors, polling, SSE and latest failure envelopes sanitized; raw failed evidence retrieval/export remains below. |
| S13 spreadsheet export | FIXED | Only evidence CSV download cells escaped; raw/canonical records unchanged. |
| S14 public diagnostics | FIXED | Minimal public health, authorized detailed access; development mode still deliberately permissive. |

The earlier S08 “FIXED” statement applies only to error transport. The complete finding is not closed. Concrete retained chain: data.py:_record_worker_start_failure passes str(error) to _upsert_failed_evidence_record; upload_data persists internal_error in errors and data_conditions. evidence.py:get_evidence_run/get_latest_evidence/export_evidence_run return or export scoped stored records, including those failed records. Authentication and workspace scope limit access but do not sanitize internal exception text for an authorized customer. This is CONFIRMED_INFORMATION_EXPOSURE, MEDIUM. No live secret disclosure is asserted.

Changing failed evidence contents was excluded to preserve evidence representations. A separately reviewed distinction between raw evidence and redacted customer presentation/access is needed; the frozen post-test candidate was not changed after the one gate. This is an APPLICATION limitation, not something ingress TLS can solve. Accordingly the decision is SECURITY_CLOSEOUT_INCOMPLETE despite the passing tests and gate. No claim that all externally accessible failure artifacts are sanitized.

## Diagnostic route inventory and consumers

| Routes | Final access | Consumer / evidence |
|---|---|---|
| /, /health, /api/health, /api/ready | PUBLIC_SAFE | healthApi.js uses status only; root links and service metadata, minimal health/status responses; 200/503 retained. |
| /api/ready?verbose=true | ADMIN_ONLY in production/staging | health.py:_readiness_access; Help/diagnostic view may receive 401/403 for non-admin users. |
| /api/startup-status, /api/routes/debug | ADMIN_ONLY | main.py dependencies require_admin_role, unchanged. |
| /api/observability/summary, /metrics, /performance, /evp-governance (same observability prefix) | ADMIN_ONLY | observability.py router dependencies; metrics are not anonymous Prometheus endpoints. |
| /api/audit/* | ADMIN_ONLY | audit.py router dependencies, unchanged. |
| /api/intelligence/engine-identity, /api/intelligence/runner-status | ADMIN_ONLY | facility.py; engine_identity.py returns runner/core filesystem locations; now restricted. |
| /api/domain/mode | AUTHENTICATED | app_info.py; domain_mode.py:_score_domain includes source column strings in evidence. Mode/profile analytical content unchanged. |
| /api/intelligence/status; upload status/stream/latest | AUTHENTICATED | Product clients; established API/workspace boundary retained. |
| /api/live-analysis/health, /api/telemetry/ingestion-health | INTERNAL_ONLY local compatibility | require_legacy_global_telemetry_access returns 410 outside development/test; not activated. |
| /api/connectors/* | INTERNAL_ONLY local compatibility plus ADMIN_ONLY | require_legacy_connector_compatibility and require_admin_role; production 410 preserved. |
| /api/app, /docs, /redoc, /openapi.json | PUBLIC_SAFE | Product/interface metadata; no detailed runtime readiness or customer telemetry. |

Private diagnostic information may remain visible to authorized administrators. Development/test authorization relaxation, deployment selection, ingress and logs remain explicit responsibilities. No general route/tenant re-audit was performed.

Residual source locations: `backend/app/routers/data.py:337` (worker failure recording), `backend/app/routers/data.py:1634` and `:1645` (stored raw exception fields), `backend/app/routers/evidence.py:31`, `:60`, `:72` (authenticated raw retrieval/latest/export). These files are frozen by raw/GATE_PREDECLARATION.json; no post-gate production remediation was attempted.
