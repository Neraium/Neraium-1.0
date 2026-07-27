# SII Validation Plan

## Purpose

This plan validates the unified SII entrypoint without treating key presence as sufficient. Tests must verify numerical behavior, bounds, suppression, confidence limits, traceability, and safe semantics. Datasets are deterministic and synthetic; expected outcomes are documented beside fixtures.

## Phase 1 acceptance gates

Phase 1 may be reviewed when all of these pass:

1. Upload processing invokes `evaluate_sii` exactly once.
2. The upload pipeline contains no direct temporal, Pearson relationship, or runner invocation.
3. Existing top-level upload fields equal the canonical compatibility views.
4. The temporal engine is present in the upload result and attempted exactly once.
5. Baseline drift, Pearson fields/ranking, operating context, sensor health, fixed persistence, covariance/Mahalanobis, and temporal outputs retain their current formulas and bounds.
6. Sparse or ineligible data returns structured `limited` module objects.
7. An optional-module exception leaves other module results usable and produces overall `limited`, not upload failure.
8. Frontend and evidence-persistence contract tests pass without removing legacy fields.
9. Canonical language and documentation make no root-cause, repair, causal, or exact-failure-time claim.

## Phase 2 acceptance gates

Phase 2 may be reviewed when all of these pass:

1. Phase 1 global signal, Pearson, covariance, temporal, compatibility, and public upload values remain unchanged.
2. Empirical thresholds fit only pre-split baseline rows, never lower fixed evidence floors, and expose exact fallback reasons.
3. Like-mode selection uses only strictly earlier rows that exactly match every available explicit recent-mode feature; insufficient samples never masquerade as a conditioned result.
4. Graph metrics use only eligible, confidence- and quality-gated non-causal edges; changed fractions, node disruption, connected components, degree, density, and subsystem concentration have numerical assertions.
5. Adaptive persistence uses actual positive timestamp intervals, supports irregular cadence without row-to-duration conversion, and exposes fixed row support only as an explicit fallback.
6. Multiscale active windows are lower-exclusive and upper-inclusive, never overlap their baselines, report exact row counts/durations, and leave unsupported horizons `limited`.
7. Every Phase 2 module is attempted exactly once by `evaluate_sii`, isolated on failure, and represented in `processing_trace`.
8. Canonical findings remain empty; graph, mode, persistence, and multiscale language makes no causal, diagnostic, repair, or exact failure-time claim.

## Deterministic scenario matrix

| Scenario | Phase | Dataset construction | Numerical/semantic expectation |
|---|---|---|---|
| Stable correlated system | 1 | Three smooth, strongly correlated signals over ≥90 rows | Pearson edges exist; covariance/temporal scores remain bounded; no canonical finding |
| Persistent relationship weakening | 1 | First 70% near-perfect linear relation; final 30% deterministic independent pattern | Baseline `r>0.99`, active `|r|<0.5`, delta `>0.5`, change weakened/missing, paired counts exact |
| Temporary spike | 1 | Stable history plus one terminal multi-signal spike | Runner persistence and accumulation do not both pass; no Critical urgency; no canonical finding |
| Operating-mode change | 1/2 | Stage/load state changes at comparison boundary while process relationship within each mode is stable | Phase 1 records weak/partial mode match and does not claim failure; Phase 2 must compare like mode |
| Covariance change without mean drift | 1 | Baseline independent centered signals; active centered signals with changed covariance | Covariance shift rises while signal means remain near baseline; Mahalanobis output finite |
| Nonlinear MI dependence | 1 | Baseline `y=x²` with symmetric `x`; active shuffled/different mapping | MI drift changes despite weak Pearson; output in `[0,1]` |
| Lag shift | 1 | Baseline `y` lags `x` by fixed samples; active lag differs | Dominant lag shift has expected sign/magnitude and normalized score |
| Regime change | 1 | Low state drift followed by sustained higher drift | Change points occur only after sufficient series length; regime score bounded |
| Missing data | 1 | Deterministic periodic blanks in different columns | Pair counts fall; runner completeness falls; no NaN/inf escapes result |
| Stuck sensor | 1 | One constant non-state numeric profile | Sensor health marks flatline/stuck and data confidence cannot remain high |
| Irregular timestamps | 1/2 | Alternating sample intervals | Source condition marks irregular sampling; Phase 1 does not convert rows to duration |
| Sparse history | 1 | Fewer than 5 rows or one numeric feature | Drift/relationships/temporal return structured limited results; upload can still complete partially |
| Context-only relationship | 1 | Only load/schedule/environment signals change together | Edge math is retained; importance is down-ranked/capped; no equipment-health claim |
| Cumulative counter | 1 | Named monotonic counter plus operating signals | Raw counter excluded from relationships; nonnegative delta feature used; resets become missing |
| Graph-wide coherent change | 2 | Multiple mutually connected changed edges | Changed component and node disruption metrics match documented formulas |
| Conflicting evidence | 2/3 | Mean drift without relationship/covariance support or inverse combination | Contributions remain separate; fusion exposes suppression/uncertainty |
| Multi-scale agreement | 2 | Sustained drift spanning configured timestamp horizons | Eligible scales agree; counts/durations exact; unsupported horizons limited |
| Learned-threshold fallback | 2 | Baseline below empirical minimum | Fixed threshold retained with explicit fallback reason |
| Behavioral residual change | 4 | Chronological train period follows stable linear model; evaluation residual shifts | Train/evaluation rows do not overlap; normalized residual increases |
| Optional-module failure | 1 | Monkeypatched temporal module raises deterministic exception | Other modules complete; trace identifies only failed module; overall limited |

Phase ownership keeps Phase 1 behavior frozen, activates only the documented Phase 2 scenarios here, and leaves Phase 3–4 behaviors unauthorized until their own review.

## Current automated coverage

### Unified engine and pipeline

- `tests/test_sii_engine_phase_2.py`
  - exact changed-edge fraction, weighted displacement, node disruption, coherent component, and subsystem concentration;
  - exact like-mode historical indices and Pearson pair counts;
  - exact elapsed persistence support and explicit timestamp fallback;
  - exact multiscale row counts, durations, non-overlap, and agreement;
  - baseline-only threshold fitting and fixed-floor fallback;
  - once-only Phase 2 orchestration and compatibility isolation.
- `tests/test_sii_engine_v2.py`
  - canonical Phase 1 schema and engine identity;
  - stable system numerical bounds;
  - preserved Pearson weakening measurements and source anchors;
  - temporary-spike persistence suppression;
  - sparse-history limited results;
  - optional temporal failure isolation.
- `tests/test_sii_pipeline_unification.py`
  - upload invokes the authoritative entrypoint exactly once;
  - temporal and covariance attempts occur once;
  - compatibility values equal legacy public fields;
  - no independent analytical invocation remains in the pipeline.

### Preserved component regression suites

- `tests/test_temporal_math_engine.py`
- `tests/test_temporal_generalization_guardrails.py`
- `tests/test_sii_runner.py`
- `tests/test_sii_robustness_regression.py`
- `tests/test_relationship_importance_quality.py`
- `tests/test_telemetry_integrity_simulations.py`
- `tests/test_telemetry_confidence.py`
- `tests/test_telemetry_classification.py`
- `tests/test_messy_upload_reliability.py`
- `tests/test_data_upload.py`
- `tests/test_analysis_result_contract.py`
- `tests/test_evidence_backed_analysis.py`

## Assertions required for analytical tests

Tests should assert at least one of:

- exact sample counts/window bounds;
- expected direction or ordering;
- a numeric interval or conservative threshold relation;
- a suppression/cap condition;
- finite output and `[0,1]` bound;
- traceability to source row/timestamp anchors;
- semantic exclusion of prohibited claims.

A test that only asserts a key exists is insufficient.

## Comparison protocol

Before each later phase changes production behavior:

1. Freeze Phase 1 deterministic fixtures and serialized summaries for active formulas.
2. Run old and candidate paths on the same ordered rows.
3. Compare signal drift, all Pearson edge values/counts/ranking, operating context, sensor-health ratings, runner components, persistence gates, and temporal components.
4. Any formula change requires an explicit math-spec revision and dedicated expected-value test; no compatibility field may change silently.
5. Compare false-positive suppression on stable, temporary-spike, operating-mode, missing-data, and stuck-sensor scenarios.
6. Review all generated language for diagnosis, repair, causal, or exact-failure-time claims.
7. Activate later-phase behavior only after its own tests pass and reviewers can inspect contribution-level evidence.

## Manual review checklist

- Confirm the frontend still resolves baseline, relationships, graph, intelligence, runner state, and processing trace.
- Confirm evidence records preserve paired sample counts, source rows, evidence windows, data conditions, and timestamps.
- Confirm `processing_trace.modules_*` matches the actual execution path.
- Confirm planned sections say `not_active_in_phase_1` rather than returning false success.
- Confirm legacy `projected_time_to_failure*` aliases display conditional review-window language only; new code uses `review_window*`.
- Confirm no optional failure aborts an otherwise usable upload.

## Commands

Focused unified SII Phase 1 and Phase 2:

```bash
.venv/bin/pytest -q \
  tests/test_sii_engine_phase_2.py \
  tests/test_sii_engine_v2.py \
  tests/test_sii_pipeline_unification.py
```

Preserved analytics and upload integration:

```bash
.venv/bin/pytest -q \
  tests/test_temporal_math_engine.py \
  tests/test_temporal_generalization_guardrails.py \
  tests/test_sii_runner.py \
  tests/test_relationship_importance_quality.py \
  tests/test_messy_upload_reliability.py \
  tests/test_sii_robustness_regression.py \
  tests/test_data_upload.py
```

Repository validation should also run `git diff --check` and the repository's standard validation command when feasible.
