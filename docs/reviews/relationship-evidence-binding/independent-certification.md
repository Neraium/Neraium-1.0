# Independent adversarial certification

Decision: `EXACT_BINDING_BLOCKED_IDENTITY_DEFECT`

Certification stopped at the first reproduced material defect. No production
code or tests were changed. No staging, commit, push or cleanup was performed.

## Baseline and inventory

Branch: `fix/deterministic-governed-output`.

HEAD, origin tracking ref and live origin branch all matched
`f01d5475967eef8b2f7dd0d05a7b631f79586e25`. The index was empty.

Candidate inventory before this certification artifact: 12 paths.

Production:
- backend/app/services/relationship_evidence_binding.py (untracked)
- backend/app/services/relationship_baselines.py
- backend/app/engine/sii/mode_conditioned_baseline.py
- backend/app/engine/sii_engine.py
- backend/app/services/analysis_explanations.py
- backend/app/services/analysis_result_contract.py

Tests:
- tests/test_relationship_evidence_binding.py (untracked)
- tests/relationship_evidence_binding_cases.py (untracked)
- tests/presentation_phase1_context_case.py
- tests/presentation_phase1_graph_fallback_case.py
- tests/test_presentation_phase1.py

Review:
- docs/reviews/relationship-evidence-binding/candidate-review.md (untracked)

There were 9,411 other untracked paths, excluded from the candidate. These include
the previous relationship-authority/exact-binding-blocker.md. They were not
modified or cleaned up. This certification artifact is the only new review file.

## Material defect: projected assertion can borrow another owner's reference

The canonical relationship projection retains `relationship_evidence_ref` but
does not retain `relationship_source_evidence`.

`resolve` validates assertion ownership only inside this conditional:

    if SOURCE in assertion and (not valid_source(assertion) or assertion[SOURCE] != source):
        return None

When SOURCE is absent, a valid reference to another relationship in the same
authorized registry is accepted. The resolver verifies that the evidence record
is intact, but does not establish that it belongs to the supplied assertion.

## Independent reproduction

Used the existing synthetic real-engine fixture:

    result = evaluate_sii(**contract(16))
    analysis = result['analysis_result']
    registry = analysis[REGISTRY]
    a, b = analysis['relationships'][:2]
    changed = deepcopy(b)
    changed[REF] = a[REF]
    resolved = resolve(changed, registry,
                       authorized_scope=registry['scope'], require_temporal=True)

Both original assertions lacked SOURCE. Their references and relationship pairs
were distinct. No digest was recomputed and no registry record was changed.

Observed output:

    assertion_pair: [tag:flow, tag:pressure]
    resolved_owner_columns: [power, pressure]
    foreign_reference_accepted: true
    registry_unmodified: true
    digest_recomputed: false

This demonstrates incorrect assertion-to-evidence ownership, including acceptance
when temporal evidence is requested. It does not claim that this short fixture
established supported persistence or that any downstream finding was promoted.
Those consumers have not yet been changed to use the new reference.

## Test gap explaining the escape

The existing copied-lineage negative test mutates a raw candidate that still
contains SOURCE. It exercises the conditional validation branch, not the actual
canonical projected assertion shape where that branch is skipped.

A necessary correction must preserve exact owner validation after canonical
projection. A regression must use two distinct real projected assertions, copy
only the valid reference between them, keep the registry untouched, and require
resolution to fail. No corrective design or implementation was performed here.

## Certification disposition

`git diff --check` passed. Full analytical-freeze, remaining identity, route,
security and compatibility certification was not completed after the required
stop. Prior candidate test totals are not substituted for independent approval.

No certified commit allowlist or commit subject is issued. Correct the ownership
defect in a separately authorized task, then repeat independent certification.
