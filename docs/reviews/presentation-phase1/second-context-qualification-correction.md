# Second comparison-basis correction

Decision: **PRESENTATION_PHASE1_SECOND_CORRECTION_READY_FOR_CERTIFICATION**

Branch: `fix/deterministic-governed-output`. HEAD and live remote branch remain `1bc6d9e031264991ce9cc7ea6bee2ac51b070626`. Nothing staged, committed, pushed, merged, tagged or deployed.

## Retained history

1. Original candidate: README and original baseline/case/restart artifacts recorded PRESENTATION_PHASE1_READY_FOR_REVIEW.
2. First defect: `final-adversarial-review.md` blocked missing like-mode/global-fallback qualification.
3. First correction: `context-qualification-correction.md` recorded PRESENTATION_PHASE1_CORRECTED_READY_FOR_CERTIFICATION.
4. Independent final certification: `final-certification.md` reproduced a second semantic defect and recorded PRESENTATION_PHASE1_BLOCKED_SEMANTIC_DEFECT.
5. This correction addresses that second omission. Both blocking reports and the first correction report remain unchanged. This is readiness for another independent certification, not a retroactive certification pass.

## Reproduction and authoritative vocabulary

The existing engine emits exactly these graph comparison-basis values:

- `mode_conditioned_relationships` and `global_relationship_model` in `backend/app/engine/sii/relationship_graph.py`.
- `global_relationship_model_failure_fallback` in `backend/app/engine/sii_engine.py`, when dynamic graph analysis is unavailable and the existing global relationship graph is retained.

The projection previously recognized only the first two values. A controlled exception injected at `app.engine.sii_engine.analyze_relationship_graph` exercises the real engine exception handler and canonical graph selection. The unchanged engine returns three global edges with the third basis and retains internal failure diagnostics separately in `phase_2_status`.

`tests/presentation_phase1_graph_fallback_case.py` reproduces this branch with the existing synthetic 64-row supplied-reference contract. An independent check using a saved copy of the pre-correction helper confirmed that it dropped the basis for this exact engine output; the corrected helper retains it.

## Narrow production correction

Only two production files changed in this correction:

- `backend/app/services/relationship_observation_projection.py`: add the single existing safe enum to the explicit comparison-basis allowlist. No arbitrary strings accepted; no diagnostic object copied.
- `frontend/src/components/engineering/RelationshipObservations.jsx`: map it to “Global relationship model” and show “Comparison basis qualification: Dynamic relationship comparison was unavailable for this evaluation.”

The qualification uses the existing neutral fact presentation, with no alarm, severity, diagnosis, data-quality or control-system condition. It does not change the separate like-mode limitation, classification, sufficiency, persistence or promotion. The raw enum is not displayed. No engine, graph failure handling, transport route, dependency or stylesheet changes were needed for this correction.

## Regression and transport coverage

`tests/test_presentation_phase1_graph_fallback.py` tests the actual failure branch, then asserts identical disclosure through compact upload projection, explicit comparison retrieval, scoped baseline comparison retrieval, and connector projection. Retrieval runs with engine execution disabled. Connector lineage fixtures retain their existing verified identity independently of the engine-derived graph/context inserted for transport testing.

Source equality and analytical equality checks preserve classification, primary selection, promotion/persistence/recurrence evidence or its absence, consequence objects and semantic identity. Raw fallback edges do not contain some dynamic evidence fields; the test explicitly preserves absence instead of inventing false values.

The retained `frontend/tests/fixtures/presentation-phase1-graph-fallback.json` contains only safe projected evidence and controlled analytical invariants. Backend tests recompute and compare it. Frontend unit tests and desktop/mobile Chromium checks consume the same fixture, require the safe qualification, verify default collapse and unchanged assessment, and reject raw enums/diagnostics and alert controls.

## Security verification

The controlled exception carries distinct canaries for exception text, module identity, traceback, worker/process/retry identity, internal path, credential, forensic evidence and diagnostics. Tests first establish that the internal failure payload really contains the canary, then verify the new disclosure contains neither any canary nor `RuntimeError`, `phase_2_status`, traceback or the internal path. Equality across all four transports checks the same safe disclosure reaches each route. UI tests also inject an unknown diagnostic object and establish that it is not rendered.

Existing restricted-field and unknown qualification tests passed. Only the safe enum crosses this new disclosure boundary; existing API payloads and security filters were not redesigned. Authorization, workspace/site scopes and read-only behavior are unchanged.

## Analytical invariants

A fresh temporary `git archive HEAD` received only the three controlled case helpers. Independent processes evaluated that baseline and the current candidate. Exact invariant JSON matched for A–D, the first strong-context fallback, and the new graph-failure fallback. The new case retained:

- classification: `context_limited_relationship_change`;
- primary relationship order: `relationship-0`, `relationship-1`;
- finding persistence: false, status limited;
- dynamic edge promotion/persistence/recurrence fields: absent in all three raw fallback edges, unchanged;
- measurable consequence: `not_quantifiable`;
- analytical digest: `d7491d6e048dbcfbe8185d6a81784413bab599ca21d746b466cbffb9c97545b4`;
- graph digest: `ed75209079425cb24bef524b0e2c070f6096ce4496ee34f80a2d82a402c245d1`.

These are before/after comparisons of the same engine failure case, not comparisons of a successful graph evaluation with a failed one. Graph digest includes the retained controlled diagnostic content; it is not newly exposed by the disclosure.

Byte comparison of 242 tracked backend files found only the same three Phase 1 API/projection files different from authoritative HEAD. AST differences remain restricted to the original four retrieval/projection functions. All engine mathematics, dynamic graph behavior, failure handling, reducers, thresholds, temporal/context/reference logic, eligibility, ranking, primary selection, classification, consequence qualification, telemetry admission and control/actuation implementations are unchanged.

## Determinism, compatibility and bounds

The new safe basis is included before the existing 48 KiB byte check. Regression tests force trailing whole-observation truncation, retain the basis, and verify accurate displayed/omitted counts. The limits remain 12 relationships and 48 KiB. Map-order reversal and volatile runtime metadata changes produce identical canonical disclosure bytes.

Absent historical basis stays absent, unknown values remain excluded, and graph absence produces no disclosure. There is no historical inference, analysis rerun, stored-evidence rewrite or migration.

## Validation

- Backend: **37 passed** across the new graph fallback, existing Phase 1 context and general tests, SII transport and connector projection suites.
- Frontend: **36 unique tests passed** (27 workspace and 9 observation tests). The first observation-suite run rejected JSX in its `.js` file; the new test was changed to the existing `React.createElement` convention and all 9 passed on rerun.
- Chromium: **5 passed**: A desktop, B mobile, first fallback mobile, second fallback desktop and mobile. Both new cases show the safe qualification and unchanged brief without horizontal overflow or alerts/control inputs. Production build passed during startup.
- Locked `npm run setup:codex` had already completed in this same environment during the immediately preceding certification; installed locked dependencies were reused.
- Focused ESLint passed after qualifying the existing E2E viewport global as `window.innerWidth`.
- Fresh clean-HEAD analytical invariant comparison passed.
- Pre-correction omission and corrected preservation reproduced independently.
- `git diff --check` passed.

No full regression, large dataset validation, LBNL, wastewater or performance campaign ran.

## Files changed by this correction

- backend/app/services/relationship_observation_projection.py
- frontend/src/components/engineering/RelationshipObservations.jsx
- frontend/src/components/engineering/RelationshipObservations.test.js
- frontend/tests/e2e/presentation-phase1.spec.js
- frontend/tests/fixtures/presentation-phase1-graph-fallback.json (new)
- tests/presentation_phase1_graph_fallback_case.py (new)
- tests/test_presentation_phase1_graph_fallback.py (new)
- docs/reviews/presentation-phase1/README.md
- docs/reviews/presentation-phase1/second-context-qualification-correction.md (new)

## Final diff review and next action

Reviewed the complete tracked candidate diff and new production helper/component, plus the correction tests and controlled fixture. No unrelated production cleanup, analytical change, graph behavior change, security weakening, unsupported semantics, dependency edit, credentials, customer telemetry or debug instrumentation was introduced. The three pre-existing API integration files and other unrelated retained artifacts were preserved.

No known correction blocker remains. Repeat independent certification of the entire corrected candidate before considering a commit. This correction did not stage or commit anything.
