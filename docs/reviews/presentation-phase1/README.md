# Neraium Presentation Phase 1 candidate

Current correction decision: **PRESENTATION_PHASE1_SECOND_CORRECTION_READY_FOR_CERTIFICATION**

Review history: the initial candidate concluded **PRESENTATION_PHASE1_READY_FOR_REVIEW**. The [adversarial review](final-adversarial-review.md) subsequently blocked certification for a missing like-mode/global-fallback qualification. That review is preserved unchanged. The narrow correction and its independent baseline comparison are recorded in [context-qualification-correction.md](context-qualification-correction.md). The subsequent [final certification](final-certification.md) independently found a second omission: the engine’s safe graph-failure comparison basis was dropped. That blocked report is preserved unchanged. The [second correction](second-context-qualification-correction.md) records its reproduction, narrow fix and validation. Certification remains a separate next step.

Baseline: `fix/deterministic-governed-output`, `1bc6d9e031264991ce9cc7ea6bee2ac51b070626`.
On restart, HEAD and branch matched the requested baseline, but the actual workspace contained six modified tracked files plus candidate source/test/review artifacts. These were preserved and treated as unverified: the full evidence trace, clean-HEAD analytical comparison, focused tests, build, browser checks and diff review were repeated. Prior completion claims were not used as verification. Pre-existing unrelated untracked validation files were preserved. No commit, push, merge, tag, or deployment was performed. See `restart-verification.json` for the fresh results and file hashes.

## Evidence path and suppression

1. `engine/sii/relationship_graph.py` retains enriched `edges`, `eligible_edges`, promoted `changed_edges`, recurrence evidence, temporal evidence, windows and source anchors. Edge promotion can occur for abrupt single-window change without temporal persistence; neither is equivalent to a governed persistent finding.
2. `engine/relationship_change.py` and `relationship_recurrence.py` own their existing reducers. `services/analysis_explanations.py` ranks relationship changes by recorded importance, displacement and confidence, and takes the existing first relationship as primary. Finding qualification separately uses existing persistence and context contracts.
3. `services/analysis_result_contract.py` bounds `sii_evidence.relationship_changes` to promoted changed edges and `relationship_recurrences` to supported recurrences. These projections do not carry all evaluated observations. The new implementation does not change that canonical contract.
4. `upload_state_repository.py` retains the authoritative terminal result and compatibility mirrors. `baseline_analysis_repository.py` resolves stored comparison results under the existing scope. Connector execution is retained in its immutable canonical artifact; `telemetry_result_service.py` verifies identity/lineage before projection. None of these storage or verification implementations changed.
5. Compact upload hydration uses `upload_persistence.project_result_for_transport`, which removes raw SII. Explicit comparison retrieval instead returns through two routes in `routers/data.py`. Connector retrieval uses `telemetry_result_projection.build_canonical_result_projection`. All three transport paths now derive the same optional disclosure from the retained graph. Compatibility transport mirrors may cache the derived disclosure; canonical analysis, source evidence, digests and immutable artifacts are unchanged.
6. `EngineeringReasoningWorkspace` consumes an explicitly selected upload/connector result. The system-level System Status, Analysis Findings and Evidence & Outcomes views now offer collapsed **Show relationship evidence** even without finding cards or with insufficient evidence. The disclosure is not inserted into finding-scoped or subsystem-scoped views, preventing system observations from acquiring false finding ownership.

Before this candidate, raw graph evidence could sometimes be inspected through connector technical channels or stored audit evidence. The new disclosure makes bounded observations consistently reachable from system views; it does not claim that all such evidence was absent from every forensic surface.

## Implemented contract

`relationship-observations.v1` is transport-only and has `authority: observation_only`.

- At most the first 12 retained edges in existing engine order, not a new ranking. A 48 KiB serialized UTF-8 bound drops whole trailing observations and reports omissions. This fits within the connector's existing shared-envelope reserve.
- Counts cover **retained evaluated graph edges**, not every possible signal pair or upstream candidates. Eligible, temporally supported and promoted changed-edge counts use existing booleans. Missing historical booleans yield unknown counts, not invented zeroes.
- Per-edge evidence: recorded/single-window change, unitless baseline/current/signed correlation, eligibility, edge promotion, sample counts/support factor, confidence/quality factors, temporal status/counts/direction/agreement, persistent relationship flag, recurrence support/episodes/veto, operating-context match/status and operator-primary eligibility.
- These dimensions are independent. Stable single-window classification can coexist with directional temporal support. Abrupt graph promotion can coexist with unconfirmed temporal persistence. Recurrence is not promoted to continuous persistence.
- Provenance remains tied to the containing result identity, exact engine source path, relationship/reference identifiers, baseline/current source windows, and existing supporting-window dataset/row anchors. No arbitrary nested object or generic JSON dump is exposed.
- Lists retain semantic source order; mappings use fixed allowlist order. Serialized size uses sorted JSON keys and compact separators. No clock, process, retry, worker or request state is consulted. There is no new canonical state or analytical identity version.
- Historical results without retained `edges` receive no disclosure. Historical missing fields display “Not recorded.” Retrieval does not rerun analysis or reconstruct temporal history.

The compact brief, finding count, primary relationship, ranking, dashboard consequence rendering and assessment remain unchanged. The disclosure explicitly states that graph promotion does not establish a persistent finding. It displays recorded support and limitations without diagnosing the failed promotion gate where no recorded gate reason exists.

## Physical magnitude and deferred work

`expected_behavior.py` already retains expected/observed values, normalized residuals, source-model relationships and aligned observations. This is useful model evidence, but not a separate governed relationship-owned physical-magnitude contract. `measurable_consequence.py` requires persistence, comparable context, exact finding ownership/window, explicit resource units, aligned observations and acquisition-gap policy before quantification. Its early refusal paths do not produce a qualifying aggregate physical magnitude.

No pre-consequence physical magnitude is exposed in this phase: selecting, aggregating or relabeling those model values without an established ownership/unit/window contract would introduce new semantics. The displayed correlation is explicitly **unitless**, never impact, loss, savings or quantified consequence. Existing formal consequence qualification/rendering remains unchanged.

All-signal persistence as relationship qualification and production relationship-state handoff remain untouched. Missing historical or production temporal state cannot be recovered by this presentation change. Transient, alternating and recovery sequences are tested through their actual recorded temporal/recurrence fields; no new persistence-state labels are invented. These restrictions need a separately scoped future investigation, not a presentation workaround.

## Retained before/after evidence

`cases.json` records controlled contract data, never customer telemetry. `tests/presentation_phase1_cases.py` generates it using existing graph reducers/classifier and consequence qualification. Finding persistence for the controlled C contract is supplied explicitly; this is not certification of production state handoff.

| Case | Before | After | Unchanged |
|---|---|---|---|
| A: no promoted finding | No finding/primary relationship, no system observation disclosure | Inspect one observed edge and its unconfirmed temporal support | Empty finding/primary selection, no promotion, analytical digest |
| B: insufficient evidence | Insufficient result, no primary relationship | Inspect ineligibility, two current samples and missing temporal support | `insufficient_evidence`, non-persistence, `not_quantifiable`, analytical digest |
| C: persistent promoted finding | Existing promoted relationship and persistent finding contract | Inspect single-window stable change separately from six-window directional persistence and recurrence | `unexplained_systemic_change`, same selected relationship/persistence, `not_quantifiable`, analytical digest |
| D: context-limited | Context-limited governed classification | Inspect recorded weak context and edge evidence | `context_limited_relationship_change`, persistence and consequence status, analytical digest |

The before projection is the existing connector projection with only the new disclosure disabled. Tests compare its analysis and identity byte-for-byte with the after projection. Source analytical digests are retained independently because the pre-existing transport already bounds/omits some stored fields.

`baseline-verification.json` independently compares 16/32/64-row existing synthetic supplied-reference fixtures against an isolated `git archive` of authoritative HEAD. All three full analytical semantic digests and classification arrays match. The corresponding retained assertions are in `tests/fixtures/presentation_phase1_invariants.json`.

Regenerate controlled review artifacts with:

```sh
PYTHONPATH=backend:tests .venv/bin/python tests/presentation_phase1_cases.py
```

## Original candidate verification (before the qualification correction)

- 16 new backend tests pass: non-promotion, insufficient/context-limited results, temporal sequences, both transports, both explicit upload API routes, historical compatibility, source references, bounded selection/bytes, immutable analysis/identity, deterministic map ordering and credential/runtime/forensic/error canaries. The restart added a positive recurrence test proving supported recurrence remains distinct from continuous persistence and promotion.
- 57 existing focused dependency tests pass: SII evidence transport (5), connector projection (7), measurable consequence (21), promotion/read-only architecture (24).
- 3 focused governed determinism tests pass, including six fresh processes with differing hash seeds and input map order.
- 81 focused frontend tests pass across workspace, new disclosure, dashboard, measurable consequence and results presentation. All five suites were rerun during restart verification: 81 pass.
- 2 new Chromium browser tests pass: A desktop, B mobile, default collapse/expansion, stable assessment, no horizontal overflow and no control inputs. Production Vite build passed as part of browser setup. `npm run setup:codex` ran first with locked dependencies.
- Focused ESLint passed for changed JS/JSX components/tests. `git diff --check` passed.
- No broad regression, 10K/500K/1M, LBNL, wastewater campaign or benchmark ran.

During development, one context fixture used a confidence-contract label where the existing classifier expects `weak`; only the fixture was corrected. A size-bound test initially made a single observation exceed the whole budget; its expectation was corrected to exercise partial retention. The browser's shared fixture replaced an issued credential cookie with a public session ID; the new test locally preserves the issued cookie for loopback testing. No application authentication behavior changed.

## Final invariant/diff review

Production changes are limited to one new allowlisted projection helper, calls at presentation/API boundaries, one read-only disclosure component, its workspace insertion and CSS. No engine, reducer, ranking, primary-selection, context matcher, context feature selector, reference window, threshold, admission, signal/pair coverage, consequence qualification, storage identity, control or actuation code changed. New files were inspected in addition to tracked `git diff`.

Next action: review this candidate and the retained cases. No approval action, commit or deployment has been taken.

## File inventory

Production:

- `backend/app/services/relationship_observation_projection.py` (new)
- `backend/app/services/upload_persistence.py`
- `backend/app/services/telemetry_result_projection.py`
- `backend/app/routers/data.py`
- `frontend/src/components/engineering/RelationshipObservations.jsx` (new)
- `frontend/src/components/EngineeringReasoningWorkspace.jsx`
- `frontend/src/styles/evidence-dashboard.css`

Tests and retained review evidence:

- `tests/test_presentation_phase1.py` (new)
- `tests/presentation_phase1_cases.py` (new)
- `tests/fixtures/presentation_phase1_invariants.json` (new)
- `frontend/src/components/engineering/RelationshipObservations.test.js` (new)
- `frontend/src/components/EngineeringReasoningWorkspace.test.js`
- `frontend/tests/e2e/presentation-phase1.spec.js` (new)
- `frontend/tests/fixtures/presentation-phase1.json` (new)
- `docs/reviews/presentation-phase1/README.md` (new)
- `docs/reviews/presentation-phase1/cases.json` (new)
- `docs/reviews/presentation-phase1/baseline-verification.json` (new)

- `docs/reviews/presentation-phase1/restart-verification.json` (new restart audit)
