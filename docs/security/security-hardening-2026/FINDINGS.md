# Findings and scope classifications (pre-implementation)

Severity is impact in an exposed deployment, not a claim of exploitation. Source paths refer to baseline hashes; final line numbers may shift.

| ID | Severity | Classification | Concrete evidence and attack condition | Disposition |
|---|---|---|---|---|
| S01 | HIGH | CONFIRMED | main.py:add_request_context calls request.body() before checking actual length for unknown-length/telemetry bodies; trusts small declared lengths elsewhere. Multipart routes excluded, endpoint file loops run after FastAPI parsing. Client can consume memory/spool before rejection. | Streaming boundary limit, preserve accepted bytes and endpoint file caps. |
| S02 | HIGH | CONFIRMED | core/security.py:_strict_auth_mode excludes supported APP_ENV=staging; require_api_access then accepts client identity/role headers and minimum-role guard returns. Staging exposed to untrusted clients bypasses authentication. | Require authentication and roles in staging. |
| S03 | MEDIUM | CONFIRMED | auth.py sets Lax cookies; unsafe cookie requests have no Origin/Referer enforcement. Same-site hostile origins can submit forms to cookie-authenticated endpoints (e.g. logout/upload); CORS does not stop request effects. | Verify unsafe browser origins; fail closed for cookie writes without provenance in shared environments. |
| S04 | LOW | CONFIRMED | security.py:_client_ip and data.py:_request_client_ip trust raw X-Forwarded-For, unlike auth.py. Spoofs audit IP and fallback rate bucket (authenticated upload buckets normally use subject). | Use ASGI peer as normalized by trusted server proxy configuration. |
| S05 | MEDIUM | CONFIRMED | main.py adds security headers only after successful call_next; early header/size responses bypass them. API/session responses lack server no-store. | Boundary response headers and private API no-store, including handled errors. |
| S06 | MEDIUM | CONFIRMED | config.py:validate_environment_completeness validates direct auth DB URL syntax but not production sslmode, unlike runtime/telemetry DB and managed auth secret mode. | Reject production direct auth database URLs without TLS requirement. |
| S07 | MEDIUM | CONFIRMED | auth_store.py:sanitize_session_record returns the authenticating session_id; auth/me and login expose it to JavaScript, admin session listing exposes other active tokens. Stored sessions are plaintext bearer secrets. | Deferred: separate public management handles from authenticators and migrate session storage/API; boundary no-store reduces cache exposure but does not fix this. |
| S08 | MEDIUM | CONFIRMED | data.py large-upload errors pass str(exc) to build_upload_error_payload; upload_errors.py returns it as technicalMessage. May disclose internal paths/provider details. | Deferred: ownership-aware error transport projection needed; do not rewrite stored evidence/error records or canonical bytes. |
| S09 | MEDIUM | POTENTIAL | rate_limiter.py is per-process memory; multipart configured cap defaults to 250 MiB and large upload 512 MiB; no global concurrency/body-time budget at ASGI boundary. | Deployment ingress quotas/timeouts and shared rate protection required. |
| S10 | LOW | CONFIRMED | backend/Dockerfile base tag mutable; Python direct pins but transitive dependencies not fully locked; root Dockerfile digest pinned. | Report supply-chain reproducibility gap; no speculative dependency upgrades. |
| S11 | MEDIUM | POTENTIAL | core/path_safety.py containment resolves symlinks before later opens; local runtime files use host umask. A hostile co-tenant with volume write access could race paths or alter data/hash together. | Deployment volume isolation/permissions and external integrity anchors; no evidence re-encoding. |
| S12 | LOW | POTENTIAL | logging_config redacts credential patterns but arbitrary exception content/filenames may contain telemetry/PII; frontend localStorage contains analysis history/notes. | Restrict log/browser access and retention; do not claim general content redaction. |

No confirmed CRITICAL finding established. This is a bounded source review, not proof of absence.

## Additional inspection and disposition

- **S13 — MEDIUM / CONFIRMED:** evidence_store.py:build_evidence_export_csv/csv_escape quotes CSV delimiters but does not neutralize spreadsheet formula prefixes. A source name beginning `=` reaches a CSV cell. Exploitation requires opening the exported CSV in a formula-capable spreadsheet. Deferred to a separately labeled spreadsheet-safe export representation; do not silently rewrite source/canonical evidence values.
- **S14 — LOW / CONFIRMED:** routers/health.py:read_health/read_ready expose operational diagnostics publicly, including runtime path/configuration; verbose readiness consults latest upload session. Restrict operational endpoints at ingress or design an authenticated diagnostic representation. No claim of observed cross-tenant telemetry payload disclosure.

S01–S06 are implemented and covered by focused tests. S07/S08/S13 remain confirmed application gaps; S09/S11/S12 retain their stated deployment-dependent conditions. S10 remains a reproducibility gap. No findings are silently converted into clean bills of health.

## Threat-class coverage

| Threat class | Classification | Evidence / conclusion |
|---|---|---|
| Unauthenticated access | CONFIRMED then hardened | S02 staging; production credential rejection existing. Operational diagnostics remain S14. |
| Broken authorization, cross-tenant access, IDOR | ALREADY_CONTROLLED on inspected paths | Server workspace membership and scoped repository lookups; real multi-user workspace test and forged-scope tests pass. Not an exhaustive endpoint penetration test. |
| Path traversal, malicious filenames | ALREADY_CONTROLLED | core/path_safety.py; connector identifier allowlist; selected symlink/encoded traversal tests. Local hostile-writer race remains S11. |
| Oversized/resource-exhaustion input | CONFIRMED then hardened | S01 actual stream budgets; global concurrency/slow clients remain S09. |
| Malformed JSON/CSV and unsupported type | ALREADY_CONTROLLED, bounded scope | FastAPI JSON validation; suffix/contract validation, parser errors; new stream cap before parsers. MIME labels alone are not trusted source validation. No broad MIME policy imposed. |
| Formula/CSV injection | CONFIRMED | S13; not fixed by ordinary CSV quoting. |
| Command injection | NOT_APPLICABLE to inspected ingestion routes | No client-controlled shell/eval/exec call found in app scan; engine_identity runs a fixed git argument vector. This is not a whole-repository proof. |
| SQL injection | ALREADY_CONTROLLED on inspected repositories | Bound parameters; server-owned query templates; no browser-supplied SQL/DSN accepted by current historian boundary. |
| Unsafe deserialization | NOT_APPLICABLE to inspected app input paths | No pickle/yaml.load/eval input path found; JSON/models and validated bounded canonical zlib decode. |
| SSRF | ALREADY_CONTROLLED for current HTTPS telemetry | Egress policy, public DNS answers, pinning, redirects off; notification webhook is administrator/deployment configuration, still needs outbound firewall. |
| XSS | ALREADY_CONTROLLED at inspected rendering sinks | React escaped rendering, no raw HTML/eval sink found; CSP backend header is not proof frontend hosting sends CSP. Session JSON exposure remains S07. |
| CSRF | CONFIRMED then hardened | S03 origin validation for ambient cookie writes; login hostile Origin rejection. Allowlisted origins and regex must themselves be trustworthy. |
| CORS | ALREADY_CONTROLLED with configuration limitation | Explicit allowlist/regex and production wildcard ban; broad or compromised allowed origins remain deployment responsibility. |
| Secrets exposure/session tokens | CONFIRMED | S07; secret store boundary/redaction exists, but bearer sessions are returned/stored as described. |
| Sensitive logs/exception leakage | CONFIRMED / POTENTIAL | S08 raw technicalMessage; S12 arbitrary telemetry/PII outside credential regex. Generic unhandled response tested safe. |
| Temporary files and permissions | ALREADY_CONTROLLED / POTENTIAL | NamedTemporaryFile/server naming and multipart error cleanup tested; volume/umask isolation remains S11. |
| Resource controls/rate limiting | CONFIRMED then hardened / POTENTIAL | S01/S04 implemented; no distributed rate limiter or ingress slow-client guarantee (S09). |
| Dependency exposure | INFORMATIONAL / ALREADY_CONTROLLED in narrow scan | npm production lockfile audit reports zero advisories on audit date; Python/transitive/OS image CVE scan not performed. S10 reproducibility gap remains. |
| Container privileges/debug/config | ALREADY_CONTROLLED with limitations | Non-root, image exclusions, FastAPI debug default false, admin debug route; no deployed capability/seccomp/readonly-root evidence verified. Development auth remains permissive by design. |
| Auth/session weaknesses | CONFIRMED then partly hardened | S02/S03/S06 fixed; S07 retained, no MFA/SSO claim; service token defaults to admin unless configured. |
| Insufficient audit logging | POTENTIAL | Existing auth/admin/export events and correlation; audit store is not independently immutable or cryptographically signed; external retention needed. |
| Artifact tampering/provenance bypass | ALREADY_CONTROLLED within trust boundary | Exact digest/source/version validation and tamper rejection test; privileged attacker changing data and expected hash requires external integrity anchor (S11). |
| Replay abuse and tenant/source identity confusion | ALREADY_CONTROLLED on tested contract | Scoped replay reads stored artifacts; source/runtime identity and historical replay tests; no current semantics re-encoding. |

Frontend dependency evidence: raw/frontend-dependency-audit.json. No assertion of no vulnerabilities outside that scan scope.
