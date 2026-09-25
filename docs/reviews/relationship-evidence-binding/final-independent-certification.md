# Final independent certification — blocked

Decision: EXACT_BINDING_BLOCKED_IDENTITY_DEFECT

Baseline: branch `fix/deterministic-governed-output`; local HEAD, origin tracking
reference and live remote all `f01d5475967eef8b2f7dd0d05a7b631f79586e25`.
Nothing staged. Certification stopped on the material defect below. Production
and tests were not modified. Previous review artifacts remain intact.

## Original correction verification

Independently executed `evaluate_sii(**contract(16))` using the synthetic
supplied-reference helper in `tests/test_sii_supplied_reference.py`. Two real
canonical assertions had different source references and evidence references.
Both originals resolved normally and with `require_temporal=True`. Replacing
only either assertion's evidence reference with the other's was rejected in
both directions, with and without the temporal requirement. The registry stayed
structurally unchanged. The previously reported different-owner attack is fixed.

## Remaining defect: final comparison scope is not assertion-bound

Executed the same supplied-reference inputs twice: once normally, once with
`app.engine.sii_engine.analyze_relationship_graph` patched to raise a synthetic
RuntimeError. Selected corresponding real canonical assertions with identical
producer source references. Their final evidence references differed, as did
their comparison bases.

For this controlled attack, combined the intact records from both result-local
registries using the candidate's `registry_record` helper. This is a diagnostic
registry containing two actual producer assessments, **not a claim that a
normal single engine execution emits this combined registry**. Both records
retain their original digests and scope. No record was edited or rehashed.
Both original assertions resolved in this registry. After its construction the
registry remained unchanged throughout all attacks.

| Assertion | Only replacement | Normal resolution | Temporal-required resolution |
|---|---|---|---|
| Failure-fallback | Successful global evidence ref | Accepted, global basis | Accepted |
| Successful global | Failure-fallback evidence ref | Accepted, failure-fallback basis | Rejected |

The fallback assertion's owner reference and every other assertion field were
unchanged. Successful temporal evidence was thereby returned for an assertion
produced on a path without that temporal assessment. Acceptance means temporal
assessment availability, not a claim that the reducer established persistence.

The requested cross-basis rejection requirement is therefore not met. This
does not demonstrate an authorization endpoint bypass or an exploit against a
normal unmixed registry. It demonstrates that the resolver cannot distinguish
these assertions' final assessment ownership once both valid records are in
the accepted scope.

## Root cause

`relationship_evidence_binding.py:229` carries the calculation source ID as the
assertion owner. The source calculation is legitimately identical across these
two paths. At lines 259–260 resolution checks only that source ownership;
lines 263–278 validate the referenced record's own basis and temporal coherence,
not its compatibility with an independently retained assertion assessment scope.
The source reference does not distinguish final comparison assessments.

Minimal reproduction after obtaining normal result `r` and forced-failure result
`f` from identical `contract(16)` inputs:

```python
a = r['analysis_result']['relationships'][0]
fa = next(x for x in f['analysis_result']['relationships']
          if x[OWNER_REF] == a[OWNER_REF])
registry = deepcopy(r[REGISTRY])
for record in f[REGISTRY]['records'].values():
    registry_record(registry, record)
saved = deepcopy(registry)
attack = deepcopy(fa)
attack[REF] = a[REF]
assert resolve(attack, registry, authorized_scope=registry['scope'],
               require_temporal=True) is not None  # Required rejection fails.
assert registry == saved
```

## Inventory at stop

Production: `backend/app/services/relationship_evidence_binding.py` (new),
`backend/app/services/relationship_baselines.py`,
`backend/app/engine/sii/mode_conditioned_baseline.py`,
`backend/app/engine/sii_engine.py`,
`backend/app/services/analysis_explanations.py`,
`backend/app/services/analysis_result_contract.py`.

Tests: `tests/test_relationship_evidence_binding.py` (new),
`tests/relationship_evidence_binding_cases.py` (new),
`tests/test_relationship_binding_ownership.py` (new),
`tests/presentation_phase1_context_case.py`,
`tests/presentation_phase1_graph_fallback_case.py`,
`tests/test_presentation_phase1.py`.

Review evidence: existing candidate-review.md, independent-certification.md,
ownership-validation-correction.md, and this final-independent-certification.md
under this directory. The earlier relationship-authority blocker and unrelated
retained validation artifacts are excluded.

## Certification limits

`git diff --check` passed before this report. No broad campaigns were run.
The focused independent diagnostic reproduced the original attack's rejection
and the remaining cross-basis acceptance. Full analytical HEAD comparisons,
transport certification, security certification and the remaining attack matrix
were not completed after the stop condition. Analytical mathematics is not
certified by this interrupted review. No commit allowlist or commit subject is
approved. A narrow scope-ownership correction requires separate authorization;
no fix or redesign was attempted here.
