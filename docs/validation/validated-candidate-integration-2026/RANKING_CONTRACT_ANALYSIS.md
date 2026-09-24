# Relationship ranking contract analysis

Decision: **UNRESOLVED_HUMAN_DECISION_REQUIRED**.

Scope: read-only architectural review of SOURCE `/home/ubuntu/Neraium-current-integration` and TARGET `/home/ubuntu/Neraium-1.0`. No integration, production edits, broad tests, complete-upload gate or performance workloads. References below are repository-relative; SOURCE/TARGET prefixes disambiguate differing files. Prior reconciliation reports remain unchanged.

## What is established, and what is not

The two implementations are not semantically equivalent. Target's stable-ID tie-break changes the selected primary, evidence references and governed condition content. Supplied order is explicitly protected by the SOURCE candidate's port scope and regression, not merely an accidental implementation detail in that candidate. TARGET's methodology explicitly characterizes that same order dependence as a defect and chooses ascending identity. Neither document is a cross-repository architectural adjudication. The shared mathematical/governance specifications do not resolve the exact-tie policy.

The product principles prohibit inferring stronger analytical evidence from a lexical identifier. They also do not independently establish that first input position signifies stronger evidence. Both can be deterministic for their declared inputs; deciding whether the input sequence is semantically ordered is the missing authority. A reproducible implementation or a passing test does not answer that question.

## Complete relevant production path in both repositories

| Stage | Code / observed behavior | Difference or downstream consequence |
|---|---|---|
| Input normalization | `engine/sii_inputs.py::normalize_rows`; engine preparation and telemetry classification | SOURCE copies mapping insertion order; TARGET uses explicit schema plus sorted extra keys. Neither sorts chronological rows. Schema order can affect eligible column enumeration; this is separate from the condition tie policy. |
| Candidate generation | `services/relationship_baselines.py::build_relationship_baseline`, `_select_numeric_columns_for_relationships` | Byte-identical in both. Eligible columns retain source/schema order, with existing cap/sampling. Nested left/right pair enumeration preserves that order. |
| Numerical evidence | Same builder, `_confidence_score`, `score_relationship_importance` | Pairwise-complete Pearson correlations, paired counts, deltas, strength, confidence and importance; existing thresholds/rounding. Same formulas and selected pairs in both for identical normalized input. No ID contributes to numerical evidence. |
| Initial ranking/selection | `relationship_baselines.py:701–702` | Candidates descending `(importance, correlation_delta, coupling_strength)`; graph edges descending `(importance, abs(delta), baseline_strength)`. Python stable sorts; top five candidates returned. Target has NOT converted these earlier sorts to stable-ID ties. |
| Engine analysis | `engine/sii_engine.py::evaluate_sii`; `engine/sii/mode_conditioned_baseline.py`; `engine/sii/relationship_graph.py` | Like-mode selection can supply graph inputs; graph analysis, temporal persistence and recurrence are evaluated upstream of governed conditions. #2 optimizes feature extraction, not rank authority. |
| Insight path | `services/analysis_explanations.py::build_insights`, `relationship_importance_sort_key`, `cluster_relationship_changes` | Both sort descending `(importance, abs(delta), confidence)` and use `group[0]`. Top three groups, meaningful sequence retained. Target's condition tie fix does not change this separate insight primary policy. |
| Condition inputs | `services/analysis_result_contract.py::build_analysis_result`; `condition_corroboration.py::build_conditions` | Existing changed relationships feed `_normalize_relationship` in supplied order. SOURCE missing ID is `relationship-{index}`; TARGET missing ID is a canonical-content hash. Explicit IDs are retained. |
| Group selection | `condition_corroboration.py::_coherent_groups` | SOURCE uses maximum three-component rank; TARGET minimum negated rank plus ID. Both group related same-orientation evidence. Target also sorts candidate indices. Group membership rules are unchanged, but seed/order and primary can differ. |
| Primary | `build_conditions`, `_corroboration_result` | SOURCE maximum numeric tuple, preserving supplied tied sequence in the tested path. TARGET minimum `(-importance,-abs(delta),-confidence,id)`; lexical ascending ID wins. This is not a new numerical score, but it does select a different analytical representative. |
| Condition classification | `_condition_classification`, `_matching_finding` | Existing explicit finding classification may take precedence; otherwise primary sample sizes/confidence/delta feed classification. Equal ranking keys do not imply equal sample counts or all qualification evidence. Therefore broader equivalence is not established. |
| Comparable operation | `build_conditions` → `historical_comparables.ComparableHistoricalEpisodeService.retrieve` | Uses the primary's columns to retrieve pair-specific comparable evidence. A different primary can select a different comparable history; this is not a label-only operation. |
| Confidence/escalation | `_condition_confidence`, `evaluate_condition_escalation` | Comparable history is an input. No changed result is asserted for all ties, but selection can flow into qualification/confidence without any formula change. |
| Governed narrative/evidence | `_condition_evidence`, `_condition_headline`, `_condition_change_summary`, `_condition_source_time_ranges` | Primary changes source signal references, `title_evidence_relationship_id`, primary evidence roles, leading relationship summaries and source bounds. A generic title or shared-signal summary can remain equal while evidence differs. |
| Output condition order | Final `build_conditions` sort | Descending corroboration strength, confidence and relationship count remains the same; ties at this outer level still preserve preceding order. No whole-product stable-ID ranking contract exists in TARGET. |
| Persistence / recurrence | `relationship_graph.py`, temporal persistence/recurrence services; `change_trajectory.py` | Upstream edge-state mathematics is byte-identical and does not consume the later condition primary. No direct feedback from the selected condition primary to the already-computed graph state was found. Condition-level trajectory aggregates support; primary choice can still affect its presented context. Do not confuse graph equality with whole-governed-output equality. |
| Measurable Consequence | `services/measurable_consequence.py::build_measurable_consequence`, `attach_measurable_consequences` | Implementation is byte-identical. Uses finding identity, source relationship IDs, finding-owned time window, persistence and comparable context; requires exactly one eligible mapped rate series. Primary is not a standalone formula argument, but context/ownership/evidence can differ upstream. The tiny tied fixture does not prove a quantity change, nor universal equality. |
| Evidence Package v1 | `services/evidence_package.py::_relationship`, `_finding`, builder | Distinct path: `_relationship` chooses the first eligible baseline/relationship/model candidate; it does NOT directly read the condition's `title_evidence_relationship_id`. `_finding` can read the first governed condition. Do not claim every package primary changes because the condition primary changed. Package narrative/provenance may reflect that condition. Fingerprint/similarity consumers treat a changed package primary pair as meaningful. |
| Provenance | `analysis_result_contract` evidence construction; `analysis_provenance.result_digest`; evidence packages | Ordered condition evidence is semantic. Changed condition contents change governed digests; SOURCE content-addressed evidence references can change where the payload includes the altered selection. Canonical package/evidence IDs have their own contracts. |
| Replay | `telemetry_result_artifact`, `telemetry_result_service`, replay routes and persisted upload results | Immutable stored results are decoded/projected, not reranked on read. A different newly computed primary changes the artifact content/hash; historical artifacts must remain exact. Regenerating new content is not equivalent to replaying the old decision. |

Paths in this table are under `backend/app/` unless otherwise stated. `relationship_baselines.py`, `relationship_graph.py`, `measurable_consequence.py`, `evidence_package.py`, `telemetry_analysis_window.py`, `telemetry_analysis_service.py`, `telemetry_result_service.py` and `behavioral_model_store.py` were directly compared and are byte-identical across the two worktrees.

## Exact tied fixture and small diagnostic

The diagnostic calls existing `ConditionCorroborationService.build_conditions` with the SOURCE regression's five-link fixture, using the existing `tests/test_condition_intelligence.py::relationship` and `historical_rows` helpers in each repository. No engine/upload/performance run is involved. Fixed `generated_at='2040-01-01T00:00:00Z'`; empty findings, data quality and operating mode; timestamp column `timestamp`. Bytecode disabled and runtime paths isolated under `/tmp/neraium-contract-review/`.

Relationships: r0=(a,b), r1=(b,c), r2=(c,d), r3=(d,e), r4=(e,a). Every relationship has importance absent (rank fallback 0.0), confidence 0.9, delta 0.68, baseline strength 0.88, current strength 0.2, baseline samples 48, recent samples 16, `change_type=weakened`, `system=Pumping System`, and the source window `2026-07-01T00:00:00Z to 2026-07-02T00:00:00Z`. These are exact ties on every key used by SOURCE's condition rank. Identity is not analytical evidence.

| Repository | Supplied order | Exact ranking keys | Primary |
|---|---|---|---|
| SOURCE | r0,r1,r2,r3,r4 | `(0.0,0.68,0.9)` for every item | r0 |
| SOURCE | r4,r3,r2,r1,r0 | `(0.0,0.68,0.9)` for every item | r4 |
| TARGET | r0,r1,r2,r3,r4 | `(-0.0,-0.68,-0.9,id)` | r0 |
| TARGET | r4,r3,r2,r1,r0 | `(-0.0,-0.68,-0.9,id)` | r0 |

The reversed input is the exact same ordered input and evidence on both sides. SOURCE's first primary evidence reference is `[r4]`; TARGET's is `[r0]`. SOURCE support order is r4→r0; TARGET support order is r0→r4. Both retain the generic title “Pumping System relationship weakening” and the same shared-signal summary in this fixture. That equality does not erase the differing primary and evidence.

Diagnostic condition digests (each using its repository’s semantic function; forward outputs happen to agree):

- SOURCE, order r0,r1,r2,r3,r4: `5368c4d0642d4a9f4a0fa7cef28079cfd2674c7542b1874fd2ecc063380ef06e`.
- SOURCE, order r4,r3,r2,r1,r0: `41181054e148d4d7e57a7b7e325ccf86783edb9450a290ad37a179f17911d49e`.
- TARGET, order r0,r1,r2,r3,r4: `5368c4d0642d4a9f4a0fa7cef28079cfd2674c7542b1874fd2ecc063380ef06e`.
- TARGET, order r4,r3,r2,r1,r0: `5368c4d0642d4a9f4a0fa7cef28079cfd2674c7542b1874fd2ecc063380ef06e`.

The previous reconciliation's smaller pure-rank witness `[r2,r1]` at `(importance=1,delta=0.2,confidence=0.8)` independently selected SOURCE r2 and TARGET r1. This review additionally exercises real condition construction rather than assuming `max/min` determines downstream outputs.

## Git history and stated intent

- Common ancestor: `97d267d317fcce4b4424cf2141e97e87680acfc0`. TARGET HEAD `a4ea0a992841d281e19de8119ecd1275a0d7e654` adds wastewater validation documents/scripts, not these production rules.
- `git blame HEAD` attributes `_relationship_rank` and its three numerical fields to `1a7132e97fef5b4c134b1a74d0f1a2c70aa6050f`, “Add corroborated condition intelligence and trajectory analysis.” That historical implementation establishes behavior, not a documented universal philosophical rationale for ties.
- SOURCE's current explicit intent is in `docs/validation/current-product-integration/PORT_SCOPE.md:7`: lexical ordering only for semantically unordered shared signals; preserve rank/ties. `tests/test_governed_output_determinism.py:100` expressly requires the first supplied tied relationship. Therefore supplied-order preservation is explicitly contractual for this validated candidate, not merely inferred from stable sort.
- TARGET's stable-ID additions are uncommitted worktree changes, not a commit with an independently approved architecture decision. Its retained `docs/validation/lbnl-determinism-v2/METHODOLOGY.md:32` says tie dependence on incidental input order was remediated with ascending stable identity. It describes a determinism/provenance remediation, not performance optimization or fault-label tuning.
- TARGET calls this a representation correction and says numerical criteria are unchanged. Inspection confirms unchanged numeric scores but disproves the stronger implication that primary-selection meaning is unchanged.
- Shared `docs/sii_math_specification.md` documents source-order candidate limits and numerical importance, but provides no exact condition-tie mandate. `docs/EVIDENCE_GOVERNANCE_FOUNDATION_V1.md` distinguishes sorted sets from declared-order sequences; it does not classify the condition-input relationship list as an unordered set. `docs/EVIDENCE_PACKAGE_V1.md` describes a different ordered evidence/package contract, not this tie-break.
- SOURCE `FINAL_STATUS.md`, `INTEGRATION_REPORT.md`, `CHANGE_CLASSIFICATION.md`, and Aletheia retirement `CHANGE_SCOPE.md` explicitly preserve rank/ties. TARGET methodology explicitly contradicts that preservation decision. Chronology is not used to adjudicate them.

## Retained validation — exact scope

| Retained campaign | What it validates | What it does not establish |
|---|---|---|
| SOURCE current-product integration | `raw/repair-focused-tests.xml`: 62 cases, no failures; includes `test_shared_signals_and_truncated_summary_preserve_ranked_selection`. The same test also appears passing in `repair-compatibility-tests.xml`. | No independent product-owner adjudication of target's competing policy. |
| SOURCE #5 targeted work | `optimization-05-normalized-telemetry-metadata-2026/raw/targeted-tests.xml`: 38 cases, no failures; metadata/provenance/projection coverage. | No dedicated relationship tie test in this campaign. |
| SOURCE #5 complete 10K gate | Retained single `test_complete_10000_upload_repeat` and unchanged semantic comparator compare complete outputs and analytical components against prior candidates. Retained top candidates have keys `(63.6405,0.507041,0.8866)` and `(55.0399,0.506411,0.8863)`. | These are not tied; the gate did not discriminate the two exact-tie policies. |
| SOURCE #5 three measured 500K runs | Retained complete output/semantic gates passed for the supplied-order implementation; production manifests retain the same condition code. Each retained output's two top candidates have keys `(63.7617,0.511167,0.8885)` and `(55.1432,0.510681,0.8883)`. | No exact condition-ranking tie among those candidates. The 121.610119-second evidence cannot be cited as a direct exact-tie experiment. No performance was rerun. |
| TARGET prior reconciliation diagnostics | `target-contract-tests.xml`: 3 passing tests, including all permutations in `test_condition_permutations_and_runtime_times`. This establishes its declared fixture-level invariance. | Does not establish intended global ranking semantics or arbitrary full-product equivalence. |
| TARGET LBNL v1 | Retained `lbnl-blind-2026/VALIDATION_REPORT.md:130`: 720/720 normalized graphs, only 5/720 predefined normalized full governed results. | Not validation of the later stable-ID remediation; graphs and governed outputs are distinct. |
| TARGET LBNL v2 | Eight files found: methodology, protocol, units, freeze/adapter/codec/runner/comparator scripts. Protocol requests 720/720 and explicitly proposes the target contract. | No completed result, frozen output campaign, comparison report or JUnit was found in that directory. A prospective acceptance criterion is not a passing campaign. |

Reading retained 500K/LBNL artifacts here does not execute either workload. The source manifest lineage supports continuity of the supplied-order implementation through #5; its dedicated earlier unit test supplies the tie-specific evidence.

## Relevant contract/test inventory

Direct conflict: SOURCE `tests/test_governed_output_determinism.py::test_shared_signals_and_truncated_summary_preserve_ranked_selection`; TARGET same file `test_condition_permutations_and_runtime_times`, `test_fresh_process_sequences_match`. Only the former target test has the prior passing diagnostic cited above; the latter test's existence is not reported as a newly verified pass.

Supporting paths inspected: `tests/test_condition_intelligence.py` (grouping, title evidence, condition evidence, confidence/escalation, comparable history, persisted primary object); `tests/test_relationship_importance_quality.py` (context down-ranking and relationship primacy); `tests/test_analysis_result_contract.py`; `tests/test_sii_engine_v2.py`; `tests/test_relationship_temporal_persistence.py`; `tests/test_relationship_recurrence.py`; `tests/test_measurable_consequence.py`; `tests/test_consequence_certification.py`; `tests/test_telemetry_result_artifact.py`; `tests/test_evidence_package_v1.py`; `tests/test_evidence_package_fingerprinting_v1.py`; `tests/test_evidence_package_approximate_similarity_v1.py::test_different_primary_pair_is_excluded_without_partial_score`; `tests/test_evidence_package_historical_pattern_v1.py::test_approximate_ranking_uses_score_then_earliest_time`; replay tests and `docs/REPLAY_VERIFICATION_FIXTURE.md`. These exercise distinct downstream contracts, not a universal condition-tie policy. No broad suite was run.

## Decision and exact human question

**UNRESOLVED_HUMAN_DECISION_REQUIRED**. Not EITHER_IS_SEMANTICALLY_EQUIVALENT: governed evidence already differs.

Does the list supplied to condition corroboration carry semantic priority under equal `(importance, abs(delta), confidence)`, or is an exact-tie group an unordered evidence equivalence class? If it is unordered, may a lexical ID choose the primary used for comparable retrieval/classification, or must all tied evidence remain co-primary with an explicitly non-analytical display representative? The latter would be a new design, not an already implemented option authorized by this review.

A decision must cover consistency with initial top-five selection, insight primaries and package primaries, not silently change only one consumer. Stable IDs have no demonstrated authority to promote analytical strength; a purely presentation sort would have to leave primary-dependent calculations, evidence order contracts and persisted records unchanged. The current target implementation does not meet that presentation-only description.

No authoritative merged ranking key or exact tie rule is issued until this question is resolved. Both current implementations and their historical results must remain intact meanwhile.

## Human authority addendum — 2026-09-24

The previous UNRESOLVED conclusion is superseded prospectively by the user-supplied architecture decisions. See [current decision](ARCHITECTURAL_DECISION.md). All preceding investigation and retained evidence remain historical and unchanged.
