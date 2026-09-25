# Exact relationship-evidence binding candidate

Decision: `EXACT_BINDING_CANDIDATE_READY_FOR_REVIEW`

## Baseline and boundaries

- Branch: `fix/deterministic-governed-output`.
- Starting and current HEAD: `f01d5475967eef8b2f7dd0d05a7b631f79586e25`.
- Tracked worktree/index were clean at the start; nothing was staged.
- The earlier `relationship-authority/exact-binding-blocker.md` is preserved.
- This is the binding prerequisite only. No classification, condition,
  consequence, governance, presentation, or production state-continuation
  correction is implemented.

## Producer lifecycle and contract

`build_relationship_baseline` issues `relationship_source_evidence` while the
edge and selected candidate still share the producer's exact calculation. The
candidate receives that explicit source record. No downstream pair/value/window
search is used to discover ownership.

The source ID uses domain-separated SHA-256 over `canonical_json_bytes` and
includes the registered symmetric Pearson method, sorted source columns, units,
selection, existing measurement/window summary, and digests of the complete
selected baseline/current numerical observation sequences. Those sequences
include timestamps and missingness, not just endpoints or row counts. For the
global producer they come from the pandas numerical frames actually consumed.
For the mode producer they use the same finite-number conversion as its paired
observations. Full observation values are not copied into the registry.

`_conditioned_edge` always replaces global lineage after recalculation. A global
candidate cannot resolve to the mode-conditioned temporal assessment of the
same pair. The old graph edge ID remains unchanged.

Finalization occurs in `evaluate_sii` after existing analytical consumers have
completed and canonical graph/fallback selection is known. A final record binds
source lineage, scope, exact comparison basis, retained reference/unit identity,
safe comparison qualification, existing eligibility/quality values, and either
the actual temporal descriptor or explicit temporal unavailability.

The temporal descriptor retains the reducer's existing identity, effective
parameters, complete bounded considered observations and produced assessment.
It checks reference, pair, units, mode, window and current measurement agreement;
it does not rerun or alter the reducer. Recurrence is not included in this ID.

The source method, version and measurement are validated before binding. More
than one distinct final assessment for a source leaves the candidate reference
absent. Unavailable metadata does not supply analytical proof.

## Registry and resolution

The version is `relationship-evidence.v1`. New selected candidates carry the
optional `relationship_evidence_ref`; finalized graph edges carry a separate
`relationship_evidence_id`. Neither replaces the existing graph ID.

`relationship_evidence_registry` is a result-local, canonically serialized JSON
mapping. Conflicting records under one ID are rejected. Global observations not
selected for dynamic mode analysis can remain source-only records; they are not
inserted into the dynamic graph's analytical edge collections.

The resolver requires an already-authorized registry and its scope. It verifies
version, digest, source lineage, basis, method and temporal ownership, returns a
copy, and fails closed. `require_temporal` requires an available assessment;
it does not turn an unconfirmed assessment into supported persistence.

An authenticated Phase 4 scope contributes a hashed namespace. Evaluations
without it use an explicitly result-local namespace. Neither form grants lookup
authority; no global or cross-result lookup endpoint was introduced. Consumers
must first obtain the canonical result through existing authorization.

## Fallback and historical behavior

All three existing comparison bases remain distinct. Graph-failure fallback can
bind the retained global observation, but has no temporal descriptor when the
dynamic assessment did not run. Raw failure text is excluded.

Historical reads never invoke finalization. Missing bindings/registry remain
absent, existing classification/consequence output is retained, and no migration
or reconstruction is performed.

## Propagation

- Producer lineage and final references remain in the engine/compatibility result.
- Relationship explanation and contribution projections mechanically copy the
  optional final reference.
- Canonical analysis relationships retain the reference; canonical analysis also
  retains the registry.
- Upload transport and serialized canonical reads preserve it.
- Real connector generation retains the registry in its canonical result.
- Bounded connector product transport carries relationship references, while the
  full registry remains in the authorized canonical artifact. It is deliberately
  not truncated into customer disclosure or reconstructed from that disclosure.
- No customer presentation behavior or disclosure bounds were changed.

## Validation

Final focused runs:

1. 218 tests passed across binding, temporal persistence, recurrence, graph/mode,
   supplied reference, Presentation Phase 1, telemetry handoff/transport and
   measurable consequence tests (101.66 seconds).
2. Three additional calculation-AST comparison tests passed.
3. The final binding suite, including those AST checks and canonical mapping-order
   serialization, passed all 35 tests (23.14 seconds).

There are 222 distinct tests across those focused selections. No broad campaign,
large-volume validation, LBNL/wastewater campaign, or benchmark was run.

Coverage includes:

| Requirement | Result |
| --- | --- |
| Exact retry, JSON replay, runtime metadata independence | Pass |
| Different reference, basis, context, units, baseline/current window | Pass |
| Full observations and missingness affect source identity | Pass |
| Different bounded temporal history affects final identity | Pass |
| Group/ranking/primary mutation preserves reference | Pass |
| Duplicate display names and symmetric pair normalization | Pass |
| Global and mode-conditioned producer paths | Pass |
| Recalculated mode evidence cannot inherit global lineage | Pass |
| Graph-failure binding without temporal proof | Pass |
| Historical absence, missing record, malformed reference/version | Pass |
| Tampering, copied lineage, wrong temporal identity, ambiguity | Pass |
| Conflicting duplicate registry ID | Pass |
| Upload compatibility path and stored-result transport | Pass |
| Real connector generation/retry and bounded product projection | Pass |
| Controlled temporal replay unchanged with lineage | Pass |
| Restricted-field canaries, wrong-scope resolution | Pass |
| Canonical registry ordering | Pass |

## Analytical freeze

`ANALYTICAL_MATH_CHANGED: NO`

Isolated executions against archived authoritative HEAD compare the complete
normalized semantic result for supplied-reference, global fallback,
mode-conditioned, and graph-failure cases. All four comparisons pass. Only these
four added metadata keys are removed for comparison:

- `relationship_source_evidence`
- `relationship_evidence_ref`
- `relationship_evidence_id`
- `relationship_evidence_registry`

Existing Presentation Phase 1 retained fixtures were not rewritten. Their digest
checks use the same explicit metadata exclusion. Existing classifications,
conditions, consequence values, context, ranking, graph decisions and reducer
state remain unchanged in these comparisons.

AST checks verify the existing three modified calculation/orchestration functions
against HEAD after removing only their explicit metadata additions. The temporal
and recurrence reducers, graph analyzer, classifier, condition implementation,
consequence implementation, governance implementation and production telemetry
handoff file are byte-identical to HEAD.

## Security and determinism

No credentials, raw errors, tracebacks, filesystem paths, worker/process/retry IDs
or forensic payloads are copied into the allowlisted evidence fields. Safe
existing mode/fallback codes are retained. Evidence IDs are integrity references,
not authentication tokens or encryption. Full registry access remains subject to
the existing authorized result boundary.

No wall-clock value, ranking, primary position or organizational group enters
the new identities. Canonicalization sorts registry mappings without reordering
the temporal observations. Resolution returns a copy and verifies content hashes.

## Candidate files

Production:

- `backend/app/services/relationship_evidence_binding.py` (new)
- `backend/app/services/relationship_baselines.py`
- `backend/app/engine/sii/mode_conditioned_baseline.py`
- `backend/app/engine/sii_engine.py`
- `backend/app/services/analysis_explanations.py`
- `backend/app/services/analysis_result_contract.py`

Tests:

- `tests/test_relationship_evidence_binding.py` (new)
- `tests/relationship_evidence_binding_cases.py` (new)
- `tests/presentation_phase1_context_case.py`
- `tests/presentation_phase1_graph_fallback_case.py`
- `tests/test_presentation_phase1.py`

Review evidence:

- `docs/reviews/relationship-evidence-binding/candidate-review.md` (this file)

## Review disposition

No remaining blocker was found in the focused candidate checks. Production hunks
were reviewed and `git diff --check` passed. No unrelated cleanup, dependency
change, migration, debug instrumentation, staging, commit or push was performed.
Unrelated retained artifacts and the previous blocker artifact remain outside
this candidate.

Next action: independent review of this prerequisite. The downstream authority
correction and production temporal-state continuation remain separate work.
