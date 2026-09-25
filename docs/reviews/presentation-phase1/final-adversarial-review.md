# Final adversarial candidate review

FINAL DECISION: **PRESENTATION_PHASE1_BLOCKED_SEMANTIC_DEFECT**

Certification stopped on the reproduced defect below. This report does not certify remaining stages. No production code or tests were modified; this is the only artifact created by this review. Nothing was staged, committed, pushed, merged, tagged or deployed.

## Blocking finding — preserve known like-mode comparison limitations

**P2, certification-blocking: the new disclosure omits the recorded global-fallback limitation while displaying a strong operating-context match.**

Locations:

- `backend/app/services/relationship_observation_projection.py:71`: operating context selects only `status`, `baseline_mode`, `recent_mode`, `match`, `confidence`. The projection does not retain `relationship_graph.edge_basis`, graph comparison limitations, or the recorded mode-conditioned selection status/fallback reason.
- `frontend/src/components/engineering/RelationshipObservations.jsx:47`: the user sees “Operating context match” with `strong`, without the specific known failure to establish sufficient like-mode comparison evidence. The generic disclaimer at line 56 does not disclose that known limitation.

Independent, inexpensive reproduction with 16 controlled rows through the unchanged real engine produced:

```json
{
  "graph_basis": "global_relationship_model",
  "graph_limitations": [
    "Mode-conditioned relationships unavailable: insufficient_recent_mode_rows.",
    "telemetry_classification_did_not_supply_subsystem_labels"
  ],
  "operating_modes_match": "strong",
  "mode_conditioned": {
    "status": "limited",
    "used_global_fallback": true,
    "fallback_reason": "insufficient_recent_mode_rows"
  },
  "disclosure_context": {
    "baseline_mode": "time_band_night_equipment_state_enabled",
    "recent_mode": "time_band_night_equipment_state_enabled",
    "match": "strong",
    "confidence": "limited"
  },
  "disclosure_contains_fallback_reason": false,
  "edges": 3
}
```

The strong field is a general operating-mode match, not proof that exact like-mode historical selection succeeded. The engine deliberately records the separate fallback, and the new observation-only disclosure loses it. This violates the requirement to preserve context limitations while exposing observations. Analytical classification itself was not modified.

Reproduction (read-only controlled engine evaluation; no production/customer telemetry):

```sh
PYTHONPATH=backend:tests .venv/bin/python - <<'PY'
import json
from app.engine.sii_engine import evaluate_sii
from app.services.relationship_observation_projection import relationship_observations
from test_sii_supplied_reference import contract
args = contract(16)
rows = args['comparison_rows']
for row in rows:
    row['pump_status'] = 1
result = evaluate_sii(
    columns=['timestamp', 'flow', 'pressure', 'power', 'pump_status'],
    rows=rows,
    numeric_profiles=[*args['numeric_profiles'], {
        'column': 'pump_status', 'constant_or_stuck': True,
        'missing_count': 0, 'non_numeric_count': 0,
    }],
    timestamp_column='timestamp',
    config={'numeric_columns': ['flow', 'pressure', 'power', 'pump_status']},
)
conditioned = result['operating_modes']['mode_conditioned_baseline']
projected = relationship_observations(result)
assert conditioned['used_global_fallback'] is True
assert conditioned['fallback_reason'] == 'insufficient_recent_mode_rows'
assert result['relationship_graph']['edge_basis'] == 'global_relationship_model'
assert projected['observations'][0]['operating_context']['match'] == 'strong'
assert 'insufficient_recent_mode_rows' not in json.dumps(projected)
print('Reproduced: known like-mode limitation absent from disclosure.')
PY
```

Required correction, in a separate implementation turn:

1. Preserve the existing comparison basis and safe, recorded mode-conditioned status/fallback information in the bounded observation projection.
2. Show the known comparability limitation adjacent to the relationship context, so a general `strong` match cannot stand in for successful like-mode selection. Do not change matching, selection, classification, promotion or persistence.
3. Do not blindly forward arbitrary graph limitations or fallback strings: module-failure paths can contain exception text. Use an explicit customer-safe mapping/allowlist for recorded limitation codes and a safe unknown/unavailable representation.
4. Add a focused real-engine regression for strong general match plus failed like-mode qualification, covering both upload and connector disclosure and its UI. Include historical absence behavior and unsafe exception-string exclusion.

The current D fixture supplies `weak` directly (`tests/presentation_phase1_cases.py:22`) and replaces the edge's operating context. It does not exercise this independent strong-match/fallback combination. The A–D artifact therefore cannot establish complete context-limitation preservation.

## Baseline and worktree

- Branch: `fix/deterministic-governed-output`.
- HEAD: `1bc6d9e031264991ce9cc7ea6bee2ac51b070626`.
- Local origin tracking ref: same HEAD.
- Live `git ls-remote origin refs/heads/fix/deterministic-governed-output`: same HEAD.
- Staged paths: none.
- Six modified tracked paths, identified below.
- Twelve untracked candidate paths at review start. Other 9,410 untracked files were not assumed to belong to this candidate and are excluded.
- No Presentation Phase 1 commit exists on the current branch after the authoritative baseline.
- All 17 file hashes in `restart-verification.json` matched actual file bytes. This confirms reviewed file identity, not correctness of the earlier conclusions.

## Exact candidate inventory at review start

| Path | Category | State |
|---|---|---|
| `backend/app/services/relationship_observation_projection.py` | PRODUCTION_PRESENTATION | Untracked |
| `backend/app/services/upload_persistence.py` | PRODUCTION_API_PROJECTION | Modified |
| `backend/app/services/telemetry_result_projection.py` | PRODUCTION_API_PROJECTION | Modified |
| `backend/app/routers/data.py` | PRODUCTION_API_PROJECTION | Modified |
| `frontend/src/components/engineering/RelationshipObservations.jsx` | FRONTEND_PRESENTATION | Untracked |
| `frontend/src/components/EngineeringReasoningWorkspace.jsx` | FRONTEND_PRESENTATION | Modified |
| `frontend/src/styles/evidence-dashboard.css` | FRONTEND_PRESENTATION | Modified |
| `tests/test_presentation_phase1.py` | TEST | Untracked |
| `tests/presentation_phase1_cases.py` | TEST | Untracked |
| `tests/fixtures/presentation_phase1_invariants.json` | TEST | Untracked |
| `frontend/src/components/engineering/RelationshipObservations.test.js` | TEST | Untracked |
| `frontend/src/components/EngineeringReasoningWorkspace.test.js` | TEST | Modified |
| `frontend/tests/fixtures/presentation-phase1.json` | TEST | Untracked |
| `frontend/tests/e2e/presentation-phase1.spec.js` | E2E_TEST | Untracked |
| `docs/reviews/presentation-phase1/README.md` | REVIEW_EVIDENCE | Untracked |
| `docs/reviews/presentation-phase1/cases.json` | REVIEW_EVIDENCE | Untracked |
| `docs/reviews/presentation-phase1/baseline-verification.json` | REVIEW_EVIDENCE | Untracked |
| `docs/reviews/presentation-phase1/restart-verification.json` | REVIEW_EVIDENCE | Untracked |

This review adds only `docs/reviews/presentation-phase1/final-adversarial-review.md`, category REVIEW_EVIDENCE. No candidate path falls outside the requested categories. Unrelated validation artifacts are excluded, not certified for inclusion.

## Production diff and analytical byte/AST review

Every tracked production hunk and both new production source files were inspected. The tracked edits insert the shared disclosure into compact upload hydration, two explicit analysis routes, connector product projection, and the system-level frontend; CSS is scoped to the new disclosure.

204 tracked files under `backend/app/engine`, `services`, `routers`, `core`, and `models` were byte-compared to HEAD. Only the three expected backend projection/API files differed. AST comparisons identified exactly four changed functions:

- `baseline_comparison_analysis_by_id`
- `comparison_analysis_by_id`
- `build_canonical_result_projection`
- `project_result_for_transport`

**Analytical mathematics did not change.** No threshold, equation, reducer, temporal/recurrence/directional logic, context matcher or feature selector, reference-window builder, empirical threshold, eligibility, signal/pair coverage, ranking, primary selection, finding classification, consequence qualification, or admission implementation changed. No control/actuation or authentication/authorization enforcement implementation changed. E2E cookie handling is test-local, not a production authentication change.

## Remaining stage disposition

- **Presentation semantics:** blocking context-limitation loss reproduced. The code otherwise displays observation, temporal support, recurrence and edge-promotion fields separately; this is not a full semantic certification.
- **Disclosure bounds/selection:** helper uses first 12 source-list entries and a 48 KiB UTF-8 serialized bound, dropping whole trailing observations and updating counts. These are projection-only operations, not analytical ranking or coverage changes. UI explains bounded disclosure. No further bounds tests were run after certification stopped.
- **Physical magnitude:** no new pre-consequence calculation or physical-magnitude field. Correlation labels are unitless. Existing qualification implementation is byte-identical; deferral remains appropriate.
- **API/retrieval:** compact upload, explicit/scoped upload retrieval, and connector projection all call the same helper. The reproduced omission therefore exists across these families; it is not isolated to one route. Existing scope checks precede the additions.
- **Security/provenance:** structural allowlisting excludes arbitrary nested runtime/credential/error objects. The missing comparison basis/limitation weakens interpretation of provenance. No direct leakage found in inspected additions; exhaustive security certification stopped. Correction must not expose raw exception-based fallback reasons.
- **Determinism/replay:** fixed allowlist order, retained source-list order and no new clock/process/retry input in the helper. No new canonical analytical state. Prior fresh-process claims were not treated as a pass for this review; no fresh-process suite was rerun after the defect.
- **Backward compatibility:** absent graph `edges` produces no new disclosure; missing scalar values remain absent/unknown. No migration or stored analytical rewrite is introduced by the reviewed hunks. Full compatibility certification stopped.
- **UI/UX:** static inspection confirms collapsed native details, observation wording, bounded list and scoped wrapping styles. Context wording fails the recorded-fallback case. No independent browser/visual/mobile certification was completed after stopping.
- **Test adequacy:** inspected tests cover non-promotion, supplied weak context, positive recurrence, sequences, counts, allowlist canaries, transports, retained digests and A/B browser cases. Actual ranking is primarily protected by source immutability and fixture equality; the tests do not comprehensively exercise selection. The concrete strong-match/like-mode-fallback case is missing and permits this defect.
- **Before/after:** case builder uses controlled engine/classifier/consequence contracts; A omits a finding, B supplies insufficient samples, C explicitly supplies persistence, and D injects weak context. These remain scoped controlled examples, not proof of production handoff or full context preservation. Complete case replay certification was stopped after finding the defect.
- **Diff hygiene:** `git diff --check` passed. No unrelated production refactor, analytical formatting, dependency edit or temporary instrumentation found in the diff. No broad campaign or benchmark was run.

## Proposed commit set / subject

None: the candidate has not passed. The inventory above is a review inventory, not an approved staging allowlist. No commit subject is recommended until the correction is reviewed.

## Next action

Return to a separately authorized implementation turn for the narrow presentation correction and regression coverage above, then repeat certification of the corrected candidate. Do not commit this candidate as-is.
