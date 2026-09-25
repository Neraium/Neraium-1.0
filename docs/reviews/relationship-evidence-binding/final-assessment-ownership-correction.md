# Final-assessment ownership correction

Decision: EXACT_BINDING_FINAL_ASSESSMENT_CORRECTED_READY_FOR_CERTIFICATION

## Baseline and preserved history

Branch: fix/deterministic-governed-output.
HEAD: f01d5475967eef8b2f7dd0d05a7b631f79586e25. Nothing staged.
The initial candidate, first failed certification, source-ownership correction,
and blocked final certification remain unchanged. This is a candidate correction,
not independent certification. No commit, push, migration or cleanup occurred.

## Pre-edit reproduction

Before production edits, generated actual supplied-reference engine results from
`test_sii_supplied_reference.contract(16)`: one successful, one with
`analyze_relationship_graph` raising a controlled synthetic exception. Corresponding
canonical assertions had identical source references and different evidence references.
Combined their intact records with `registry_record`, retaining the accepted scope.
Both originals resolved. The fallback original failed require_temporal=True.
Replacing ONLY its evidence reference with the successful assessment's reference
was accepted both normally and with require_temporal=True. Registry equality was
checked before/after; no record or digest was changed.

## Root cause and invariant

A source calculation can own several final assessments. Source ownership alone
cannot establish which assessment was assigned to a particular assertion.

Source invariant remains: assertion source ref equals the validated record source ID.
New final-assessment invariant: the assertion retains the exact producer-assigned
(source ref, evidence ref, version, scope) tuple through a deterministic digest.
Changing one reference without its original assignment binding fails resolution.

## Correction and identity

Added `relationship_assessment_binding`, using existing canonical_json_bytes and
SHA-256 through digest(), domain `relationship-assessment-binding.v1`.
Inputs are the existing evidence contract version, source_ref, evidence_ref, scope.
No new evidence identity, observations, analytical values or runtime fields are added.

Finalization clears any stale binding, validates the candidate source, assigns a
unique final evidence reference, and only then emits the binding. Ambiguous
assessments have neither an evidence reference nor an assignment binding.
Resolver verifies the carried binding against the current tuple in addition to
all existing record/source digest, version, scope, method, basis and temporal checks.
It never repairs or writes the assertion and never searches for alternative evidence.

This is an unkeyed integrity binding, not a signature or authentication mechanism.
It detects the required partial-field substitution. It does not authenticate a
caller that can replace/recompute the entire tuple. Authorized canonical-result
access remains the trust boundary; no new lookup endpoint exists.

## Propagation and compatibility

Mechanical optional-field copies in build_relationships, relationship_contribution,
and build_analysis_result retain the producer binding. Tests verify producer,
explanation, contributions, canonical relationships, JSON storage, upload transport,
and bounded connector projection. Actual connector generation/retry also resolves
and retains the same tuple. Full source evidence is not added to projected assertions;
full registry is not added to bounded relationship disclosure. UI is unchanged.

Historical absence stays absent. No read-time finalization, inference, rerun,
rewriting or migration. Missing assignment binding means unavailable authority,
even when full source payload and both references exist. Stored classifications
and consequences retain existing behavior.

## Attack and invariant coverage

- Actual success/failure-fallback borrowing rejected in both directions, normally
  and with temporal requirement; originals still resolve and registry is unchanged.
- Correct fallback retains failure-fallback basis and has unavailable temporal proof.
- Controlled reducer-produced evidence with different final reference, context,
  units or bounded history cannot lend its assessment to a same-source assertion.
- Existing different-relationship attacks and mode-conditioned lineage tests pass.
- Missing, malformed, tampered or another assessment's valid assignment binding fails.
- Full source payload does not substitute for the required compact assignment binding.
- Existing wrong-scope, conflicting registry, digest tampering, source-owner mismatch,
  reference mismatch and restricted-field canaries pass.
- Retry, JSON replay, mapping-order variation, ranking, primary and unrelated group
  changes preserve the assignment tuple. No runtime metadata enters the new hash.

## Analytical freeze

ANALYTICAL_MATH_CHANGED: NO

Four isolated authoritative-HEAD comparisons pass: supplied reference, global
fallback, mode-conditioned and graph-failure fallback. Existing semantic/product
comparison uses only the explicit additive binding metadata exclusion list, now
including relationship_assessment_binding; no pre-existing analytical fields were
added to that exclusion list. Existing AST comparisons pass for the three modified
calculation/assembly functions after removing the explicit metadata additions.

Byte comparison with HEAD confirmed unchanged relationship_change.py,
relationship_recurrence.py, sii/relationship_graph.py, finding_classification.py,
condition_corroboration.py, measurable_consequence.py, runtime_governance.py and
telemetry_analysis_window.py. No downstream authority consumer uses this binding.
No temporal-state handoff or history reconstruction was implemented.

## Files changed by this correction

Production:
- backend/app/services/relationship_evidence_binding.py
- backend/app/services/analysis_explanations.py
- backend/app/services/analysis_result_contract.py

Tests:
- tests/test_relationship_assessment_binding.py (new; 12 cases)
- tests/test_relationship_binding_ownership.py (projection binding assertions)
- tests/test_relationship_evidence_binding.py (retry/connector tuple and ambiguity checks)
- tests/relationship_evidence_binding_cases.py (new metadata normalization key only)

Review: this artifact only. Earlier candidate files remain part of the candidate;
this correction does not otherwise change them.

## Validation results

Commands use PYTHONDONTWRITEBYTECODE=1, PYTHONPATH=backend:tests and .venv/bin/python.

1. pytest -q tests/test_relationship_assessment_binding.py
   tests/test_relationship_binding_ownership.py tests/test_relationship_evidence_binding.py
   — 65 passed (37.64s).
2. pytest -q tests/test_presentation_phase1.py tests/test_presentation_phase1_context.py
   tests/test_presentation_phase1_graph_fallback.py tests/test_telemetry_analysis_handoff.py
   tests/test_telemetry_result_projection.py tests/test_measurable_consequence.py
   tests/test_sii_evidence_transport.py — 65 passed (32.30s).
3. After strengthening final checks, reran the 12 new cases and existing retry,
   real connector retry, and conflicting/ambiguous assessment tests — 15 passed (6.14s).

130 distinct focused tests passed; 15 targeted checks rerun after final test edits.
This includes 21 measurable-consequence tests. No broad campaign or benchmark ran.

Complete tracked production diff and new binding module inspected. Changes remain
additive identity/projection metadata only. No dependency, threshold, presentation,
classification, condition, consequence, governance or control changes. No new raw
observations, errors, credentials, paths or runtime identity are projected by the
correction. git diff --check passed. No remaining blocker found in this correction.
Independent adversarial certification is the next action.
