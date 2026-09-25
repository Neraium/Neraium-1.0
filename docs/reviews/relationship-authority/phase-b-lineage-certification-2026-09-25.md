# Phase B relationship-lineage certification

- Repository: `/home/ubuntu/Neraium-1.0`
- Branch: `fix/deterministic-governed-output`
- Baseline and inspected HEAD: `0d28d049aad3f38fe1254e2a8105b344fbfd049b`
- Result: PASS for Phase B relationship lineage only.
- Analytical math changed: NO.

## Review

Issuance requires the canonical endpoint identity, authenticated Phase 4 scope,
current server-bound system identity, asset identity, and Phase A observation
lineage. The endpoint mapping IDs and revisions are compared with observations
that are themselves checked against current system, asset, and mapping authority.
Missing or mismatched authority suppresses lineage.

Lineage is a deterministic descriptor separate from the result-local source,
evidence, and assessment-binding references. It binds scope, canonical endpoint
IDs, assessment basis, mode identity, semantics, and semantic version. Fallback
has its own basis and is continuation-ineligible. No presentation, runtime,
retry, rank, group, primary, name, or persistent-column identity is used.

When an assertion carries a lineage reference, `resolve()` requires the matching
registry descriptor and verifies its digest and exact authorized evidence scope,
endpoints, basis, semantic version, and mode identity. Assertions without a
lineage reference retain the existing result-local behavior; that behavior does
not validate or grant lineage authority. Existing ownership references and
assessment binding remain authoritative and unchanged.

No temporal state, storage, continuation, Phase C, or analytical calculation
changes were found in the Phase B diff.

## Verification

Command:

```text
.venv/bin/python -m pytest -q tests/test_relationship_lineage.py tests/test_relationship_evidence_binding.py tests/test_telemetry_lineage.py tests/test_phase4_authenticated_scope.py tests/test_phase4_upload_system_identity.py
```

Result: 68 passed, 2 warnings.

`git diff --check`: clean.

## Commit allowlist

- `backend/app/engine/sii_engine.py`
- `backend/app/services/relationship_evidence_binding.py`
- `backend/app/services/relationship_lineage.py`
- `backend/app/services/telemetry_analysis_window.py`
- `tests/test_relationship_evidence_binding.py`
- `tests/test_relationship_lineage.py`
- `docs/reviews/relationship-authority/phase-b-lineage-certification-2026-09-25.md`

Recommended commit subject: `fix: certify Phase B relationship lineage authority`
