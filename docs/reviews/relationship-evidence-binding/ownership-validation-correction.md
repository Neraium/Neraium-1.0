# Projected assertion ownership correction

Decision: `EXACT_BINDING_CORRECTED_READY_FOR_CERTIFICATION`

## Baseline and retained history

- Branch: `fix/deterministic-governed-output`.
- HEAD remains `f01d5475967eef8b2f7dd0d05a7b631f79586e25`.
- Existing candidate changes were present; nothing was staged.
- Repository AGENTS.md was read before editing.
- The original candidate review and failed independent certification remain
  unchanged. The first candidate did not pass certification.
- No commit, push, merge, tag, deployment or unrelated cleanup was performed.

## Reproduction before production edits

Executed `evaluate_sii(**contract(16))` using the existing synthetic
supplied-reference fixture. Two distinct canonical projected assertions had
different evidence references and no full source payload.

Copying only the flow/pressure assertion's reference onto the pressure/power
assertion succeeded with both ordinary resolution and `require_temporal=True`.
The returned owner was flow/pressure. The registry was unchanged and no digest
was recomputed. This reproduced the independent certification defect.

This fixture supplies a temporal assessment; the reproduction does not assert
that the short evaluation established supported persistence or promoted a finding.

## Root cause and correction

The old resolver checked assertion ownership only if
`relationship_source_evidence` was present. Canonical projections intentionally
omitted that full payload, so ownership verification became optional.

Producer finalization now emits a compact `relationship_source_ref` directly
from the selected candidate's validated `relationship_source_evidence.source_id`.
This happens before downstream projection and independently of the registry
record lookup. It does not create a new identity algorithm or change existing
source/evidence digests.

Relationship explanation, contribution and canonical relationship projections
copy this field mechanically. They do not derive it from names, measurements,
windows, the final reference or a registry lookup.

Resolution now requires the owner reference on every authority-bearing assertion:

    assertion.relationship_source_ref == record.source.source_id

This is required in addition to existing record/source digest, scope, version,
method, basis and temporal checks. Missing or nonmatching owner references fail
closed even when a raw source payload remains available. No resolver path derives
or repairs a missing ownership reference.

## Propagation and compatibility

The opaque owner reference survives candidate, explanation, contribution,
canonical relationship, stored JSON, upload transport and connector transport
paths. Real connector generation/retry also retains both owner and evidence
references. No full source payload is added to projected assertions.

Bounded product transport carries only the opaque ownership/evidence references
already present in canonical relationships. The full evidence registry remains
in the authorized canonical artifact. No UI change or new endpoint was added.

Historical results remain readable. Neither missing field is reconstructed;
relationship authority stays unavailable. Existing classification/consequence
outputs and storage behavior are unchanged. No migration is required.

## Attack regressions

The new tests use real canonical projected assertions for the mandatory attack,
confirm both originals resolve, swap only the evidence reference in each
direction, require rejection with and without temporal requirements, and verify
the original assertions and registry remain unchanged.

Additional passing cases cover:

- Same pair with different actual reference observations/dataset identity.
- Global owner borrowing a mode-conditioned temporal reference.
- Borrowed graph-failure fallback reference, in both directions.
- Borrowed reference plus changed displayed source/target fields.
- Borrowed reference plus rank/group mutation.
- Correct evidence reference with another producer's owner reference.
- Correct owner reference with an invalid evidence reference.
- Missing, empty, malformed or tampered owner references.
- Missing owner reference even when the full raw source payload is present.
- Historical assertions with neither binding field.
- Projection must not reconstruct an omitted owner from the retained raw source.

Untampered fallback assertions still resolve their exact observation evidence,
and still fail when temporal evidence is required. Mode recalculation still has
distinct producer lineage.

## Determinism, security and analytical freeze

Owner references reuse the existing deterministic source ID. Group, rank,
primary status and runtime metadata do not participate. Retry, JSON replay,
mapping ordering and controlled temporal replay remain covered by the existing
binding suite; new assertions explicitly check owner-reference preservation.

Only an opaque digest reference is added to projected assertions. No raw
observations, credentials, errors, paths, process/worker/retry identifiers or
forensic payloads are added. The reference is not an authorization token;
existing result/site/workspace authorization remains required.

`ANALYTICAL_MATH_CHANGED: NO`

The correction changes no source/evidence identity calculation, analytical
producer, reducer, threshold, context method or authority consumer. Eight
protected implementation files (temporal and recurrence reducers, graph analyzer,
classifier, conditions, consequence, governance and telemetry handoff) were
independently compared byte-for-byte with HEAD and remain identical.

The existing three calculation-AST checks and four isolated HEAD comparisons
(supplied reference, global fallback, mode-conditioned and graph-failure paths)
pass. Analytical normalization now additionally excludes only the new
`relationship_source_ref` metadata field. Retained analytical fixtures were not
rewritten. No downstream consumer begins using the binding for qualification.

Production temporal-state continuation remains a separate follow-up.

## Files changed by this correction

Production:
- backend/app/services/relationship_evidence_binding.py
- backend/app/services/analysis_explanations.py
- backend/app/services/analysis_result_contract.py

Tests:
- tests/test_relationship_binding_ownership.py (new; 18 tests)
- tests/test_relationship_evidence_binding.py (stronger owner propagation/invariance checks)
- tests/relationship_evidence_binding_cases.py (explicit metadata exclusion)

Review:
- docs/reviews/relationship-evidence-binding/ownership-validation-correction.md

The original candidate's other production/test changes remain present; their
complete diff was reviewed together with this correction.

## Validation results

- Initial correction run: 53 ownership/binding tests passed.
- Final focused run: **113 passed**, six warnings, 58.49 seconds.
- Included ownership attacks, all existing binding tests, relevant Presentation
  Phase 1 compatibility tests, telemetry handoff/product projection tests and
  measurable-consequence tests.
- `git diff --check` passed; the index remains empty.
- No broad regression campaign, large-volume validation or benchmark was run.

No remaining blocker was found in these focused correction checks. Independent
certification of the complete corrected candidate is still required.

## Preserved artifact hashes

- candidate-review.md:
  `df6e85758ec9cedd1b037775b4bea460495a0f74efb764f6e41d93ba39302494`
- independent-certification.md:
  `938e728381a652d55c3bd93017bfe92d1d2412762ac9aa453d71285185b231eb`
- ../relationship-authority/exact-binding-blocker.md:
  `47cb230adcba76d18f7637f199968c190c1ffe4fcea45c52823150119d645151`

Next action: repeat independent adversarial certification. Do not resume the
downstream relationship-authority correction as part of this candidate.
