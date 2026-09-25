# Phase A Endpoint Identity Certification

**Decision:** `PHASE_A_ENDPOINT_IDENTITY_CERTIFIED_FOR_COMMIT`

**Repository baseline:** `a75b7c1ef572b3c926e8fd00db3691d69e84e112`

## Findings

- Endpoint IDs are projected from validated `ObservationLineage.canonical_signal_id` values. Mapping provenance comes from the same records' mapping IDs/revisions and authority digest. The projection does not consult raw names, ranking, grouping, primary selection, persistent columns, or presentation.
- Missing endpoint coverage or mismatched system, asset, authority digest, canonical signal, mapping ID, or revision suppresses the endpoint metadata. The projection does not mutate analysis rows. Focused tests also compare analytical/relationship outputs with endpoint metadata omitted.
- `evaluate_sii` attaches the supplied endpoint structure only after analytical consumers and relationship registry finalization. It does not modify relationship edges, evidence ownership, or resource binding.
- No temporal continuation was added.
- Comparison tests now use `a75b7c1e`. AST normalization removes only the Phase A argument and metadata attachment, leaving Phase A changes visible to the comparison.
- `ANALYTICAL_MATH_CHANGED: NO`.

## Verification

- `.venv/bin/python -m pytest -q tests/test_relationship_evidence_binding.py tests/test_telemetry_analysis_handoff.py --tb=short`: **49 passed**, 2 warnings.
- `git diff --check`: passed.

## Exact commit allowlist

- `backend/app/engine/sii_engine.py`
- `backend/app/services/telemetry_analysis_window.py`
- `tests/test_relationship_evidence_binding.py`
- `tests/test_telemetry_analysis_handoff.py`
- `docs/reviews/relationship-authority/phase-a-endpoint-identity-certification.md`

**Suggested commit subject:** `feat: add governed relationship endpoint identity`
