# Resource-to-assessment binding candidate

Decision: RESOURCE_BINDING_CANDIDATE_READY_FOR_REVIEW

Baseline: `fix/deterministic-governed-output`,
`a922c496fa2baeac63b7c882a640d8e6b58caa90`.
Read AGENTS.md and the existing consequence-ownership preflight. Earlier reports
and unrelated work remain untouched. This report supersedes the resource blocker
for prospective exact-source cases; it does not certify the full finding/group
qualification correction.

## Resource ownership contract

Two additive metadata fields implement `resource-relationship.v1`:

- `resource_relationship_source_ref`: the actual selected graph edge's validated
  producer source ID. New provisional/updated relationship-memory entries retain
  this source directly from the consumed edge. Training copies it from the actual
  relationship-memory entry selected for that model; evaluation copies it from
  the actual selected model. Missing lineage stays missing/unavailable. Updating
  an entry with an unbound edge clears the current lineage instead of inheriting
  an old source. No pair-name lookup fills this field.
- `resource_relationship_binding`: a version, the complete certified
  `relationship_source_ref` / `relationship_evidence_ref` /
  `relationship_assessment_binding` tuple, and a resource integrity digest.

After the existing relationship finalizer completes, the new resource finalizer
requires one unique valid final record for that exact carried source in the
already authorized result registry. It uses the certified `assessment_binding`
function, unchanged, and validates the resulting tuple with the certified
resolver. It never selects by relationship names, IDs from relationship memory,
contributions, ranking, primary status, or overlapping signals. Multiple final
records for the same source leave resource authority unavailable. This uniqueness
check is identity disambiguation, not persistence voting.

The finalizer does not take a ranked candidate list. Adding, removing, or ordering
unrelated registry records cannot change a resource's binding. The final tuple
matches the existing assertion tuple when they own the same exact assessment.
The source pointer is producer lineage only and cannot itself authorize a
consequence. A changed comparison source cannot adopt an older model's lineage.

The resource digest covers the tuple and rate inputs/provenance: completion
status, target, predictors, source relationship IDs, model type/version/parameters,
training window, source model version, operating mode, aligned observations,
maximum gap, observation method, and carried source reference. Presentation and
ranking fields do not participate. No raw observations are newly disclosed in
the binding itself.

These are integrity hashes, not signatures or authorization capabilities. The
trust boundary remains the authorized producer/result store, as in the certified
relationship contract. Replacing and recomputing an entire trusted producer
assignment is outside component-substitution protection. There is no new endpoint,
lookup service, privilege, or credential.

## Consumer authority and compatibility

A consequence requires the finding itself to carry the same complete tuple as
the sealed resource. Contributions cannot supply or expand it. The certified
resolver must resolve temporal evidence in the accepted registry scope; the
resolved assessment must retain `eligible: true` and
`persistent_relationship_change: true`. Target/predictor consistency is checked
only after exact resolution, never to select an owner. The calculation window
must lie within that exact assessment's current window.

All existing consequence gates remain: finding persistence, comparable context,
exact non-disjoint calculation window, explicit source relationship provenance,
exactly one compatible mapped resource, explicit positive acquisition gap,
aligned observations, supported unit conversion, per-observation validity and
window restrictions. The package's rate integration and numerical inputs are
unchanged. The new seal is included in successful consequence provenance.

`_relationship_ids` now reads only explicit finding provenance and no longer
unions supporting/contributing relationships. Such IDs remain an additional
provenance gate and cannot replace the ownership tuple.

`attach_measurable_consequences` requires a unique original finding ID, an exact
matching tuple, the same window, and consistency of projected persistence/context
fields when present. Missing/duplicate originals, missing owners, changed owners,
and conflicting projected qualification inputs refuse; there is no group or
current-finding fallback. Canonical condition/insight projection only copies an
already complete tuple. It never derives one from a primary or a contribution.
No display, narrative, ranking, or Presentation Phase 1 code was changed.

Compatibility is deliberately fail closed for new calculations: existing models
without lineage, models tied to a different source, unscoped grouped findings,
and fallback records without temporal authority cannot quantify by inference.
This can reduce numerical availability until an exact scoped finding and resource
are both present. It is the missing-ownership behavior explicitly authorized in
the follow-up request, not a promise of positive authority for every legacy model.

Recorded historical consequences remain readable without reconstruction. No
historical records, snapshots, or stored calculations were rewritten or rerun.
No production temporal-state continuation was added. The broader finding-persistence
adapter remains unchanged and is a separate next phase.

## Files in this candidate

Production (7):

- `backend/app/services/resource_relationship_binding.py` (new contract)
- `backend/app/engine/sii/behavioral_model.py` (prospective source retention)
- `backend/app/engine/sii/phase4.py` (provisional source retention)
- `backend/app/engine/sii/expected_behavior.py` (model/series lineage copying)
- `backend/app/engine/sii_engine.py` (post-assessment resource finalization)
- `backend/app/services/measurable_consequence.py` (exact ownership gates)
- `backend/app/services/analysis_result_contract.py` (mechanical tuple copying)

Tests (4):

- `tests/resource_binding_cases.py` (new controlled producer fixture)
- `tests/test_resource_relationship_binding.py` (new focused validation)
- `tests/test_measurable_consequence.py` (explicitly bound eligible fixtures)
- `tests/test_relationship_evidence_binding.py` (narrow authority-era comparison)

Review (1): this file. The previous preflight artifact is retained unchanged.

## Verification and analytical freeze

ANALYTICAL_MATH_CHANGED: NO

No changes to relationship/graph calculations, persistence/recurrence reducers,
thresholds, context definitions, sufficiency/quality reducers, corroboration,
governance, ranking/primary selection, telemetry admission, human authority,
control, or the consequence package. No migration or temporal continuation.

Focused command:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend:tests .venv/bin/python -m pytest -q tests/test_resource_relationship_binding.py tests/test_measurable_consequence.py tests/test_relationship_assessment_binding.py tests/test_relationship_binding_ownership.py tests/test_relationship_evidence_binding.py tests/test_sii_phase4_primitives.py tests/test_sii_phase4_orchestrator.py
```

The new tests cover:

- Persistent A/resource A: numerical output unchanged (including approximately
  12,840 units in the existing six-hour fixture), complete old-adapter result
  equality after removing only the newly added consequence binding provenance.
- Persistent A/resource B, including shared target signals: rejection.
- Multiple resources: only the exact owner is usable; no cross-borrowing.
- Group/rank/primary mutations and unrelated registry membership/order: unchanged
  ownership; JSON transport preserves it.
- Context, finding persistence, gap, units, window, and observation-quality gates;
  actual expected-model quality and insufficient-coverage failures.
- Unconfirmed and graph-failure temporal evidence, stale sources, and ambiguous
  same-source final records: refusal.
- Original finding absence, duplicate IDs, changed owner, absent projected tuple,
  changed context/window/persistence: refusal.
- Missing historical binding: no reconstruction; recorded consequence read remains
  unchanged. Consumer attacks never recompute a seal to legitimize substitution.
- Actual graph-source -> provisional memory -> train -> evaluate -> resource
  finalization -> resolver path. Missing producer source does not get inferred.
- Full expected-model training and evaluation output equality with committed
  `a922c496`, excluding only the additive lineage field.
- Existing exact-binding substitution attacks and Phase 4 producer checks.

The old pre-binding semantic comparisons initially failed because unowned
consequences now have narrower refusal diagnostics. Their comparison now explicitly
asserts `not_quantifiable` on both sides and normalizes only that refusal payload;
it does not permit a quantified result to disappear or appear. All other semantic
fields still compare. The existing engine AST comparison additionally excludes
only the new metadata-finalizer import/call. Positive consequence numerical
invariance is checked separately against the committed adapter, including gate
variants. No analytical failure was hidden by a blanket consequence exclusion.

An early synthetic temporal fixture used numeric timestamps unsupported by the
existing graph timestamp parser and remained limited. The fixture was corrected
to ISO timestamps without touching the parser or reducer. Subsequent eligible
checks passed. The first draft's candidate-list dependency was removed in review;
final resource assignment reads the exact registry, independent of ranking.

No broad, LBNL, wastewater, large-volume, browser, or performance campaign ran.
Final combined focused run: **133 passed**, two warnings, 60.99 seconds.
Final review then changed resource resolution to pass the complete finding to the
certified resolver (preserving its full-source consistency checks) and added a
conflicting-raw-source attack case. The affected resource/consequence suites were
rerun: **51 passed**, two warnings, 19.30 seconds. All tests affected by that last
change passed; the other focused suites were not unnecessarily rerun.

Reviewed the tracked diff and all new candidate files. `git diff --check` passed;
`git diff --no-index --check` also passed for all four new files. The certified
binding implementation and seven protected relationship/reducer/classification/
corroboration/governance/window files have no diff against the committed baseline.
Branch and HEAD remain unchanged; the index is empty. No staging, commit, push,
cleanup of unrelated artifacts, or production data writes were performed.

## Next action

Review this prospective resource-binding candidate. Then implement the separate
relationship-owned finding qualification correction, keeping scoped findings
independent of group qualification. Do not stage, commit, or push without explicit
user authorization.
