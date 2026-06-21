# SII Robustness Assessment

## 2026-06-14 Reliability Hardening Update

This pass strengthens the upload path and evidence contract beyond the earlier post-fix runner guardrails:

- Data quality now includes `reliability_score`, `reliability_rating`, and structured metrics for rows received/used/dropped, drop ratio, missing numeric rows, invalid numeric rows, stuck sensors, irregular sampling, and baseline reliability.
- Numeric profiles mark constant or stuck sensors.
- Relationship-change evidence now carries real variables, baseline/recent window metrics, source-row anchors, and timestamps.
- Persisted evidence records include source-row anchors, variables, drift metrics, data conditions, and source row counts.
- Upload intelligence now exposes operator-grade fields: what changed, why it matters, review next, supporting evidence, data-quality warning, and reliability rating.
- Confidence is capped when data quality is weak, baselines are sparse, rows are dropped, timestamps are irregular, evidence is absent, or row counts are too low.
- Frontend upload normalization now exposes `supported_sii_claims`, which is true only when SII output is reliable enough to show and evidence persistence succeeded.

New automated coverage:

| Area | Test coverage |
|---|---|
| Messy data | Missing numeric values, duplicate timestamps, unsorted timestamps, invalid timestamps, bad numeric fields, whitespace-delimited uploads |
| Evidence reliability | Persisted evidence includes variables, coupling metrics, source rows, and baseline/recent windows |
| Confidence calibration | Missing data and constant/sparse sensors lower confidence |
| Benchmark matrix | Stable clean, stable noisy/missing, injected drift, relationship collapse, sensor dropout, 10k rows, 100k rows |
| Large upload guard | 1M-row test exists behind `NERAIUM_RUN_1M_BENCHMARK=1` |
| Frontend guard | Unsupported SII claims are not marked supported unless persisted evidence and display reliability are both true |

The historical pre-fix benchmark below remains useful as a failure baseline. Current acceptance should be based on the pytest suite and benchmark targets in `docs/platform_strengthening_plan.md`.

This assessment was originally produced from `docs/sii_math_audit.md` and the then-current codebase to evaluate whether the uploaded-telemetry SII path could handle messy real-world telemetry reliably. It is retained as the pre-fix benchmark that drove the robustness changes below.

## Post-Fix Status (Implemented After Original Benchmark)

The original benchmark below exposed a runner false-positive path where stable cyclic/noisy telemetry could produce `LOCK_IN`/`CRITICAL` through covariance-distance and transition-pressure scoring even while top-level upload state stayed `Baseline-aligned`. The current code now adds these guardrails:

- Covariance scoring requires at least 8 baseline rows and at least 65% baseline completeness.
- Covariance matrices use variance-scaled diagonal regularization: `max(mean_positive_variance * 0.05, 0.001)`.
- Mahalanobis drift is scored as excess over the baseline distance distribution: `max(0, distance - (mean + 3*std)) / max(mean + 3*std, 1.0)`.
- Covariance-only spikes are zeroed when fallback mean drift is `< 0.08` and covariance shift is `< 0.8`.
- Uncorroborated technical scores are capped at `0.19`, below the `TRANSITION` threshold.
- Transition pressure is gated by corroborated drift instead of raw Mahalanobis velocity alone.
- Runner confidence now uses current and recent completeness and caps below `0.90` when missingness is present.
- Per-room drift now compares early-vs-recent mean and variance growth instead of full min/max range.

Post-fix regression checks added in `tests/test_sii_robustness_regression.py` verify:

| Regression | Current result |
|---|---|
| Stable 240-row telemetry | `drift_status=info`, runner `STABLE/NOMINAL`, score `0.053605` |
| Noisy stable 240-row telemetry | `drift_status=info`, runner `STABLE/NOMINAL`, score `0.053763` |
| Missing/null telemetry | runner `STABLE/NOMINAL`; confidence drops from `0.90` to `0.88724` |
| Progressive degradation | `drift_status=review`, runner `UNSTABLE/ALERT`, score `0.682582` |

Validation command: `PYTHONPATH=./backend .venv/bin/pytest -q tests/test_sii_runner.py tests/test_messy_upload_reliability.py tests/test_sii_robustness_regression.py -vv` passed 14/14. A broader backend upload/service run passed 114 selected tests.

Remaining limitation: the full 28-case synthetic benchmark table below has not been fully regenerated after the fixes. Treat its detailed rows as the pre-fix failure baseline, not the current expected behavior.

## Methodology

I ran synthetic CSV uploads through the current backend upload path:

```text
backend/app/services/upload_jobs.py::process_csv_file
  -> _stream_csv_snapshot
  -> _build_csv_result
  -> build_relationship_baseline
  -> build_baseline_analysis
  -> build_upload_intelligence
  -> run_sii_runner
```

The harness used a temporary runtime directory under `/tmp`, generated CSV files, ran the same parser and SII runner used by uploads, and recorded runtime, row acceptance, warnings, runner state, relationship-change count, and output labels.

Detection rule used for this assessment:

```text
predicted_positive =
  drift_status in {review, unstable, elevated}
  OR operating_state contains drift/action
  OR runner_instability_score >= 0.24
  OR relationship_change_count > 0
```

This is intentionally broad because the UI and persisted payload can expose runner instability and relationship evidence even when top-level `drift_status` remains `info`. A stricter rule based only on `drift_status` would hide internal contradictions rather than measure the whole current pipeline.

## Original Pre-Fix Aggregate Result

| Metric | Result |
|---|---:|
| Total synthetic tests | 28 |
| Expected positive tests | 7 |
| Expected negative/stable tests | 21 |
| True positives | 7 |
| False negatives | 0 |
| True negatives | 0 |
| False positives | 21 |
| Detection accuracy | 25.0% |
| False positive rate on stable/negative cases | 100.0% |
| False negative rate on injected-positive cases | 0.0% |

The pipeline is sensitive but not reliable: it catches injected drift-like cases, but it also flags stable, missing, noisy, timing-irregular, and scale-only data as positive under the broad backend-output criterion.

## Original Pre-Fix Test Results

| Test | Expected | Predicted | Accuracy | FP | FN | Runtime s | RSS delta MB | Rows used/dropped | Drift status | Runner score | Relationships | Failure mode |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---|
| missing_random_rows | negative | positive | 0 | 1 | 0 | 1.8285 | 6.34 | 942/0 | info | 0.676992 | 0 | false_positive |
| missing_columns_sparse_sensor | negative | positive | 0 | 1 | 0 | 1.8604 | 0.98 | 1000/0 | info | 0.49 | 0 | false_positive |
| null_values | negative | positive | 0 | 1 | 0 | 1.8628 | 0.03 | 1000/0 | info | 0.49 | 0 | false_positive |
| partial_malformed_rows | negative | positive | 0 | 1 | 0 | 1.8240 | 0.01 | 968/32 | info | 0.716896 | 0 | false_positive |
| gaussian_noise_low | negative | positive | 0 | 1 | 0 | 1.8780 | 0.00 | 1000/0 | info | 0.49 | 0 | false_positive |
| gaussian_noise_high_stable | negative | positive | 0 | 1 | 0 | 1.8670 | 0.00 | 1000/0 | review | 0.49 | 0 | false_positive |
| sensor_spikes | positive | positive | 1 | 0 | 0 | 1.8933 | 0.00 | 1000/0 | unstable | 0.723901 | 1 | none |
| sensor_dropouts | positive | positive | 1 | 0 | 0 | 1.9435 | 1.63 | 1000/0 | info | 0.723901 | 0 | none |
| stuck_sensor | positive | positive | 1 | 0 | 0 | 1.9458 | 0.00 | 1000/0 | info | 0.723536 | 0 | none |
| out_of_order_timestamps | negative | positive | 0 | 1 | 0 | 1.9171 | -0.01 | 961/39 | info | 0.667577 | 0 | false_positive |
| duplicate_timestamps | negative | positive | 0 | 1 | 0 | 1.9464 | 0.00 | 997/3 | info | 0.723901 | 0 | false_positive |
| irregular_sampling | negative | positive | 0 | 1 | 0 | 1.8366 | 0.02 | 949/51 | info | 0.946676 | 0 | false_positive |
| missing_time_windows | negative | positive | 0 | 1 | 0 | 1.9100 | -0.02 | 985/15 | info | 0.723901 | 0 | false_positive |
| scale_100_stable | negative | positive | 0 | 1 | 0 | 0.6110 | -1.61 | 100/0 | info | 0.791787 | 4 | false_positive |
| scale_1000_stable | negative | positive | 0 | 1 | 0 | 1.9433 | 1.62 | 1000/0 | info | 0.723901 | 0 | false_positive |
| scale_10000_stable | negative | positive | 0 | 1 | 0 | 15.1798 | 9.17 | 10000/0 | info | 0.49 | 0 | false_positive |
| scale_100000_stable | negative | positive | 0 | 1 | 0 | 14.4609 | 4.99 | 100000/0 | info | 0.49 | 0 | false_positive |
| scale_1000000_stable | negative | positive | 0 | 1 | 0 | 38.7544 | 4.49 | 1000000/0 | info | 0.49 | 0 | false_positive |
| mixed_different_room_lengths | negative | positive | 0 | 1 | 0 | 1.1089 | 0.00 | 707/0 | info | 0.49 | 0 | false_positive |
| mixed_different_sensor_counts | negative | positive | 0 | 1 | 0 | 1.4449 | 0.00 | 1000/0 | info | 0.752063 | 0 | false_positive |
| mixed_missing_relationships | negative | positive | 0 | 1 | 0 | 1.4242 | 0.00 | 1000/0 | info | 0.722120 | 0 | false_positive |
| mixed_changing_operating_conditions | negative | positive | 0 | 1 | 0 | 1.5468 | 0.00 | 1000/0 | info | 0.723901 | 2 | false_positive |
| false_positive_stable | negative | positive | 0 | 1 | 0 | 1.5333 | 0.00 | 1000/0 | info | 0.723901 | 0 | false_positive |
| false_positive_noisy_stable | negative | positive | 0 | 1 | 0 | 1.5462 | 0.00 | 1000/0 | review | 0.49 | 0 | false_positive |
| true_positive_injected_drift | positive | positive | 1 | 0 | 0 | 1.5595 | 0.00 | 1000/0 | info | 0.723901 | 0 | none |
| true_positive_relationship_collapse | positive | positive | 1 | 0 | 0 | 1.5483 | 0.00 | 1000/0 | info | 0.49 | 0 | none |
| true_positive_covariance_shift | positive | positive | 1 | 0 | 0 | 1.5395 | 0.00 | 1000/0 | unstable | 0.49 | 0 | none |
| true_positive_progressive_degradation | positive | positive | 1 | 0 | 0 | 1.5744 | 0.00 | 1000/0 | unstable | 0.889775 | 0 | none |

## Findings By Category

### 1. Missing Values

Tests:

- random missing rows
- missing numeric cells
- null values
- malformed/partial rows

Result:

- Detection accuracy: 0/4 for stable missing-data cases.
- False positive rate: 4/4.
- False negative rate: 0/0 applicable for this group.
- Runtime: about 1.82-1.86 seconds for 1,000-row files.
- Memory: low RSS deltas, roughly 0-6 MB.
- Confidence behavior: runner confidence stayed high at `0.94` in most cases even when missing/null/malformed data was present.
- Failure mode: missingness often produced top-level `drift_status="info"` but runner instability scores from `0.49` to `0.716896`, causing positive backend SII signals.

Assessment:

The parser degrades gracefully for many missing values: it blanks invalid cells, drops malformed rows, and records warnings. The detection layer does not degrade gracefully: confidence remains high and runner state can escalate to `UNSTABLE`, `LOCK_IN`, or `CRITICAL` even when the top-level upload state is baseline-aligned.

### 2. Noisy Data

Tests:

- low Gaussian noise
- high Gaussian noise on otherwise stable data
- sensor spikes
- sensor dropouts
- stuck sensor

Result:

- Injected positives: 3/3 detected for spikes, dropouts, stuck sensor.
- Stable noisy negatives: 0/2 remained stable.
- False positive rate for stable noise: 2/2.
- Runtime: about 1.87-1.95 seconds for 1,000-row files.
- Confidence behavior: runner confidence stayed `0.94`, including low-noise stable data flagged as `LOCK_IN`/`CRITICAL`.
- Failure mode: no robust noise model or spike suppression. High Gaussian noise directly produced `drift_status="review"`. Low Gaussian noise still produced runner critical state.

Assessment:

The system is sensitive to noisy and spiky data, but not tolerant of it. It does not distinguish benign noise from structural change reliably.

### 3. Timing Problems

Tests:

- out-of-order timestamps
- duplicate timestamps
- irregular sampling
- missing time windows

Result:

- Detection accuracy: 0/4 for stable timing-problem cases.
- False positive rate: 4/4.
- Runtime: about 1.84-1.95 seconds for 1,000-row files.
- Memory: low.
- Confidence behavior: runner confidence stayed `0.94`.
- Failure mode: timestamp problems created warnings, dropped rows, and high runner scores. Irregular sampling produced runner score `0.946676`.

Assessment:

The parser can sort timestamps and drop duplicates. The math does not model irregular sampling intervals; most downstream calculations are row-order based. Missing windows and irregular intervals can become false-positive structural signals.

### 4. Scale Issues

Tests:

- 100 rows
- 1,000 rows
- 10,000 rows
- 100,000 rows
- 1,000,000 rows

Result:

- All scale tests used stable data and all produced positive backend SII signals.
- False positive rate: 5/5.
- Runtime:
  - 100 rows: 0.6110s
  - 1,000 rows: 1.9433s
  - 10,000 rows: 15.1798s
  - 100,000 rows: 14.4609s
  - 1,000,000 rows: 38.7544s for a 110.83 MB CSV
- Memory: RSS deltas were modest in this harness, but this is not a full production memory profile.
- Confidence behavior: runner confidence stayed `0.94` and runner regime was `LOCK_IN`/`CRITICAL` even for stable files.
- Prior failure mode: analysis used to be capped at 10,000 accepted rows while the parser still scanned the full raw file. Current upload analysis and SII ingestion pass all cleaned rows through; the 1M-row benchmark should be regenerated after this change.

Assessment:

The current parser can ingest large flat CSVs, and current upload analysis passes all cleaned rows into SII ingestion. Stable large-dataset behavior should still be revalidated, because scale completion does not by itself imply reliable interpretation.

### 5. Mixed Telemetry

Tests:

- different room lengths
- different sensor counts by room
- missing relationships
- changing operating conditions

Result:

- Detection accuracy: 0/4 for expected-negative mixed cases.
- False positive rate: 4/4.
- Runtime: about 1.1-1.55 seconds.
- Confidence behavior: runner confidence remained high or moderately high: `0.864` to `0.94`.
- Failure mode: heterogeneous room coverage and missing relationships were treated as high runner instability rather than lowering confidence enough to suppress interpretation.

Assessment:

The code can segment room-like columns and keep rows with missing room-specific sensors, but it does not build separate robust baselines per room with different sensor availability. Mixed telemetry is accepted, but not interpreted reliably.

### 6. False Positive Testing

Tests:

- stable data
- noisy stable data

Result:

- Stable data remained top-level `Baseline-aligned`, but runner score was `0.723901`, regime `LOCK_IN`, urgency `CRITICAL`.
- Noisy stable data produced `drift_status="review"` and runner regime `LOCK_IN`/`CRITICAL`.
- False positive rate: 2/2.

Assessment:

This is the most serious weakness. Current backend outputs can internally disagree: top-level fields say stable while runner fields say critical. A UI or downstream consumer that reads runner instability can present a false alert for stable telemetry.

### 7. True Positive Testing

Tests:

- injected drift
- relationship collapse
- covariance shift
- progressive degradation

Result:

- Detection accuracy: 4/4.
- False negative rate: 0/4.
- Runtime: about 1.54-1.57 seconds.
- Confidence behavior: runner confidence stayed `0.94` for all cases.
- Failure mode: detection is broad and sensitive, but not well calibrated. Relationship collapse was detected by runner score despite `relationship_change_count=0`, so the named relationship-collapse mechanism did not actually surface as relationship evidence in that test.

Assessment:

The pipeline catches injected degradation, but because it also catches stable data, this is sensitivity rather than reliable discrimination.

## Original Pre-Fix Confidence Behavior

In the original benchmark, confidence was not a reliable uncertainty signal for messy telemetry.

Observed behavior:

- Runner confidence was usually `0.94`, including stable data, noisy stable data, missing rows, null values, timing problems, and true-positive cases.
- Missing sensor counts reduced confidence only in one mixed case (`0.864`), but still produced `LOCK_IN`/`CRITICAL`.
- Attribution confidence was usually `low`, even while runner urgency was critical.
- `sii_reliable_enough_to_show` was `true` in all completed tests, including false positives.

Original root cause from pre-fix code:

`confidence_from_history` in `backend/app/services/sii_runner.py` depends on history length and vector completeness:

```text
confidence = clamp(0.4 + min(history_length/12, 1.0)*0.35 + completeness*0.19, 0.35, 0.94)
```

The current implementation now accounts for current/recent completeness in the confidence cap, but it still does not model timestamp irregularity, false-positive likelihood, noise model fit, or relationship evidence quality as calibrated probability terms.

## Original Pre-Fix Failure Modes

1. High false positives on stable data.
   Stable data repeatedly produced runner `LOCK_IN`/`CRITICAL` and instability scores above the assessment threshold.

2. Internal output contradiction.
   Many tests had `drift_status="info"` and `operating_state="Baseline-aligned"` while runner state was `LOCK_IN`/`CRITICAL`.

3. Confidence is overconfident.
   Confidence saturates at `0.94` based mostly on row count and completeness.

4. Timing is not mathematically modeled.
   Timestamps are parsed, sorted, and profiled, but drift math is largely row-order based. Irregular sampling and missing windows can become false positives.

5. Missingness is accepted but not calibrated.
   Missing/null/malformed data is cleaned, but downstream confidence and escalation do not sufficiently reflect degraded input quality.

6. Relationship collapse is not reliably represented as relationship evidence.
   The relationship-collapse test was detected by runner score, but `relationship_change_count` was 0.

7. Scale is operationally plausible but not interpretively reliable.
   The 1M-row file completed in 38.7544s without allocation tracing, but stable large data still produced positive runner instability.

## Can Neraium Reliably Handle Real-World Messy Telemetry?

Current answer after targeted fixes: partially, but not yet proven across the full messy-telemetry matrix.

The ingestion layer is reasonably tolerant: it can parse messy CSVs, sort timestamps, drop duplicate or malformed rows, retain partially missing rows, and process large files. The interpretation layer now has guardrails for the worst stable/noisy false positives found in regression testing, but full industrial readiness still needs the complete 28-case benchmark regenerated and expanded.

The current system is better described as:

```text
messy CSV ingestion: moderately robust
structural detection: better guarded, still heuristic
confidence: completeness-aware but not probabilistically calibrated
prediction: heuristic only
industrial readiness: improved but still needs full benchmark coverage
```

## Updated Scores After Targeted Fixes

| Dimension | Score | Rationale |
|---|---:|---|
| Mathematical rigor | 5/10 | Covariance scoring is now baseline-relative and gated, but thresholds remain heuristic and the fuller temporal math engine is still not on the upload path. |
| Noise tolerance | 5/10 | Stable and noisy-stable regressions now remain nominal, but there is still no formal sensor noise model or spike classifier. |
| Missing data tolerance | 5/10 | Ingestion already tolerated missing/null values, and confidence now drops with recent missingness; broader missingness sweeps are still needed. |
| Industrial telemetry readiness | 4/10 | The worst runner false positives are fixed in regression coverage, but mixed-room and irregular-sampling behavior still needs a regenerated benchmark. |
| Predictive capability | 1/10 | Projected time remains hardcoded heuristic scaling, not validated prediction. |
| Explainability | 7/10 | Runner outputs and docs now better reflect the actual math, with confidence no longer counted as direct instability. |
| Production readiness | 5/10 | Backend upload/service tests pass and core false positives are guarded, but full messy-telemetry benchmark acceptance criteria are not yet automated. |

## Recommended Next Evaluation Work

Before changing behavior, the next evaluation should add a fixed regression suite with known synthetic ground truth:

- stable baseline families with different amplitudes and frequencies
- noisy-stable families with controlled SNR
- missingness sweeps from 1% to 60%
- irregular sampling sweeps
- room-specific baselines with unequal sensor availability
- drift/covariance/relationship-collapse injections at graded severity
- assertions on both top-level UI fields and runner fields

The acceptance bar should include specificity, not just sensitivity. A practical starting target would be:

```text
false positive rate <= 10% on stable/noisy-stable synthetic telemetry
false negative rate <= 15% on injected drift/covariance/relationship tests
confidence decreases when missingness, timestamp irregularity, or sparse room coverage increases
top-level state and runner state cannot disagree without an explicit uncertainty state
```
