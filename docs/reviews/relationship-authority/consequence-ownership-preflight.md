# Relationship authority: consequence ownership preflight

DECISION: RELATIONSHIP_AUTHORITY_BLOCKED_CONSEQUENCE

## Baseline and disposition

Inspected branch `fix/deterministic-governed-output` at
`a922c496fa2baeac63b7c882a640d8e6b58caa90`. Read repository AGENTS.md, the retained
relationship-authority blocker, and the corrected exact-binding certification.
The tracked worktree and index were initially clean. Pre-existing untracked work,
including the earlier authority blocker, remains untouched.

The certified assertion binding is present and is not being rejected or reopened.
`relationship_source_ref` + `relationship_evidence_ref` +
`relationship_assessment_binding` can resolve the assertion's exact final assessment.
The remaining gap is the resource-series side of consequence ownership. No
production or test changes were made. This report is the sole added artifact.

## Implementation surface inspected

- `analysis_explanations.py:780`: `relationship_persistence_info` currently tests
  all grouped columns against `persistent_columns`. Its caller passes all group
  columns and the primary relationship. This confirms the requested overcoupling.
- The assertion resolver can support an individual relationship authority adapter
  without changing reducers. Group classification cannot simply consume that
  relationship's boolean: scoped qualification and downstream condition propagation
  would also need an explicit authority boundary.
- `measurable_consequence.py:120`: the adapter accepts finding-level persistence.
  Its resource selection subsequently checks that `source_relationships` is a
  subset of finding relationship IDs. Neither check resolves the certified tuple.
- `expected_behavior.py:37`: training receives relationship memory and passes a
  memory relationship ID to the fitted model. The fitted model returns
  `source_relationships: [relationship_id]` at line 490.
- `behavioral_model.py:855`: that memory identity is produced from columns,
  relationship type, and operating mode. It is not a final assessment reference.
- `expected_behavior.py:222`: evaluation copies those model relationship IDs
  into the resource series. It does not retain the certified source, evidence, or
  assessment-binding fields. Model version, training run, target, predictor,
  timestamps, and model ID are useful provenance but do not establish the missing
  exact final-assessment assignment.
- `sii_engine.py:1239`: finalization issues the certified assertion bindings after
  Phase 4 consumers, including expected behavior, have completed. It does not
  bind expected resource series to the final registry.
- `measurable_consequence.py`, `attach_measurable_consequences`: original findings
  are selected by condition/finding ID, with a fallback to the current finding.
  This also requires review when implementing exact consequence ownership; a
  group identifier alone must not supply relationship persistence authority.

## Why implementation stopped

The current exact binding supports assertion-to-assessment ownership, but does
not provide a resource-series-to-assessment assignment. Joining the latter by
pair, memory relationship ID, target/predictor names, group membership, or primary
selection would introduce the expressly prohibited inferred ownership.

A strict missing-binding refusal could prevent consequence promotion, but would
leave all currently produced expected resource series without a supported positive
consequence path. This review does not silently choose that compatibility change
as the complete correction. Nor does it invent a new producer resource assignment
contract inside the certified assertion contract. The user explicitly required a
stop when exact binding cannot support the correction without heuristic matching.

This is not a claim that a future metadata-only producer extension is impossible.
The prerequisite is an explicit, producer-carried resource assignment to the exact
compatible relationship assessment, with finding ownership checked at consumption.
Historical records must remain unbound rather than being reconstructed. Such an
extension must preserve expected-rate calculations and consequence mathematics.

## Focused verification

Executed:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend:tests .venv/bin/python -m pytest -q tests/test_relationship_assessment_binding.py tests/test_measurable_consequence.py
```

Result: **33 passed**, two warnings, 13.31 seconds. These are baseline checks,
not certification of a relationship-authority correction. They include exact
assessment substitution rejection and the existing consequence adapter behavior.

Additional read-only synthetic diagnostic used 40 rows with `t=i*60`,
`load=10+i`, `flow=25+2*i`, and one active relationship-memory entry (`rel-1`,
running mode, strength 0.9, load -> flow). Actual `train_expected_behavior_models`
and `evaluate_expected_behavior` produced two models and two resource series.
All four lacked every member of the certified ownership tuple.

The existing `test_measurable_consequence.fixture()` quantified using only its
legacy relationship ID and finding persistence. Inputs were unchanged. The
reported amount was 12839.999999999996. An initial diagnostic assertion of exact
equality to integer 12840 failed; rerunning with `math.isclose(..., rel_tol=1e-12)`
passed. This was floating-point comparison in the diagnostic, not a production
failure or a mathematics change.

Mandatory candidate cases 1–17 were **not executed as an implementation matrix**:
implementation stopped at the consequence prerequisite. Existing focused tests
cover some binding/fallback/mutation and consequence scenarios, but do not count
as validation of the requested new scoped authority behavior. No full regression,
LBNL, wastewater, scale, performance, or browser campaign ran.

## Invariants and next action

ANALYTICAL_MATH_CHANGED: NO

No reducers, thresholds, context, eligibility, quality, recurrence, graph or
relationship mathematics, ranking, consequence mathematics, governance, human
review, telemetry admission, control, Presentation Phase 1, or temporal-state
continuation were changed. No historical reconstruction, migration, or rerun.
The requested false-suppression/false-promotion correction and hard group-mutation
invariant remain unimplemented and are not claimed to pass.

Reviewed `git diff`; tracked production/test diff remains empty.
`git diff --check` passed. No staging, commit, or push.

Next action: define and certify the missing producer-owned resource-to-assessment
assignment and its compatibility behavior, then resume the scoped authority
correction and all 17 mandatory cases. Do not substitute a name/ID join.
