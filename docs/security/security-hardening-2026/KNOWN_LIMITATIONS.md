# Known limitations and follow-up

This campaign is not a penetration test, compliance attestation or deployment approval. Six boundary findings were fixed; outstanding risks remain.

Priority application follow-up: separate session management IDs from bearer credentials, hash stored tokens and stop returning authenticators (S07); sanitize technical upload errors at a defined transport boundary without changing canonical evidence (S08); explicitly separate spreadsheet-safe export from raw evidence CSV (S13). Public health/readiness diagnostics need ingress restriction or a distinct authenticated representation (S14). No architecture/identity migration was attempted.

Deployment responsibilities: TLS at ingress; verify-full database certificates; correct APP_ENV (development/test intentionally relax auth); least-privilege service role/workspace allowlists; narrow CORS origins with controlled DNS; trusted proxy allowlist (not arbitrary forwarding headers); private DB/object stores; customer/tenant network and volume isolation; storage encryption/key management; backups/recovery; log/browser-data retention; distributed rate/connection/concurrency limits; request timeouts, temp-space quotas and container memory/CPU limits. Configure non-root runtime volumes with restrictive permissions and no hostile local writers. Read-only root filesystem, seccomp/capabilities and production host posture were not live-verified.

Application SHA-256 links detect disagreement within the trusted storage boundary; they do not authenticate artifacts against an administrator replacing both content and hashes. External immutable storage/signing would require deployment-specific design and key authority. MFA/SSO, centralized session policy and immutable audit retention are not established by this review.

Log redaction targets credential patterns; arbitrary telemetry/PII in filenames/exceptions is not universally removed. Session JSON and raw diagnostic upload messages remain known issues. Browser localStorage can retain scoped analytical history and notes; shared workstation policy matters.

Dependency results are limited to npm production lockfile advisories; no Python/OS/container CVE scanner or external live security test ran. Backend transitive dependencies are not fully locked, backend Dockerfile uses a mutable base tag and some deployment workflows use long-lived secret references. Do not infer no dependency vulnerabilities from the frontend result.

The 10K gate exercises the existing deterministic workload and core production upload processing, not HTTP admission under production infrastructure. HTTP abuse tests cover the added boundary. Exact-tie cases are covered by targeted regressions. No 500K/1M/LBNL/full suite or scale benchmark.


## Application closeout disposition (2026-09-24)

The original limitations above remain historical evidence. Current detail is in ../security-closeout-2026/.

- S07 JSON bearer disclosure: FIXED; management handle replaces authenticating session ID in JSON. Token hashing at rest: DEFERRED_WITH_REASON, separate auth-store migration.
- S08: ordinary upload error/status/SSE/latest HTTP presentation FIXED, but overall finding DEFERRED_WITH_REASON. Failed evidence records still contain original exception text in errors/data_conditions and scoped evidence retrieval/export can return it. Preserving raw evidence does not constitute sanitization; this APPLICATION limitation prevents complete closeout.
- S13 CSV export: FIXED at presentation only; source/canonical evidence unchanged.
- S14 public diagnostics: FIXED by minimization/admin or authenticated access. Deployment/test modes still require correct deployment selection.
- Existing S09/S11/S12 deployment-dependent responsibilities and S10 dependency reproducibility gap remain; not rescanned or silently resolved. TLS, isolation, volume controls, immutable retention and distributed resource controls remain DEPLOYMENT_RESPONSIBILITY. Broader logging, MFA/SSO and token-storage migration remain deferred application/architecture items as previously described.

Closeout result: SECURITY_CLOSEOUT_INCOMPLETE. Changes themselves passed 57 backend security, 17 frontend unit and 14 analytical cases, plus one exact 10K repeat gate. This does not erase the residual evidence-response exposure.


## Final S08 disposition — FIXED (2026-09-24)

The previous S08 deferral/incomplete closeout above is superseded under the user's explicit raw-forensic/customer-presentation contract. Raw failed evidence remains unchanged; customer list/detail/latest/update responses, downloads, CSV/Markdown/JSON/PDF packages and interpretation input use one safe projection. Dedicated forensic access is authenticated-admin-only in every environment, scoped and audited, with no-store responses. No historical sanitization rewrite or analytical identity change.

Final closeout: SECURITY_CLOSEOUT_COMPLETE_WITH_DEPLOYMENT_LIMITATIONS. 27 focused security cases, 15 analytical cases and one final S08 10K repeat gate passed; both outputs exactly match both current certified outputs. Prior evidence remains retained. Details: ../security-closeout-2026/DECISION.md and raw/s08-final/.

Deployment protections for administrator access, raw forensic storage/retention, TLS, private storage, permissions, proxy/CORS, audit/log handling and resource limits remain. Previously classified broader items were not reopened by this narrow S08 task. No claim of regulatory certification or universal absence of vulnerabilities.
