# Final independent certification — relationship authority

Baseline: `774892e4cfa237195bee51714ae789c061086380`

Decision: RELATIONSHIP_AUTHORITY_CERTIFIED_FOR_COMMIT

ANALYTICAL_MATH_CHANGED: NO

## Independent review

Read AGENTS.md, the candidate report, the canonical ownership correction, the
verification record, and inspected the current tracked diff. Confirmed branch and
HEAD match the requested baseline. No staged changes were present. The final
correction report and prior candidate artifacts were read as claims to verify,
not certification evidence.

The prospective adapter resolves the assertion through the exact
relationship_source_ref, relationship_evidence_ref and
relationship_assessment_binding tuple in the result registry and scope. It then
requires the record's own eligible assessment and temporal persistence result.
The canonical result builder now reconstructs prospective scoped qualification
from the producer relationship assertions and registry, ignoring cached scoped
persistence/classification. No pair, group, rank, primary, signal or
persistent_columns association supplies authority. Group conditions and insights
carry unqualified group persistence; individual relationship findings retain
their own assessment. Recurrence remains outside the persistence adapter.

Focused review found no change to relationship or graph calculations, persistence
or recurrence reducers, thresholds, eligibility, context semantics, classification
mathematics, governance, telemetry admission, control, consequence calculations,
presentation templates, or temporal-state continuation. Upload and connector
paths carry scoped findings without requalification on stored reads. Exact resource
ownership continues to gate quantified consequences.

## Cached authority attack

The regression creates persistent A and nonpersistent B, builds their cached
explanation, copies A's persistence, classification and confidence onto B while
retaining B's ownership tuple, then builds the canonical result. Canonical output
reconstructs both from the producer entries and current registry: B remains
nonpersistent and A remains persistent. The reverse transfer is also rejected.
Missing cached scoped findings are rebuilt. Tampered cached binding/persistence,
missing producer registry, mismatched scope, tampered producer binding and missing
producer assertions cannot establish authority. Inputs remain unchanged.

## 17-case matrix

Independently reran `tests/test_relationship_authority.py`; all matrix behaviors
pass: persistent A alone; stable, transient, alternating, sparse/ineligible,
persistent, and mixed group members; recurrence and abrupt promotion; context,
quality and health ceilings; valid global and failed graph fallback; grouping and
ranking/primary invariance; condition overlap; exact consequence owner and
mismatch; and identical signal persistence with different relationship outcomes.

## Ownership, compatibility and transport

Exact resource binding and cross-owner attacks passed. The committed consequence
adapter equality and gates passed, including the existing approximately 12,840
unit numerical fixture. Historical explanation behavior without the version
marker remains equal to the committed implementation, with no mutation. A
dedicated check fails if historical construction or stored canonical retrieval
calls prospective requalification. Upload serialization, connector projection,
real engine handoff and retry digest checks passed.

The condition-intelligence ordering assertion was independently checked against
the baseline by loading committed `condition_corroboration.py` and running the
same four relationships. The committed output fails the alphabetical-order
assertion, and the full baseline and candidate outputs are equal. This is a
pre-existing assertion failure, not a candidate regression.

## Verification

Focused command:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend:tests .venv/bin/python -m pytest -q tests/test_relationship_authority.py tests/test_analysis_result_contract.py tests/test_resource_relationship_binding.py tests/test_relationship_evidence_binding.py::test_real_engine_upload_storage_and_connector_projection tests/test_relationship_evidence_binding.py::test_real_connector_generation_retains_registry_and_retries tests/test_relationship_evidence_binding.py::test_real_upload_compatibility_path_preserves_binding tests/test_relationship_evidence_binding.py::test_existing_calculation_ast_unchanged_except_binding_metadata tests/test_sii_evidence_transport.py
```

Result: **91 passed**, two warnings, 82.01 seconds. `git diff --check` passed.
No full regression, LBNL, wastewater, scale, large-volume or performance campaign
ran.

## Exact commit allowlist

PRODUCTION

- `backend/app/engine/sii_engine.py`
- `backend/app/services/relationship_authority.py`
- `backend/app/services/analysis_explanations.py`
- `backend/app/services/analysis_result_contract.py`
- `backend/app/services/condition_corroboration.py`
- `backend/app/services/measurable_consequence.py`
- `backend/app/services/upload_jobs.py`
- `backend/app/services/telemetry_result_projection.py`

TESTS

- `tests/test_relationship_authority.py`
- `tests/test_relationship_evidence_binding.py`

REVIEW EVIDENCE

- `docs/reviews/relationship-authority/authority-candidate.md`
- `docs/reviews/relationship-authority/authority-verification.json`
- `docs/reviews/relationship-authority/canonical-ownership-correction.md`
- `docs/reviews/relationship-authority/final-independent-certification.md`

All other retained untracked artifacts are excluded. No staging, commit, push,
merge, tag or deployment was performed.

Recommended commit subject: `fix: bind relationship persistence to exact evidence`

Next action: commit only this allowlist when explicitly authorized.
