# Unified SII Phase 2 main-branch audit

## Audit identity and recovery point

- Repository: `Neraium/Neraium-1.0`
- Audited branch: `agent/audit-unified-sii-phase-2`
- Current `main` / Phase 2 commit: `7950e76685b1df54ffbb0184f692da728b85edc0` (`Add unified SII Phase 2 evidence modules`)
- Commit immediately before Phase 2: `4798aa144c262436b47fc4e663eae4c40da9c6e1`
- Recovery ref: remote branch `rollback/pre-sii-phase-2` at `4798aa144c262436b47fc4e663eae4c40da9c6e1`

`main` was not modified or reset. The audit branch was created from `origin/main` at the SHA above.

## Executive result

The upload path has one authoritative SII orchestration call. All Phase 1 and Phase 2 analytical modules are reached through `app.engine.sii_engine.evaluate_sii`; the upload pipeline does not call the temporal, relationship, persistence, multiscale, graph, or runner components directly.

Phase 2 is active as **supporting evidence only**. It is not authoritative for the current user-visible finding count, instability, alert/urgency, operating/review state, severity, or confidence. Canonical `sii_result.findings` remains empty. Therefore this audit does not add an authority feature flag: there is no Phase 2 authority to disable. The result now declares this explicitly through `processing_trace.phase_2_authoritative=false` and `processing_trace.phase_2_effect=supporting_evidence_only`.

The audit did find concrete safety and contract gaps: ambiguous recent modes could be labeled conditioned; adaptive persistence did not adjust its observation requirement for quality, health, mode, sampling, or volatility; its engine window could dilute a change that starts at the Phase 2 active boundary; multiscale horizons did not enforce time coverage or direction consistency and lacked an explicit row fallback; processing trace lacked an exact per-module map; and evidence records discarded Phase 2 supporting sections. The corrective changes are narrow and preserve current alert semantics.

## Unified call path

```text
upload_jobs._build_csv_result
  -> upload_pipeline.run_structural_analysis_pipeline
     -> sii_engine.evaluate_sii exactly once
        -> build_baseline_analysis                         (Phase 1 signal drift)
        -> build_relationship_baseline                     (Phase 1 Pearson relationships)
        -> assess_operating_modes / apply context          (Phase 1 annotation)
        -> build_data_conditions / assess_sensor_health
        -> estimate_empirical_thresholds                   (Phase 2 supporting)
        -> analyze_mode_conditioned_baseline               (Phase 2 supporting)
        -> analyze_relationship_graph                      (Phase 2 supporting)
        -> assess_persistence                              (Phase 1 fixed row support)
        -> evaluate_adaptive_persistence                   (Phase 2 supporting)
        -> evaluate_temporal_math                          (Phase 1 temporal engine)
        -> analyze_multiscale                              (Phase 2 supporting)
        -> run_sii_runner                                  (Phase 1 covariance/Mahalanobis)
        -> canonical neraium_sii/v2 result + compatibility
     -> Phase 1 compatibility presentation
  -> analysis_result / evidence / upload-result persistence
```

Search results over production Python code:

| Symbol | Production definition | Production callers | Upload-pipeline direct caller |
|---|---|---|---|
| `evaluate_sii` | `backend/app/engine/sii_engine.py` | `backend/app/services/upload_pipeline.py` once | Yes, the sole orchestration call |
| `run_sii_analysis` | Absent | None | No |
| `run_sii_runner` | `backend/app/services/sii_runner.py` | `sii_engine.py` once | No |
| `evaluate_temporal_math` | `backend/app/engine/temporal_math.py` | `sii_engine.py` once | No |
| `build_relationship_baseline` | `backend/app/services/relationship_baselines.py` | `sii_engine.py` once | No |
| `assess_persistence` | `backend/app/engine/analysis.py` | legacy analysis function and `sii_engine.py`; upload reaches the engine call only | No |
| `evaluate_adaptive_persistence` | `backend/app/engine/sii/adaptive_persistence.py` | `sii_engine.py` once | No |
| `analyze_multiscale` | `backend/app/engine/sii/multiscale_analysis.py` | `sii_engine.py` once | No |
| `analyze_relationship_graph` | `backend/app/engine/sii/relationship_graph.py` | `sii_engine.py` once | No |

`backend/app/engine/relationships.py` remains legacy code but has no upload-path caller. Tests call individual modules directly for numerical verification; those are not production duplicate evaluations. No silent second SII state is mapped into the upload payload: top-level compatibility fields are taken from `sii_result.compatibility`.

## Canonical output and persistence audit

For sufficient telemetry, the following paths are populated. For insufficient telemetry, each module returns a `status=limited` envelope with a reason, empty collections, and/or an explicit fallback rather than disappearing.

| Requested output | Canonical result path | Evidence-record path |
|---|---|---|
| Relationship graph metrics | `sii_result.relationship_graph` | `phase_2_supporting_evidence.relationship_graph` |
| Changed relationships | `sii_result.relationship_graph.changed_edges` | same nested section |
| Changed components | `sii_result.relationship_graph.connected_changed_components` | same nested section |
| Node disruption | `sii_result.relationship_graph.node_disruption_scores` | same nested section |
| Density / degree / concentration | `sii_result.relationship_graph.graph_density_change`, `.weighted_degree_change`, `.subsystem_concentration` | same nested section |
| Mode-conditioned baseline | `sii_result.operating_modes.mode_conditioned_baseline` and `sii_result.relationship_analysis.mode_conditioned_baseline` | `phase_2_supporting_evidence.mode_conditioned_baseline` |
| Selected operating mode | `...mode_conditioned_baseline.selected_operating_mode` | same nested section |
| Fallback reason | `...mode_conditioned_baseline.fallback_reason` | same nested section |
| Empirical thresholds | `sii_result.data_conditions.empirical_thresholds` | `phase_2_supporting_evidence.empirical_thresholds` |
| Adaptive persistence | `sii_result.persistence_analysis.adaptive_persistence` | `phase_2_supporting_evidence.adaptive_persistence` |
| Required observations | `...adaptive_persistence.required_observations`; per signal under `.details[].required_observations` | same nested section |
| Actual persistence | `...adaptive_persistence.actual_persistence`; per signal under `.details[].actual_persistence` | same nested section |
| Multiscale outputs | `sii_result.multiscale_analysis.scales` and `.agreement` | `phase_2_supporting_evidence.multiscale_analysis` |
| Cross-scale interpretation | `sii_result.multiscale_analysis.cross_scale_interpretation` | same nested section |
| Processing trace | `sii_result.processing_trace` | `phase_2_supporting_evidence.processing_trace` |
| Module failure states | `sii_result.processing_trace.module_statuses`, `.module_failures`; also `sii_result.uncertainty.module_failures` | supporting trace and `.module_failures` |

The complete canonical object remains stored at top-level upload key `sii_result`. Existing `analysis_result` and top-level compatibility fields remain unchanged. Evidence persistence now copies a bounded Phase 2 supporting snapshot rather than the complete global compatibility model, and labels it non-authoritative.

## Effect on live findings and severity

Phase 2 does not affect live severity on this revision.

1. `upload_jobs._build_csv_result` computes per-room drift from early/recent mean and standard-deviation movement. It sets room urgency to `unstable` above `0.25`, `review` above `0.08`, `review` for sparse rooms, otherwise `nominal`.
2. `upload_pipeline.compatibility_context_factory` maps that urgency to compatibility driver severity: `action`, `review`, or `info`.
3. `_build_upload_engine_result` uses only preserved `baseline_analysis.column_drift` and `relationship_model.top_relationship_changes`. It sets `overall_result=elevated` for elevated signals or unstable urgency, `needs_review` for any signal/relationship or review urgency, otherwise `complete`.
4. `build_upload_intelligence` derives urgency, score, state, persistence guard, and confidence from that compatibility engine result, attribution, baseline, and data quality. `evaluate_evidence_guard` blocks strong findings for a weak baseline, poor quality, short fixed persistence, or contradictory compatibility evidence.
5. Top-level `operating_state` and `drift_status` are mapped from the pre-engine `overall_urgency`. The runner's `latest_state.instability_index` is copied separately into `sii_intelligence`.
6. `build_analysis_explanation`, `ConditionCorroborationService.build_conditions`, and `build_analysis_result` consume the compatibility signal/relationship evidence and the resulting conditions. They do not read Phase 2 graph, conditioned mode, adaptive persistence, or multiscale sections.

Consequently, Phase 2 currently cannot:

- create or suppress a compatibility finding;
- increase or decrease current severity;
- replace runner or temporal state;
- change top-level operating/review state, drift status, or frontend status;
- contribute to `analysis_result` confidence.

No second state field or authority flag was introduced. If authority is proposed later, it needs a separate validated design and an explicit conservative rollout; that is outside this Phase 2 audit.

## Empirical learned-threshold status

Classification: **implemented and active as Phase 2 supporting evidence**, not authoritative and not cross-upload learning.

- Fit window: first `floor(0.70*N)` rows only; active rows are excluded.
- Full baseline minimum: 48 rows.
- Per-signal minimum: 24 finite values.
- Signal threshold: `max(q95(|x-median(B)|), 1.4826*MAD(B), max(0.01, 0.05*|median(B)|))`.
- Relationship fit: non-overlapping 12-row baseline windows, Pearson per eligible pair, then q95 of consecutive absolute correlation deltas.
- Relationship minimum: four valid windows; fixed floor `0.25`.
- Insufficient data: fixed threshold retained with an explicit fallback reason.

The learned relationship threshold can only raise the graph promotion threshold. Learned signal thresholds feed adaptive persistence and multiscale comparisons. There is no bootstrap, rolling cross-upload distribution, historical fleet calibration, or probabilistic false-positive calibration. Documentation now says so.

## Mode-conditioned baseline audit

Modes come from deterministic telemetry context in `services/operating_modes.py`: explicit equipment/state signals, inferred active-unit counts, numeric context bands, and timestamp day/night plus weekday/weekend features when available. Numeric band boundaries are computed from combined ordered rows. Phase 2 summarizes the final 30 percent window, then selects only strictly earlier rows that exactly match every explicit selected feature.

Current requirements and fallbacks:

- at least 12 selected historical rows;
- at least 6 recent rows;
- at least 3 pairwise-complete values per Pearson edge;
- every recent explicit feature must support the selected value in at least 70 percent of recent rows;
- no features -> `no_explicit_operating_mode_features`;
- sparse recent mode -> `insufficient_recent_mode_rows`;
- low mode purity -> `ambiguous_recent_operating_mode`;
- sparse like-mode history -> `insufficient_like_mode_historical_rows`;
- fallbacks are limited and confidence is capped at `0.35`, or `0.25` for ambiguity.

Ordering is narrower than the original Phase 2 claim: the preserved global relationship model runs before Phase 2 selection. Mode-conditioned selection then runs before the Phase 2 graph, and the graph consumes conditioned edges when successful. Temporal and covariance execute later but do not consume the conditioned rows. The audit preserves this architecture and documents the limitation.

Synthetic assertions cover a normal transition with no graph change, true drift within the same mode, sparse-mode global fallback, and ambiguous-mode suppression.

## Adaptive persistence audit

Elapsed time is used only when the recent timestamp coverage is at least 90 percent, there are at least three recent rows, a median interval exists, and valid timestamps are strictly increasing. Actual positive intervals are weights; the final sample receives one median interval. Interval regularity is the fraction within 20 percent of the median and is reported separately.

For upload orchestration, the analyzed recent window is the smaller of the Phase 1 recent window and the Phase 2 final-30-percent active window. Direct component calls retain the Phase 1 recent window unless alignment is enabled.

The required observation count starts at 3, is capped at 12, and can only increase:

- irregular sampling: `+1`;
- limited/poor data quality: `+1/+2`;
- limited/poor sensor health: `+1/+2`;
- ambiguous/unavailable operating mode: `+1/+2`;
- moderate/high baseline volatility: `+1/+2`.

A signal is persistent only if supporting observations, the longest consecutive run, weighted support fraction (`>=0.70`), and continuous support duration all pass. Required duration is `max(required_observations*median_interval, 0.70*observed_duration)`. Poor data quality or health can never reduce a requirement. An isolated spike cannot pass the count and accumulation gates.

Without reliable timestamps the module is limited and exposes fixed row support as an observation-count fallback. No duration fields or duration wording are emitted in the fallback. Tests cover regular and irregular cadence, no timestamps, noisy/stable data, a spike, a sustained small change, weak quality, ambiguous mode, and unhealthy sensors.

## Multiscale audit

Elapsed horizons are 15 minutes, 1 hour, 6 hours, and 24 hours. The active window is `(latest-horizon, latest]`; baseline rows are at or before the cutoff. A horizon requires 12 baseline rows, 6 active rows, and an active timestamp span covering at least 80 percent of the horizon.

Signal activation uses the median shift divided by `max(1.4826*MAD(B), 0.05*|median(B)|, 0.01, learned_threshold)`. Activation requires a normalized change of at least `1.0`. Cross-scale agreement needs a consistent direction in `max(2, ceil(0.67*eligible_scales))` scales. Opposing directions are `conflicting_scales`; isolated activity is `transient_or_scale_specific`; a directionally consistent elapsed result is `sustained_across_elapsed_scales`.

When there is no timestamp column, the explicit fallback uses 6-, 12-, and 24-row windows, labels the basis `row_count`, emits no seconds/duration fields, and never claims sustained elapsed-time change. Present but unreliable timestamps remain limited rather than being reinterpreted as time. Runtime defaults are bounded to 8 scales, 64 signal columns, and 16 relationship columns. Each scale is evaluated once; pair calculations are bounded but not cached across scales.

Tests cover short transient, medium change, slow long-term drift, conflicting scales, insufficient coverage, irregular timestamps, and no timestamps. The short transient does not produce a sustained classification.

## Dynamic non-causal graph mathematics

Eligible edges have exactly two metrics, finite baseline/current Pearson values, at least three paired samples in each window, and `operator_primary_eligible=true`. Context-only edges are excluded from eligible graph promotion. The edge health factor is the minimum endpoint factor (`1.0` healthy, `0.65` limited, `0.4` suspect/review, `0.25` severe condition, `0.7` unavailable). It reduces both effective confidence and the data-quality factor.

```text
absolute_delta_e = |r_current,e - r_baseline,e|
edge_confidence_e = raw_confidence_e * sensor_health_factor_e
data_quality_factor_e = global_quality_factor * sensor_health_factor_e
edge_displacement_e = absolute_delta_e * edge_confidence_e * data_quality_factor_e
changed_edge_fraction = promoted_edges / max(eligible_edges, 1)
weighted_edge_displacement = sum(edge_displacement_e) / max(sum(edge_confidence_e), epsilon)
node_disruption_v = sum(changed incident edge displacement)
                    / max(sum(changed incident edge_confidence * data_quality_factor), epsilon)
```

Promotion additionally requires the preserved change-type strength gate, absolute delta at least the learned threshold with fixed floor `0.25`, edge confidence at least `0.45`, and data-quality factor at least `0.35`.

Promoted edges form undirected connected components. Coherence is:

```text
0.20*shared_node + 0.20*compatible_direction + 0.15*time_alignment
+ 0.15*confidence + 0.15*persistence + 0.15*sensor_health
```

A coherent component needs two promoted edges and a score at least `0.62`. Weighted degree is `sum(|r|*edge_confidence)` per node for baseline/current, with current minus baseline reported. Graph density counts eligible edges with `|r|>=0.10` divided by `n(n-1)/2`, again reporting current minus baseline. Subsystem concentration is the maximum same-subsystem changed displacement divided by total changed displacement; `>=0.75` is concentrated, cross-subsystem fraction `>=0.40` or at least three same-subsystem groups is distributed, otherwise mixed.

Subsystems come only from explicit telemetry catalog metadata. Graph edges retain source relationship IDs, pair counts, windows, and source anchors. The graph and component language is explicitly non-causal and never fabricates a root cause. Numerical tests cover stable graph, isolated changed edge, three connected changes, context-only, low-confidence, and unhealthy-sensor cases.

## Failure isolation and processing trace

Every orchestration module has an independent `try/except`. A failed optional module records a failed envelope and does not abort the remaining modules. The trace now includes an exact `module_statuses` map with status/reason plus `module_failures`; failures remain mirrored in `uncertainty.module_failures`. A module is never recorded as complete for an unknown status. Sufficient and sparse canonical integration tests verify populated and limited shapes, and the existing monkeypatch failure tests verify continued execution.

## Deterministic dataset comparison

`finding count` below is the current `analysis_result.conditions` count. Phase 2 canonical findings are zero in every case.

| Dataset | Phase 1 / current compatibility result | Phase 2 supporting result | Top evidence / suppressions | Assessment |
|---|---|---|---|---|
| A. Stable system | 0 findings; `Baseline-aligned`; drift `info`; confidence `high`; 0 relationship changes | 0 graph changes/components; no persistent signals; `stable_across_scales`; exact-mode confidence high | Stable presentation insight: “Operating fingerprint remains stable”; no suppressions | Expected and beneficial; no Phase 2 false positive |
| B. Persistent relationship change | 1 finding; `Persistent structural drift observed`; drift `unstable`; confidence `moderate`; 1 relationship change | 1 changed edge, 1 component; temperature persistence satisfied; `sustained_across_elapsed_scales`; exact-mode confidence high | “Flow & Pressure response weakening”; temperature health is limited, reducing confidence | Expected detection; Phase 2 adds corroborating evidence without changing severity |
| C. Normal operating-mode change | 1 current compatibility finding; `Persistent structural drift observed`; drift `unstable`; confidence `moderate`; 2 global relationship changes | 0 graph changes/components; no persistent signals; `stable_across_scales`; exact-mode confidence high | Current top evidence is a connected Flow/Pressure strengthening; flow health limited | Phase 2 conditioned evidence beneficially suppresses the apparent graph change, but current Phase 1 presentation may still false-positive because Phase 2 is shadow-only |
| D. Sensor fault / stuck signal | 0 findings; `Baseline-aligned`; drift `info`; 0 relationship changes | 0 graph changes/components; no persistent signals; `stable_across_scales`; exact-mode confidence high | Flow health limited; no physical graph claim | Expected conservative behavior; health limitation is retained |

The comparison exposes an intentional rollout limitation: dataset C demonstrates useful Phase 2 false-positive suppression that is not yet applied to live severity. Making it authoritative requires a separately scoped validation effort, not this audit PR.

## Validation record

Validation on the audit branch:

- Focused Phase 1/Phase 2, temporal, runner, graph, pipeline, quality, and robustness group: **90 passed**.
- Upload/evidence regression group before stale-contract correction: **182 passed, 5 failed, 6 deselected**.
- Full backend suite before stale-contract correction: **662 passed, 6 failed, 1 skipped, 20 deselected** (669 selected).
- Six reported contract failures after narrow assertion correction: **27 passed**.
- Frontend lint (`npm run lint:ci`): **passed**.
- Frontend production build (`npm run build`): **passed**.
- Browser smoke (`setup-upload-regression.spec.js`, `responsive-layout.spec.js`): **30 passed** across Chromium, Firefox, and WebKit.
- Final full backend rerun: **668 passed, 1 skipped, 20 deselected** (669 selected; the skipped 1M-row benchmark requires `NERAIUM_RUN_1M_BENCHMARK=1`).

The six reproduced failures and their traced causes were:

| Test | Failure | Trace and disposition |
|---|---|---|
| `test_api_contracts.py::test_openapi_covers_runtime_routes_and_contract_metadata` | expected 109 operations, runtime and schema both expose 111 | Stale exact count; the Phase 2 commit changes no router. Updated to the current 111-operation contract. |
| `test_frontend_upload_auth.py::test_frontend_polling_uses_bounded_backoff_under_failures` | expected superseded 30s/45s formulas | Current bounded helper uses a 15s cap and 1s floor. Updated assertions to the actual helper; Phase 2 changes no frontend file. |
| `...::test_frontend_upload_progress_uses_propagation_fields_with_fallback` | expected old stage copy in the rendering panel | Stage contract moved to `viewModels/uploadFlow.js` (`Import`, `Check`, `Prepare`, `Learn`, evidence). Updated the assertion source and current labels. |
| `...::test_mobile_upload_limit_and_guidance_are_operational_grade` | expected inline 250 MiB constant and obsolete copy | Current workspace imports the shared 512 MiB limit from `uploadApi.js`. Updated the assertion to the shared contract and current guidance. |
| `...::test_frontend_uses_single_data_connections_workspace_for_uploads` | expected navigation label `Data Connections` | Stable workspace ID remains `data-connections`; current product label is `Data`. Updated only the stale label assertion. |
| `...::test_retry_analysis_targets_current_uploaded_job` | expected obsolete initial CTA copy | Retry still targets the current job and renders `Retry Analysis`; current initial CTA is `Start Baseline Analysis`. Updated only the stale copy assertion. |

All six assertions already failed at the pre-Phase-2 recovery SHA or were introduced by commits that are ancestors of it. The Phase 2 commit changes no router, frontend source, `test_api_contracts.py`, or `test_frontend_upload_auth.py` file. No payload, ordering, compatibility, or frontend status change from Phase 2 caused them.

## Component status and known limitations

| Component | Status after audit |
|---|---|
| Unified upload orchestration | Active and authoritative entrypoint |
| Phase 1 compatibility signal/relationship/presentation path | Active and authoritative for current user-visible state |
| Phase 1 temporal and covariance/Mahalanobis modules | Active; separately traceable compatibility evidence |
| Empirical thresholds | Active supporting evidence; within-upload baseline only |
| Exact mode-conditioned baseline | Active supporting evidence; graph consumer only |
| Dynamic relationship graph | Active supporting evidence; explicitly non-causal |
| Adaptive persistence | Active supporting evidence; row fallback limited |
| Multiscale analysis | Active supporting evidence; elapsed or explicitly row-based |
| Phase 2 canonical findings/fusion | Inactive; `findings=[]` |
| Physics priors, causal propagation, Bayesian fusion | Planned Phase 3; inactive |
| Behavioral digital model | Planned Phase 4; inactive |

Known limitations retained deliberately:

- Phase 1 presentation can still report a normal mode transition as drift because it uses the global relationship comparison.
- Mode-conditioned rows do not feed the Phase 1 temporal or covariance modules.
- Adaptive persistence assesses eligible signal drift, not elapsed persistence of each changing relationship edge.
- Empirical thresholds learn within one upload only and are not calibrated probabilities.
- Pearson and all graph summaries are non-causal.
- Row fallback cannot support elapsed-duration claims.
- Multiscale relationship pairs are bounded but recalculated per eligible scale.

No Phase 3 feature, causal model, Bayesian fusion, physics prior, machine-learning model, or architecture rewrite was added.
