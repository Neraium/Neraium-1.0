# Neraium Audit Sweep - May 21, 2026

This audit run covered all 12 requested categories with direct command evidence where tooling was available.

## 1) Threat-Model Audit
Status: PASS (manual review)
Evidence:
- Reviewed exposed API surface (`backend/app/main.py`, `backend/app/routers/*.py`).
- Verified protected routers use `Depends(require_api_access)` for operational endpoints.

## 2) Access-Control Audit
Status: PASS
Evidence:
- `python -m pytest tests/test_health.py tests/test_frontend_upload_auth.py tests/test_connectors.py -q`
- Result: 41 passed.

## 3) Data-Retention Audit
Status: PASS (baseline)
Evidence:
- Verified runtime/audit persistence paths and queue runtime DB checks via existing route and service tests.
- `python -m pytest tests/test_data_upload.py::test_upload_status_returns_complete_job_summary_and_writes_state -q`

## 4) PII/Logging Audit
Status: PASS
Evidence:
- Existing tests confirm no secret leakage in logs:
  `python -m pytest tests/test_health.py -q`
- Code scan covered token/authorization handling and masking paths in connectors/security middleware.

## 5) Concurrency Audit
Status: PASS
Evidence:
- `python -m pytest tests/test_upload_queue_hygiene.py tests/test_data_connections_polling.py -q`
- Result: queue and polling concurrency paths passed.

## 6) Failure-Injection Audit
Status: PASS (tested scenarios)
Evidence:
- Route/health/failure-handling contracts exercised:
  `python -m pytest tests/test_backend_route_smoke.py tests/test_health.py -q`
- Upload flow still returns contract-complete terminal states in tested failure-adjacent paths.

## 7) Contract Drift Audit
Status: PASS
Evidence:
- OpenAPI generated from app runtime:
  - openapi: `3.1.0`
  - path count: `94`
- Contract enforcement tests passed:
  `python -m pytest tests/test_sii_contract_enforcement.py tests/test_operator_workflow_contract.py -q`

## 8) Determinism Audit
Status: PASS (current deterministic code paths)
Evidence:
- `python -m pytest tests/test_engine.py tests/test_structural_cognition.py tests/test_telemetry_integrity_simulations.py -q`
- Result: 21 passed.

## 9) Model-Quality Audit (system types)
Status: PASS (available suites), PARTIAL (coverage expansion opportunity)
Evidence:
- Domain and aquatic mappings validated:
  `python -m pytest tests/test_domain_mode.py tests/test_aquatic_domain.py -q`
- Note: HVAC/electrical/pool-spa benchmark packs are not yet represented as dedicated quantitative precision/recall datasets in this repo.

## 10) Supply-Chain Audit
Status: PASS
Evidence:
- Frontend dependencies:
  `npm audit --omit=dev` -> 0 vulnerabilities.
- Backend dependencies:
  `python -m pip_audit -r backend/requirements.txt` -> no known vulnerabilities.
- License summary (frontend production deps) showed only first-party package as `UNLICENSED` (private app package), third-party deps MIT.

## 11) Infra Posture Audit
Status: BLOCKED (local tool missing)
Evidence:
- Terraform CLI not installed on this machine (`terraform` command not found).
- Could not execute `terraform fmt/validate` locally in this run.

## 12) Backup/Restore Drill Audit
Status: PASS (file-level runtime restore drill)
Evidence:
- Performed backup-mutate-restore cycle for `backend/runtime/latest_sii_state.json`.
- Result: `backup_restore:PASS`.
- Backup artifact created at `output/audit-backup-restore/latest_sii_state.backup.json`.

## Additional Production Performance/Health Smoke
Status: PASS
Evidence:
- `node scripts/smoke-production.js`
- API health/ready/metrics/runner checks passed.
- Upload job reached `COMPLETE` and advanced visible runtime state.

## Follow-Up Items
1. Install Terraform in CI/local runner and add `terraform fmt -check` + `terraform validate` gate.
2. Add dedicated HVAC/electrical/pool-spa benchmark packs with measurable FP/FN metrics.
3. Persist and diff OpenAPI snapshot in CI for explicit contract-drift alerts.
