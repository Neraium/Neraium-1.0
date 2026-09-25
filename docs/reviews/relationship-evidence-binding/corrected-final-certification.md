# Corrected exact-binding final independent certification

Decision: EXACT_BINDING_CERTIFIED_FOR_COMMIT

## Baseline and scope

Branch fix/deterministic-governed-output; HEAD, origin tracking ref and live remote:
f01d5475967eef8b2f7dd0d05a7b631f79586e25. Index empty. Candidate remains uncommitted.
This review changed no production or tests. This report is the sole new review artifact.
Previous failed certifications and correction records remain intact.

Candidate: 6 production + 7 test + 6 review paths including this report = 19 paths.
Before this report, 9,421 untracked paths included 10 candidate paths; 9,411 unrelated
retained artifacts are excluded, including the earlier relationship-authority blocker.

## Ownership and adversarial checks

Inspected producer source creation, mode recalculation, finalization, resolver,
and all three mechanical projection additions. The assignment binding is produced
only after unique final evidence selection. Source, final evidence, contract version,
and accepted scope participate; no ranking/grouping/runtime field participates.
Missing metadata is not repaired by projection or resolution. Ambiguity clears
both evidence reference and assessment binding.

Independently generated real supplied-reference canonical assertions and actual
forced graph-failure results. Combined intact records using registry_record for the
cross-assessment diagnostic (not a claim of a naturally mixed production registry).
Ran 35 independent substitution/malformed-field checks. Both cross-relationship
and same-source success/fallback attacks fail in both directions, with and without
require_temporal. Untampered originals resolve and registry remains unchanged.
Correct fallback observation evidence resolves; requiring temporal evidence rejects it.
No digest was recomputed to legitimize any attack.

Also executed actual mode producer/reducer/finalizer and relationship projection
with global and recalculated mode candidates. Both originals resolve to their own
records; both reference-borrowing directions fail, including temporal-required calls.
Existing tests cover changed reference/context/units/history, wrong scope, invalid
source, malformed/missing/tampered or another valid assignment binding, conflicting
registry records, ambiguous finalization, and no historical authority reconstruction.

## Determinism and propagation

Producer -> engine -> explanation/contribution -> canonical relationship/result ->
JSON storage/upload -> connector canonical and bounded product projection retains
all three opaque fields by copying. Canonical registry remains independent of
bounded disclosure; bounded connector result does not acquire the complete registry.
Tests cover real upload analysis, actual connector generation/retry and controlled
replay, projection absence, organizational mutations and historical reads.

Independent fresh processes with different Python hash seeds and worker/request/
retry environment values produced the same registry plus ownership-tuple digest:
a241515edda8936b98e98462820c1f8ab9d40931c9fd51d3e8b00d717f67bad0.
Source inspection confirms no wall-clock or process identity enters the binding.
Grouping, rank and primary mutation tests pass without changing ownership.

## Security and compatibility

Binding is an unkeyed integrity mechanism, not a signature or authorization token.
This certification covers independent component substitution; it does not claim
resistance to replacing and recomputing an entire tuple by an already trusted writer.
Existing authorized result access is required. No lookup endpoint or authorization
change exists; raw source observations are hashed, not copied into canonical assertions.
Safe field selection and restricted-field canaries pass. No source payload is added
to projected assertions by the owner/binding corrections. No migration, historical
rerun, rewrite or inference; absent historical binding means unavailable authority.

## Analytical freeze

ANALYTICAL_MATH_CHANGED: NO

Every tracked production hunk and the new binding module were inspected. Added
metadata is issued without modifying calculations; downstream classification,
conditions, consequence and governance do not consume the resolver. No temporal-state
handoff, presentation, dependency, threshold or control change was introduced.

Eight protected implementation files were compared byte-for-byte with HEAD:
relationship_change.py, relationship_recurrence.py, sii/relationship_graph.py,
finding_classification.py, condition_corroboration.py, measurable_consequence.py,
runtime_governance.py, telemetry_analysis_window.py. All identical.
Existing three calculation/assembly AST comparisons passed.

Four isolated authoritative-HEAD comparisons passed: supplied reference, global
fallback, mode-conditioned and graph-failure fallback. Additionally repeated all
four without product_evidence filtering, comparing full existing semantic_content
results. The only additional exclusions were exactly the six binding metadata keys:
relationship_source_evidence, relationship_source_ref, relationship_evidence_ref,
relationship_evidence_id, relationship_evidence_registry, relationship_assessment_binding.
The existing semantic encoder excludes declared runtime envelopes/aliases; no new
pre-existing analytical field was excluded. This is semantic analytical equality,
not a claim of identical wall-clock execution envelopes.

## Focused validation and hygiene

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend:tests .venv/bin/python -m pytest -q:
test_relationship_assessment_binding.py, test_relationship_binding_ownership.py,
test_relationship_evidence_binding.py, test_presentation_phase1.py,
test_presentation_phase1_context.py, test_presentation_phase1_graph_fallback.py,
test_measurable_consequence.py, test_telemetry_analysis_handoff.py,
test_telemetry_result_projection.py, test_sii_evidence_transport.py.

Result: 130 passed, six warnings, 68.58 seconds. Includes 21 consequence checks,
Presentation Phase 1 compatibility, analytical HEAD comparisons and ownership tests.
Additional independent diagnostics described above passed. No broad campaigns ran.
git diff --check passed. No credentials, customer telemetry, debug instrumentation,
unrelated refactor, dependency changes or generated outputs found in the allowlist.
No material defects found. No staging, commit, push, merge, tag or deployment.

Recommended commit subject:
feat(evidence): bind relationship assertions to exact producer assessments

Next action: user-authorized exact-allowlist commit workflow; certification alone
does not stage or commit. Downstream authority remains a separate phase.

## Exact commit allowlist and certified SHA-256 bytes

Hashes cover all candidate files before this report. This report is included in
the allowlist without a self-referential hash.

### PRODUCTION

- `backend/app/engine/sii/mode_conditioned_baseline.py` — `6ad1e8c5a9c2195cb99d3a818121fd9355b036c55cbc4389e92ecd966cca3f46`
- `backend/app/engine/sii_engine.py` — `254d2071be8a9569922d65e5d71108f9c96b450965671e11748160e4fd47deff`
- `backend/app/services/analysis_explanations.py` — `78a18f0d7a6dae3bcf3584bf4eead3765cf56728f57f719d2981921f6e95e11f`
- `backend/app/services/analysis_result_contract.py` — `138b886d2d570fd5c12ec38dd8fe231ecb5ee933a896858d6c14ea7b1b152a23`
- `backend/app/services/relationship_baselines.py` — `e6eedf756b771ca60eb4cc879d1c45d9bceb4b35c62f5ca8b6f22931220a54fe`
- `backend/app/services/relationship_evidence_binding.py` — `86b04f10ccba5090e96420aeae5f1d23172881e06958ebf6e66ec4f4c9a97cb9`

### TESTS

- `tests/presentation_phase1_context_case.py` — `4c8e5639ffd62a3a0f9e3227d038481685ed81ac126c04cecef88814b6fddabc`
- `tests/presentation_phase1_graph_fallback_case.py` — `0f8b8133380b158e3c0c186eab154058f2a7ba977cb5775a8903ffc532379f97`
- `tests/relationship_evidence_binding_cases.py` — `c38741fe4bd2a6b0eb7be42976bcf3f0a9afcc4493049139e86000c373211cfb`
- `tests/test_presentation_phase1.py` — `cb8b463b19112306d1528b6cf652fa71d53d2b4392d383677a2301edda24ca14`
- `tests/test_relationship_assessment_binding.py` — `0113b1fdbc8f5be1ad8879755f6d2c196f7ed8cb5f3587b42d2fab0115c675ad`
- `tests/test_relationship_binding_ownership.py` — `fc4c8859ca6a17e71290a2ce696f6fb0ca33bebda3273302022f4bec09f84d63`
- `tests/test_relationship_evidence_binding.py` — `9f89541504cb7c2dca0a4218c253e57b2d217bc6d2a72f1c4aebc31f6e2d5df0`

### REVIEW EVIDENCE

- `docs/reviews/relationship-evidence-binding/candidate-review.md` — `df6e85758ec9cedd1b037775b4bea460495a0f74efb764f6e41d93ba39302494`
- `docs/reviews/relationship-evidence-binding/final-assessment-ownership-correction.md` — `dea623eab6596134da33070a7f156d3f8b097a2316eea6ef164882169576c0d8`
- `docs/reviews/relationship-evidence-binding/final-independent-certification.md` — `11c12113843d1edc917e29194a09563ed3fac671063fe8bc5ecd6a86bcedeafc`
- `docs/reviews/relationship-evidence-binding/independent-certification.md` — `938e728381a652d55c3bd93017bfe92d1d2412762ac9aa453d71285185b231eb`
- `docs/reviews/relationship-evidence-binding/ownership-validation-correction.md` — `c7e469f451d67eaf1ae1dcbe35d6171b444d0c83d5238f34380fe48e6eb805af`
- `docs/reviews/relationship-evidence-binding/corrected-final-certification.md` — certification artifact (self hash omitted).
