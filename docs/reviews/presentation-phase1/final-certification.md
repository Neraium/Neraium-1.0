# Corrected candidate final certification

FINAL DECISION: PRESENTATION_PHASE1_BLOCKED_SEMANTIC_DEFECT

Certification stopped on the independently reproduced comparison-basis omission below. Prior conclusions were not accepted as evidence. No production code or tests were changed. This report is the only certification artifact created. No staging, commit, push, merge, tag or deployment occurred.

## BASELINE

Branch: `fix/deterministic-governed-output`.
HEAD and live remote branch (`git ls-remote origin refs/heads/fix/deterministic-governed-output`): `1bc6d9e031264991ce9cc7ea6bee2ac51b070626`.
No Presentation Phase 1 commit follows the authoritative baseline. Staged files: none.

## CANDIDATE INVENTORY

Derived from actual tracked modifications and untracked paths, not prior inventory claims. Six tracked modifications and seventeen untracked candidate files existed at entry. This report adds one REVIEW_EVIDENCE file.

| Path | Classification | Entry state |
|---|---|---|
| backend/app/routers/data.py | PRODUCTION_API_PROJECTION | Modified |
| backend/app/services/telemetry_result_projection.py | PRODUCTION_API_PROJECTION | Modified |
| backend/app/services/upload_persistence.py | PRODUCTION_API_PROJECTION | Modified |
| backend/app/services/relationship_observation_projection.py | PRODUCTION_PRESENTATION | Untracked |
| frontend/src/components/EngineeringReasoningWorkspace.jsx | FRONTEND_PRESENTATION | Modified |
| frontend/src/styles/evidence-dashboard.css | FRONTEND_PRESENTATION | Modified |
| frontend/src/components/engineering/RelationshipObservations.jsx | FRONTEND_PRESENTATION | Untracked |
| frontend/src/components/EngineeringReasoningWorkspace.test.js | TEST | Modified |
| frontend/src/components/engineering/RelationshipObservations.test.js | TEST | Untracked |
| frontend/tests/fixtures/presentation-phase1.json | TEST | Untracked |
| frontend/tests/fixtures/presentation-phase1-context-fallback.json | TEST | Untracked |
| frontend/tests/e2e/presentation-phase1.spec.js | E2E_TEST | Untracked |
| tests/fixtures/presentation_phase1_invariants.json | TEST | Untracked |
| tests/presentation_phase1_cases.py | TEST | Untracked |
| tests/presentation_phase1_context_case.py | TEST | Untracked |
| tests/test_presentation_phase1.py | TEST | Untracked |
| tests/test_presentation_phase1_context.py | TEST | Untracked |
| docs/reviews/presentation-phase1/README.md | REVIEW_EVIDENCE | Untracked |
| docs/reviews/presentation-phase1/baseline-verification.json | REVIEW_EVIDENCE | Untracked |
| docs/reviews/presentation-phase1/cases.json | REVIEW_EVIDENCE | Untracked |
| docs/reviews/presentation-phase1/context-qualification-correction.md | REVIEW_EVIDENCE | Untracked |
| docs/reviews/presentation-phase1/final-adversarial-review.md | REVIEW_EVIDENCE | Untracked |
| docs/reviews/presentation-phase1/restart-verification.json | REVIEW_EVIDENCE | Untracked |
| docs/reviews/presentation-phase1/final-certification.md | REVIEW_EVIDENCE | Created by certification |

All candidate paths fit the requested categories. The other 9,410 untracked files are excluded, not certified for inclusion: release history, security closeout/hardening, LBNL blind/determinism, prize, validated-candidate integration, wastewater retained artifacts, the two root validation summaries, and nine prize validation/report scripts. No wildcard staging of docs/reviews, docs/validation, scripts, or the worktree is authorized by this inventory.

## CORRECTION VERIFICATION

The original strong-general-match case is corrected. A fresh real-engine test reproduced `strong`, like-mode `limited`, `used_global_fallback=true`, `insufficient_recent_mode_rows`, and `global_relationship_model`. All four tested retrieval paths retained that qualification. Unit and Chromium checks verified the adjacent customer-visible labels and unchanged assessment.

The correction is incomplete for another existing engine comparison basis; see DEFECTS FOUND.

## PRESENTATION SEMANTICS

Observation, temporal support, recurrence, persistence and edge promotion have separate fields. Positive recurrence with no temporal support/persistence/promotion is directly tested. No-finding and insufficient presentation remain governed by existing assessment. The helper does not promote or classify observations. However, the recorded failure-fallback comparison basis is lost, preventing complete semantic certification.

## ANALYTICAL BYTE / AST CERTIFICATION

Byte-compared all 242 tracked files under backend/app against HEAD. Only the three inventoried backend API/projection files differ. AST comparison identified only four changed definitions: `baseline_comparison_analysis_by_id`, `comparison_analysis_by_id`, `build_canonical_result_projection`, and `project_result_for_transport`.

Every production hunk and both new production source files were inspected. Analytical mathematics did not change. The inspected additions do not change thresholds, confidence, quality, strength, displacement, persistence/recurrence/temporal/drift reducers, context matching/features, reference windows, pooled thresholds, eligibility, analytical coverage, uncertain-observation admission, ranking, primary selection, classification or consequence qualification.

A fresh isolated git archive of HEAD independently matched the candidate for A–D analytical invariants and graph semantic digests, the real-engine fallback case, and the existing 16/32/64-row supplied-reference analytical digests. Only the two controlled case helpers were copied into the temporary archive; no production source was copied from the candidate.

## DISCLOSURE BOUNDS

Inspected and focused tests passed: first 12 retained dictionary edges in engine order, at most 48 KiB compact UTF-8 JSON, deterministic trailing whole-observation removal, and correct displayed/omitted counts. Qualification is included before byte measurement. These are transport bounds; analytical coverage, ranking and primary selection are untouched. UI explicitly distinguishes retained graph counts from upstream pair coverage.

## API / RETRIEVAL PATHS

Traced compact upload projection and its upload session/state/connection callers; explicit analysis retrieval; scoped baseline analysis retrieval; connector projection. The same helper supplies the disclosure, so the blocking omission affects every family. Existing scope/identity checks remain before projection. Connector product filtering does not remove the currently allowlisted qualification fields. Existing transport mirrors can retain the derived projection; canonical analysis and storage authority remain unchanged.

## PHYSICAL MAGNITUDE / CONSEQUENCE

Deferred. No new physical magnitude or consequence computation. Displayed correlations remain explicitly unitless. Measurable-consequence code is byte-identical, and independent case comparisons preserve consequence status. No impact/loss/savings claim was introduced by the disclosure.

## SECURITY / PROVENANCE

Inspected scalar/nested field allowlists and source paths. Focused restricted-field tests passed. The failure reproduction confirms raw exception text is excluded. The blocker concerns omission of a fixed, safe engine enum, not a request to expose exception text. No authorization endpoint bypass or changed workspace/site enforcement was found. Complete certification stops at the semantic defect.

## DETERMINISM / REPLAY

Focused map-order, volatile-metadata independence, optional-field and byte-truncation tests passed. Fixed allowlist order and retained list order do not consult clocks, worker/process/retry identity or rendering order. No analytical replay or historical reconstruction was introduced.

## BACKWARD COMPATIBILITY

Historical missing graph evidence remains absent; missing qualification is not synthesized. Source immutability and additive transport behavior passed focused tests. No migration or canonical rewrite was found. Existing historical absence differs from the defect: the reproduced comparison basis exists in the source and is actively dropped.

## UI / UX CERTIFICATION

35 frontend tests passed across the disclosure and workspace suites. Chromium passed A desktop (1440px), B mobile (390px), and corrected fallback mobile (390px), verifying default collapse, visible evidence, unchanged brief, no horizontal overflow and no control inputs. Production build passed during browser startup. These checks do not certify the omitted failure-fallback basis: JSX renders Comparison basis only when the projection retains it.

## TEST ADEQUACY

Fresh focused backend run: 35 passed across `test_presentation_phase1.py`, `test_presentation_phase1_context.py`, `test_sii_evidence_transport.py`, and `test_telemetry_result_projection.py`.

Fresh frontend run: 35 passed across RelationshipObservations and EngineeringReasoningWorkspace tests. Locked `npm run setup:codex` completed before browser tests. Three Chromium tests and the production build passed.

Tests were inspected, not just counted. They exercise A–D, recurrence, temporal support, persistence/promotion separation, bounds, identity, historical absence, restrictions, all four disclosure retrieval paths, and the corrected normal fallback case. They omit the engine's `global_relationship_model_failure_fallback` branch. Passing tests therefore do not establish complete comparison-basis preservation. No broad regression, large validation campaign or benchmark ran.

## BEFORE / AFTER VERIFICATION

Fresh clean-HEAD comparisons matched exact analytical invariants and graph semantic digests:

- A: empty classification/primary, no promoted finding.
- B: insufficient_evidence, no primary, nonpersistent, not_quantifiable.
- C: unexplained_systemic_change, same selected relationship, supplied persistent finding contract, not_quantifiable.
- D: context_limited_relationship_change, same selected relationship, nonpersistent, not_quantifiable.
- Original fallback: possible_instrumentation_issue from the existing constant signal, no primary, three nonpromoted/nonpersistent edges, not_quantifiable. Analytical digest `b973f98207ebf3576d9f88d6a13ed5f944f1253358860fef949b380687c2edad`; graph digest `e525c41d9557b8532d244fbb758436f9b81433b052a49a239422a234347b01cc`.

A–D remain controlled contracts; C supplies finding persistence and does not prove production state handoff. Graph digest comparison also covers recurrence semantics. These successful comparisons do not resolve the newly reproduced presentation omission.

## DIFF HYGIENE

`git diff --check` passed before the blocker. All production hunks were inspected: no unrelated refactor, debug code, analytical formatting change, dependency change or new production credentials/customer telemetry/local paths. Certification changed only this report. Existing historical verification hashes are historical records, not assertions that corrected source still has those old hashes.

## DEFECTS FOUND

**P2 — Known engine failure-fallback comparison basis is discarded.**

`backend/app/engine/sii_engine.py:806–819` retains the global relationship-model graph when dynamic relationship-graph analysis fails and records `edge_basis=global_relationship_model_failure_fallback`. This is a fixed engine code, not customer-unsafe exception text.

`backend/app/services/relationship_observation_projection.py:19` permits only `global_relationship_model` and `mode_conditioned_relationships`. Lines 72–74 consequently discard the valid third basis. `frontend/src/components/engineering/RelationshipObservations.jsx` likewise maps only those two values and conditionally omits Comparison basis when absent.

Independent controlled reproduction exercised the real engine failure branch without editing code or tests:

```python
from unittest.mock import patch
from app.engine.sii_engine import evaluate_sii
from app.services.relationship_observation_projection import relationship_observations
from test_sii_supplied_reference import contract

with patch('app.engine.sii_engine.analyze_relationship_graph',
           side_effect=RuntimeError('CONTROLLED_FAILURE_CANARY')):
    result = evaluate_sii(**contract(64))
projected = relationship_observations(result)
assert result['relationship_graph']['edge_basis'] == 'global_relationship_model_failure_fallback'
assert projected['coverage']['displayed'] == 3
assert 'edge_basis' not in projected['comparison_qualification']
```

Observed source/projection:

```json
{
  "recorded_basis": "global_relationship_model_failure_fallback",
  "edge_count": 3,
  "recorded_mode": {
    "status": "limited",
    "used_global_fallback": true,
    "fallback_reason": "no_explicit_operating_mode_features"
  },
  "projected_qualification": {
    "mode_conditioned_baseline": {
      "status": "limited",
      "used_global_fallback": true,
      "fallback_reason": "no_explicit_operating_mode_features"
    }
  },
  "displayed": 3,
  "raw_error_exposed": false
}
```

The UI communicates the separate like-mode limitation but loses the recorded basis of the displayed fallback graph. Thus comparison-basis/provenance qualification is not preserved for every supported engine retrieval state. This is a presentation-semantic defect, not an analytical mathematics change or evidence that global fallback itself invalidates analysis.

Required separately authorized correction: preserve and safely label this existing enum, keep exception text excluded, and directly cover the failure-fallback graph through projection/transport and UI. No fix was attempted during certification.

## FINAL COMMIT ALLOWLIST

Not issued: certification failed. The inventory is not a staging allowlist.

## RECOMMENDED COMMIT SUBJECT

None until certification passes.

## FINAL DECISION

PRESENTATION_PHASE1_BLOCKED_SEMANTIC_DEFECT

## NEXT ACTION

Correct the narrow comparison-basis omission in a separate implementation task, then repeat certification. Do not commit this candidate as-is.
