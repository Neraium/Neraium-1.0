# SII Math Audit

This document traces the current uploaded-CSV path from telemetry ingestion to backend SII output and UI display. It documents the math that is present in code, identifies hardcoded constants, and labels non-mathematical heuristics directly.

## Scope And Primary Files

Uploaded CSV processing currently runs through these implementation points:

- `backend/app/services/upload_jobs.py`: CSV ingestion, safe cleaning, room segmentation heuristics, relationship baseline orchestration, replay generation, result persistence.
- `backend/app/services/data_quality.py`: timestamp detection/profiling, numeric profiling, numeric parsing, data-quality readiness.
- `backend/app/services/baseline_analysis.py`: simple baseline-vs-recent column drift.
- `backend/app/services/relationship_baselines.py`: current upload relationship baseline and top relationship changes.
- `backend/app/services/sii_runner.py`: backend-native SII runner, covariance/Mahalanobis scoring, runtime state output.
- `backend/app/engine/temporal_math.py`: separate temporal math engine. It is present and tested, but the current upload path does not call it from `_build_csv_result`.
- `backend/app/services/sii_intelligence.py`: converts engine/runner/attribution output into SII intelligence fields.
- `backend/app/services/system_interpretation.py`: converts upload/replay fields into gate-level interpretation and relationship divergence metrics.
- `backend/app/services/evidence_store.py` and `backend/app/services/upload_jobs.py`: evidence record persistence.
- UI consumers: `frontend/src/components/workspaces/SystemBody/SystemBodyWorkspace.jsx`, `frontend/src/components/replay/ReplayWorkspace.jsx`, `frontend/src/components/ObservationCenterWorkspace.jsx`, `frontend/src/viewModels/uploadState.js`.

## End-To-End Pseudocode

```text
process_upload_bytes(filename, bytes):
  write bytes to a temp file
  process_csv_file(temp_path)

process_csv_file:
  snapshot = _stream_csv_snapshot(path, max_analysis_rows=10000)
  _build_csv_result(job_id, filename, snapshot.sample_rows, snapshot metadata)

_stream_csv_snapshot:
  detect delimiter from first nonblank lines
  detect whether first row is header
  normalize duplicate/blank headers
  detect timestamp column by header hint or sample parse ratio
  detect identity column (room/zone/location/etc.)
  detect numeric columns from first <=1000 usable rows
  for each data row:
    drop blank/malformed rows
    if timestamp column exists:
      parse timestamp, drop invalid timestamps
      drop duplicate timestamp per identity value
    parse numeric cells; invalid numeric cells become empty strings
    drop row if no usable numeric values
    keep cleaned row
  sort rows by timestamp if timestamp exists
  return cleaned sample rows and ingestion counts

_build_csv_result:
  detect numeric columns from cleaned rows
  profile numeric columns
  segment rows by room-like column or State Group A
  assign per-room urgency via robust early-vs-recent mean/variance heuristic
  build relationship baseline/correlation changes
  build replay frames
  build timestamp profile, baseline analysis, cultivation mapping, data quality
  build engine_result from baseline and relationship changes
  build driver_attribution
  build operator_report
  build sii_intelligence
  run BackendSiiRunner over numeric vectors
  if runner returns latest_state:
    overwrite sii_intelligence.instability_index and projected time fields
  persist upload result, summary, latest SII state, evidence run
```

## 1. Input Shape

### Rows

The upload parser reads CSV-like text using `_stream_csv_snapshot`. It streams the file, cleans accepted rows, and passes all cleaned rows into downstream analysis and SII ingestion. Returned `row_count` is the number of rows retained after cleaning, not raw file lines.

Plain English: every downstream calculation works on cleaned accepted rows, not all uploaded rows.

### Timestamps

Timestamp detection has two paths:

- Header-only `_detect_timestamp_column` in `upload_jobs.py:1286-1293` chooses a column whose name contains `timestamp`, `time`, `datetime`, `date_time`, `logged_at`, or `recorded_at`; if none exists, it falls back to the first column.
- Data-quality `detect_timestamp_column` in `data_quality.py:31-59` first uses header hints, then samples up to 200 rows and requires at least 3 observed values and at least 60% parseable timestamps.

Timestamp parsing accepts ISO values, trailing `Z`, slash-to-dash variants, space-to-`T` variants, and formats `%Y-%m-%d %H:%M:%S`, `%Y-%m-%d %H:%M`, `%Y-%m-%d` (`data_quality.py:185-204`).

Plain English: timestamps are used for sorting and coverage, but most math is row-order based after sorting.

### Numeric Columns

During streaming, numeric indexes are detected from the first up to 1000 detection rows. A column must not be timestamp or identity, and must have parseable numeric values in at least `max(3, int(sample_count * 0.15))` sampled rows (`upload_jobs.py:475-490`). `_build_csv_result` later calls `_detect_numeric_columns`, again requiring at least `max(3, int(len(sample) * 0.15))` parseable values in the first up to 1000 cleaned rows, excluding timestamp; event-like columns are removed if at least 3 continuous columns remain (`upload_jobs.py:1316-1328`).

Numeric profiles require at least 3 values and numeric ratio at least 0.4 among non-missing values (`data_quality.py:62-87`).

Plain English: a column can be numeric if only 15% of sampled rows parse numerically for pipeline inclusion, but it needs stronger evidence for the numeric profile list.

### Ignored Columns

Timestamp and identity columns are excluded from streaming numeric detection (`upload_jobs.py:475-490`). Event-like numeric columns with names containing `event`, `status`, `fault`, `alarm`, or `override` are excluded from `_detect_numeric_columns` when at least 3 non-event numeric columns remain (`upload_jobs.py:1316-1328`). Non-numeric columns are skipped by numeric profiling and baseline analysis (`data_quality.py:86-87`, `baseline_analysis.py:45-47`).

### Missing Values

Blank numeric cells are counted as missing (`data_quality.py:71-75`, `upload_jobs.py:538-557`). Invalid numeric cells in streaming are replaced with `""`, counted, and the row can remain if at least one numeric value is usable (`upload_jobs.py:541-555`). In the runner, missing numeric cells become `NaN`; rows are kept unless all numeric values are `NaN` (`sii_runner.py:413-442`).

### Preprocessing Rules

Delimiter detection uses `csv.Sniffer` over first nonblank sample lines with delimiters `,`, tab, `;`, and `|`, otherwise whitespace (`upload_jobs.py:387-401`). Headers are detected when numeric-looking plus timestamp-looking token count is less than `max(1, len(tokens)//2)` (`upload_jobs.py:404-409`). Duplicate column names are renamed with suffix `_2`, `_3`, etc. (`upload_jobs.py:412-421`).

## 2. Data Cleaning Math And Rules

### Type Coercion

`parse_numeric_value` strips whitespace, removes commas and percent signs, treats `nan`, `null`, `none`, `n/a`, `na`, and `-` as missing, parses the first whitespace-separated token, and falls back to filtering digits plus `.`, `-`, `+` before `float()` (`data_quality.py:207-229`).

Formula:

```text
numeric_value = float(first_token_without_commas_or_percent)
fallback = float(chars in first_token where char is digit or . or - or +)
```

Plain English: values like `"1,234"` and `"45%"` become numbers; unit-suffixed values can sometimes parse by stripping non-numeric characters.

### Missing Value Handling

The current upload pipeline does not interpolate missing values. It either:

- Leaves blank values blank in cleaned rows.
- Replaces invalid numeric cells with blank strings during streaming (`upload_jobs.py:545-551`).
- Drops rows only when no usable numeric values exist (`upload_jobs.py:553-555`).
- For runner vectors, uses `NaN` for missing cells and `nanmean`, `nanstd`, and `nan_to_num` inside calculations (`sii_runner.py:70-87`, `sii_runner.py:112-120`).

Plain English: there is no time-series interpolation. Missing cells are skipped, blanked, or treated through NumPy NaN-safe operations.

### Drop Logic

Rows are dropped for blank line, column-count mismatch, invalid timestamp, duplicate timestamp per identity, or no usable numeric values (`upload_jobs.py:506-563`). Drop reasons are persisted in `ingestion_report.drop_reasons` (`upload_jobs.py:571-621`, `upload_jobs.py:1149-1157`).

### Duplicate Handling

If a timestamp column exists, duplicates are keyed as `identity_value::timestamp_iso`. Duplicate keys are dropped (`upload_jobs.py:524-535`). If there is no timestamp column, duplicate rows are not mathematically deduplicated.

### Timestamp Sorting

Rows are sorted by parsed timestamp if a timestamp column exists (`upload_jobs.py:565-567`). A warning is recorded if sorting changed row order (`upload_jobs.py:594-595`).

### Normalization And Scaling

There is no global normalization of cleaned rows before baseline analysis or relationship baseline. Specific scoring stages normalize locally:

- replay drift: `abs(value - baseline_mean) / max(abs(baseline_mean), 1.0 if near zero)` (`upload_jobs.py:1367-1376`)
- runner fallback drift: `abs(recent_mean - baseline_mean) / safe_baseline` with `safe_baseline = 1.0` when `abs(baseline_mean) < 1e-6` (`sii_runner.py:73-79`)
- temporal math state drift: z-score against baseline standard deviation, with std floor to 1.0 (`temporal_math.py:193-198`)

### Sparse Data Rules

Per-room sparse data is `count < 4`; sparse rooms are assigned `urgency="review"`, `driver_category="sensor_network"`, `attribution_confidence="low"`, `room_state="Insufficient telemetry"` (`upload_jobs.py:961-985`).

Baseline analysis requires at least 5 rows (`baseline_analysis.py:18-26`). Relationship baseline requires at least 12 rows and at least 2 selected numeric columns (`relationship_baselines.py:74-82`). Temporal math requires at least `max(8, min_baseline_rows + 4)` rows, with default `min_baseline_rows=12`, so default minimum is 16 rows and at least 1 numeric feature (`temporal_math.py:10-17`, `temporal_math.py:40-43`).

## 3. Feature Generation

### Numeric Profiles

For each numeric profile:

```text
min = min(values)
max = max(values)
average = sum(values) / n
missing_percent = missing_count / row_count * 100
```

Reference: `data_quality.py:89-104`.

Plain English: this is descriptive profiling only.

Variability:

```text
variance = sum((x - average)^2) / n
std = sqrt(variance)
baseline = abs(average) if abs(average) > 1e-6 else max(abs(values))
coefficient = std / baseline
low if coefficient < 0.02
high if coefficient > 0.25
normal otherwise
```

Reference: `data_quality.py:261-274`.

Plain English: variability is coefficient of variation with a fallback baseline when the mean is near zero.

### Simple Column Drift

Baseline window:

```text
baseline_window_size = min(100, max(1, len(rows)//2))
recent_window_size = min(100, len(rows) - baseline_window_size)
baseline_rows = rows[:baseline_window_size]
recent_rows = rows[-recent_window_size:]
```

Reference: `baseline_analysis.py:6-9`, `baseline_analysis.py:28-41`.

Per column:

```text
baseline_average = mean(baseline_values)
recent_average = mean(recent_values)
absolute_change = recent_average - baseline_average
percent_change = None if abs(baseline_average) < 1e-6
percent_change = absolute_change / abs(baseline_average) * 100 otherwise
```

Reference: `baseline_analysis.py:60-65`, `baseline_analysis.py:126-129`.

Plain English: this compares the first half/first up to 100 rows against the latest comparable window.

Direction:

```text
threshold = max(abs(baseline_average) * 0.01, 0.01)
up if absolute_change > threshold
down if absolute_change < -threshold
flat otherwise
```

Reference: `baseline_analysis.py:132-138`.

Drift flag:

```text
if percent_change is None:
  watch if abs(absolute_change) > 0.01 else normal
elif abs(percent_change) >= 20:
  review
elif abs(percent_change) >= 10:
  watch
else:
  normal
```

Reference: `baseline_analysis.py:141-156`.

Plain English: 10% starts watch, 20% starts review; near-zero baselines fall back to absolute movement over 0.01.

### Relationship Baseline And Correlation Drift

The current upload result uses `build_relationship_baseline` (`upload_jobs.py:1027-1046`, `relationship_baselines.py:61-165`).

Column limit:

```text
max_relationship_columns = 32
selected_numeric_columns = numeric_columns[:32]
```

Reference: `relationship_baselines.py:42-59`, `relationship_baselines.py:66-73`.

Baseline/recent split:

```text
baseline_count = max(6, int(len(rows) * 0.7))
baseline_rows = rows[:baseline_count]
recent_rows = rows[baseline_count:]
```

Reference: `relationship_baselines.py:84-87`.

Sampling limits:

```text
if len(baseline_rows) > 12000: baseline_rows = baseline_rows[:12000]
if len(recent_rows) > 6000: recent_rows = recent_rows[-6000:]
```

Reference: `relationship_baselines.py:66-68`, `relationship_baselines.py:88-98`.

Pearson correlation:

```text
mean_x = sum(x)/n
mean_y = sum(y)/n
r = sum((x_i - mean_x) * (y_i - mean_y)) /
    sqrt(sum((x_i - mean_x)^2) * sum((y_i - mean_y)^2))
```

Reference: `relationship_baselines.py:27-39`.

Relationship candidate:

```text
baseline_strength = abs(baseline_corr)
if baseline_strength < 0.65: skip
drift = abs(recent_corr - baseline_corr)
if drift < 0.25: skip
```

Reference: `relationship_baselines.py:122-141`.

Ranking:

```text
candidates.sort by (correlation_delta, coupling_strength), descending
top_relationship_changes = candidates[:5]
```

Reference: `relationship_baselines.py:156-164`.

Plain English: relationship evidence is only recorded for pairs that were strongly coupled in baseline and changed by at least 0.25 absolute correlation points.

### Replay Drift Metrics

Replay frames are generated by `_build_replay` (`upload_jobs.py:1347-1404`).

Frame positions:

```text
frame_target = min(120, max(20, len(rows)))
positions = round(i * (len(rows)-1) / max(frame_target-1, 1)) for i in range(frame_target)
```

Reference: `upload_jobs.py:1354-1355`.

Replay baseline:

```text
baseline_rows = rows[:max(5, min(100, len(rows)//10))]
baseline[col] = mean(non_missing values in baseline_rows)
```

Reference: `upload_jobs.py:1356-1362`.

Frame drift:

```text
shift_col = abs(value_col - baseline_col) / (abs(baseline_col) if abs(baseline_col) > 1e-6 else 1.0)
drift = mean(top 5 shift_col values)
velocity = drift - previous_drift
primary_contributors = top 3 columns by shift
```

Reference: `upload_jobs.py:1367-1379`.

Phase:

```text
stable_topology if drift < 0.1
relationship_weakening if drift < 0.25
propagation_activation otherwise
```

Reference: `upload_jobs.py:1380-1399`.

Plain English: replay is a sampled visualization of relative movement from early-row means, not a separate learned model.

## 4. Baseline Construction

There are multiple baselines:

1. Simple column baseline: first half of rows capped at 100 rows; recent window is last comparable up to 100 rows (`baseline_analysis.py:28-41`).
2. Relationship baseline: first 70% of cleaned rows, at least 6 rows, capped at 12000 rows (`relationship_baselines.py:84-96`).
3. Replay baseline: first `max(5, min(100, len(rows)//10))` rows (`upload_jobs.py:1356`).
4. Runner baseline: `BackendSiiRunner` baseline vectors are prior history excluding the recent window, capped by `baseline_window`; upload integration sets `baseline_window = min(50, max(2, min(48, vector_count//2 or 2)))`, which effectively caps at 48 for normal uploads (`sii_runner.py:353-354`, `sii_runner.py:224-236`).
5. Temporal math baseline: first `max(12, int(n*0.35))`, clamped to at least 4 and at most `n-2` (`temporal_math.py:45-48`). This engine is not called by current `_build_csv_result`.

Minimums:

- Simple baseline: 5 rows (`baseline_analysis.py:9`, `baseline_analysis.py:18-26`).
- Relationship baseline: 12 rows and 2 numeric columns (`relationship_baselines.py:74-82`).
- Runner starts at one vector but classifies first two vectors as warmup/nominal (`sii_runner.py:703-712`).
- Temporal math: default 16 rows and 1 numeric column (`temporal_math.py:40-43`).

Normal behavior is represented as means for column/replay/runner fallback baselines, Pearson correlations for relationship baselines, covariance matrix for runner Mahalanobis scoring, and distributional/relationship summaries in temporal math.

## 5. SII Detection Math

### Current Upload Engine Result

The upload result builds `engine_result` from significant column drift and relationship changes in `_build_upload_engine_result` (`upload_jobs.py:816-911`).

Significant column drift:

```text
significant_drift = drift where drift_flag in {watch, review}
persistent_columns = review drift columns plus relationship-change columns
```

Reference: `upload_jobs.py:823-870`.

Signal level from column drift:

```text
elevated if drift_flag == review and abs(percent_change) >= 30
review if drift_flag == review
watch if drift_flag == watch
info otherwise
```

Reference: `upload_jobs.py:624-633`.

Corroboration:

```text
strong if relationship_changes and meaningful_categories >= 2
moderate if relationship_changes or significant_drift
limited otherwise
```

Reference: `upload_jobs.py:872-882`.

Overall result:

```text
elevated if any signal level is elevated or overall_urgency == unstable
needs_review if any signals or relationship_changes or overall_urgency == review
complete otherwise
```

Reference: `upload_jobs.py:893-911`.

Plain English: current upload `engine_result` is rule-based aggregation over simple drift and relationship candidates.

### Per-Room Urgency Heuristic

For each room/segment, the current code calculates a robust early-vs-recent drift heuristic over up to the first 4 numeric columns:

```text
for up to first 4 numeric columns:
  clean = non-missing values
  if len(clean) < 6: skip this signal
  window_size = max(3, len(clean)//3)
  baseline_slice = first window_size values
  recent_slice = last window_size values
  baseline = mean(baseline_slice)
  recent = mean(recent_slice)
  baseline_std = population_std(baseline_slice)
  recent_std = population_std(recent_slice)
  denom = max(abs(baseline), baseline_std * 3.0, 1.0)
  mean_shift = abs(recent - baseline) / denom
  variance_growth = max(0.0, recent_std - baseline_std) / denom
  per_signal_drift = mean_shift + variance_growth * 0.5
room_drift = mean(per_signal_drifts)
```

Reference: `upload_jobs.py:961-986`, `upload_jobs.py:1318-1323`.

Plain English: room drift compares early and recent operating windows instead of using the full range. Stable noisy telemetry can have a wide min/max range without being treated as drift unless the recent mean or variance grows relative to the baseline window.

State thresholds:

```text
count < 4 -> review / Insufficient telemetry
room_drift > 0.25 -> unstable / Persistent structural drift observed
room_drift > 0.08 -> review / Structural drift observed
otherwise -> nominal / Baseline-aligned
```

Reference: `upload_jobs.py:987-1007`.

Plain English: room state is still a heuristic, not a covariance model.

### Backend SII Runner: Fallback Score

Runner vectors include all numeric profile columns and keep rows with at least one non-NaN value (`sii_runner.py:413-442`).

Baseline/recent windows:

```text
recent_count = min(recent_window, history_length)
recent_vectors = last recent_count vectors
baseline_source = history before recent window, or first half when absent
baseline_vectors = last baseline_window vectors from baseline_source
```

Reference: `sii_runner.py:224-236`.

Fallback structural drift:

```text
baseline_mean = nanmean(baseline_vectors)
recent_mean = nanmean(recent_vectors)
safe_baseline = abs(baseline_mean), replaced by 1.0 where abs < 1e-6
normalized_delta = abs(recent_mean - baseline_mean) / safe_baseline
fallback_structural_drift = clip(nanmean(normalized_delta), 0.0, 1.5)
```

Reference: `sii_runner.py:73-79`.

Fallback transition pressure:

```text
last_step = abs(current_vector - previous_vector) / safe_baseline
fallback_transition_pressure = clip(nanmean(last_step), 0.0, 1.5)
```

Reference: `sii_runner.py:80-84`.

Fallback variability pressure:

```text
variability = nanstd(recent_vectors)
fallback_variability_pressure = clip(variability / max(nanmean(safe_baseline), 1.0), 0.0, 1.0)
```

Reference: `sii_runner.py:86-87`.

Fallback score:

```text
fallback_score = clip(
  fallback_structural_drift * 0.55
  + fallback_transition_pressure * 0.30
  + fallback_variability_pressure * 0.15,
  0.0, 1.0
)
```

Reference: `sii_runner.py:88-96`.

Plain English: fallback score combines mean drift, last-step movement, and recent variability.

### Backend SII Runner: Covariance/Mahalanobis Score

Covariance scoring is gated by baseline sufficiency:

```text
baseline_completeness = mean(non_nan cells in baseline_vectors)
recent_completeness = mean(non_nan cells in recent_vectors)
enough_baseline_for_covariance = (
  len(baseline_matrix) >= 8
  and baseline_completeness >= 0.65
  and vector_dimension > 0
)
```

Reference: `sii_runner.py:121-130`.

Regularized covariance matrix:

```text
baseline_covariance = np.cov(baseline_matrix, rowvar=False, bias=True)
variance_scale = mean(positive diagonal variances) or 1.0
regularization = max(variance_scale * 0.05, 0.001)
baseline_covariance += identity * regularization
covariance_inverse = pinv(baseline_covariance)
centered_vector = current_vector - baseline_mean
mahalanobis_distance = sqrt(max(centered_vector.T @ covariance_inverse @ centered_vector, 0))
```

Reference: `sii_runner.py:132-145`, `sii_runner.py:269-280`.

Plain English: the covariance matrix uses a variance-scaled diagonal floor to reduce singular-covariance spikes.

Structural drift score:

```text
baseline_distances = Mahalanobis distances for each baseline vector against baseline_mean
baseline_distance_limit = max(mean(baseline_distances) + 3*std(baseline_distances), 1.0)
excess_distance = max(0.0, mahalanobis_distance - baseline_distance_limit)
structural_drift_score = clip(excess_distance / baseline_distance_limit, 0.0, 1.0)
```

Reference: `sii_runner.py:148-153`, `sii_runner.py:283-295`.

Plain English: distance is scored only when it exceeds the baseline distribution by more than a 3-sigma-style limit.

Covariance shift and structural corroboration:

```text
covariance_shift = frobenius_norm(recent_covariance - baseline_covariance) /
                   max(frobenius_norm(baseline_covariance), 1e-6)
if fallback_structural_drift < 0.08 and covariance_shift < 0.8:
  structural_drift_score = 0.0
```

Reference: `sii_runner.py:156-168`.

Plain English: a covariance-distance spike alone is not enough to call structural drift when the recent mean is near baseline and covariance shift is modest.

Trajectory curvature:

```text
drift_velocity = mahalanobis_distance - previous_distance
drift_acceleration = drift_velocity - previous_velocity
trajectory_curvature = clip(abs(drift_acceleration) / max(abs(drift_velocity), 1e-6), 0.0, 1.0)
```

Reference: `sii_runner.py:154-166`.

Dynamic threshold and persistence:

```text
dynamic_threshold = mean(distance_history + current_distance) + std(distance_history + current_distance)
distance_window = latest recent_window distances
persistence_condition = at least 3 values in distance_window > dynamic_threshold, if len >= 3
accumulation = sum(distance_window)
accumulation_condition = len(distance_window) >= 3 and accumulation >= dynamic_threshold * 3.0
corroborated_drift = persistence_condition and accumulation_condition and structural_drift_score >= 0.08
motion_gate = max(structural_drift_score, min(covariance_shift, 1.0) * 0.25 if corroborated_drift else 0.0)
```

Reference: `sii_runner.py:170-179`.

Technical score:

```text
technical_score = clip(
  structural_drift_score * 0.45
  + min(abs(drift_velocity), 1.0) * motion_gate * 0.20
  + min(abs(drift_acceleration), 1.0) * motion_gate * 0.15
  + min(covariance_shift, 1.0) * (1.0 if corroborated_drift else 0.25) * 0.15
  + min(trajectory_curvature, 1.0) * motion_gate * 0.05,
  0.0, 1.0
)
if not (persistence_condition and accumulation_condition):
  technical_score = min(technical_score, 0.19)
fallback_adjusted_score = fallback_score
if not corroborated_drift and fallback_structural_drift < 0.08:
  fallback_adjusted_score = min(fallback_adjusted_score, 0.20)
instability_score = max(fallback_adjusted_score * 0.35, technical_score)
transition_pressure = clip((abs(drift_velocity) + abs(drift_acceleration)) * motion_gate, 0.0, 1.0)
if not corroborated_drift:
  transition_pressure = min(transition_pressure, 0.27)
```

Reference: `sii_runner.py:181-207`.

Plain English: uncorroborated covariance movement is capped below the `TRANSITION`/`WATCH` threshold, and velocity/acceleration only add pressure when drift is corroborated.

### Runner State Thresholds

```text
if history_length < 3: WARMUP, NOMINAL
elif instability_score >= 0.72 or transition_pressure >= 0.9: LOCK_IN, CRITICAL
elif instability_score >= 0.52 or transition_pressure >= 0.62: UNSTABLE, ALERT
elif instability_score >= 0.24 or transition_pressure >= 0.28: TRANSITION, WATCH
else: STABLE, NOMINAL
```

Reference: `sii_runner.py:703-712`.

Urgency normalization:

```text
CRITICAL -> unstable
ALERT -> elevated
WATCH -> review
otherwise -> nominal
```

Reference: `sii_runner.py:721-729`.

Room state mapping:

```text
LOCK_IN or UNSTABLE -> Needs action
TRANSITION -> Drift observed
STABLE -> Stable
WARMUP -> Monitoring
```

Reference: `sii_runner.py:732-739`.

### Runner Confidence

```text
current_completeness = mean(~isnan(current_vector))
recent_completeness = mean(~isnan(recent_vectors))
history_factor = min(history_length / 24.0, 1.0)
raw_confidence = 0.25 + history_factor*0.30 + current_completeness*0.20 + recent_completeness*0.20
quality_cap = 0.90 if min(current_completeness, recent_completeness) >= 0.995
              else 0.55 + min(current_completeness, recent_completeness)*0.35
confidence = clip(raw_confidence, 0.25, quality_cap)
```

Reference: `sii_runner.py:782-788`.

Plain English: confidence is still deterministic, but recent missingness now caps confidence below the complete-data maximum. It is not a calibrated probability.

### Runner Instability Index

`build_instability_index` converts latest runner state into the `sii_intelligence.instability_index` object (`sii_runner.py:623-664`).

```text
drift = structural_drift_score or drift
relationship = transition_pressure if present else relationship_degradation
entropy = covariance_shift if present else entropy_growth
runner_score = latest_state.instability_score
causal = confidence * runner_score
topology = covariance_shift * 0.7 + trajectory_curvature * 0.3
score = drift * 0.35 + relationship * 0.25 + entropy * 0.15 + causal * 0.15 + topology * 0.10
```

Reference: `sii_runner.py:631-649`.

Plain English: confidence is no longer treated as direct instability. It contributes only as confidence-weighted evidence for the runner's own instability score.

### Review Window Heuristic

Runner review-window hours:

```text
base_hours = unstable:8, elevated:36, review:72, nominal:504
risk_factor = instability_score * 0.5 + structural_drift * 0.3 + transition_pressure * 0.2
scaled = int(base_hours * max(0.25, 1.0 - min(max(risk_factor, 0.0), 0.9)))
hours = max(4, scaled)
```

Reference: `sii_runner.py:764-772`.

Plain English: this is a hardcoded operational review-window heuristic; it is not a validated failure-time model.

### Temporal Math Engine

`backend/app/engine/temporal_math.py` contains a fuller math pipeline, but current `_build_csv_result` does not call `evaluate_temporal_math`. Its outputs should not be claimed as current upload UI behavior unless another caller invokes it.

Key formulas present:

- State drift: `mean(abs((active - baseline_mean) / baseline_std)) / 4`, clipped 0-1 (`temporal_math.py:193-198`).
- Variance growth: rolling active variance divided by baseline variance, excess over 1, mean divided by 3 (`temporal_math.py:201-211`).
- Entropy growth: histogram entropy with 12 bins, excess over baseline entropy divided by `baseline_entropy + 1` (`temporal_math.py:214-236`).
- Correlation drift: rolling `nanmean(abs(active_corr - baseline_corr)) / 1.5` (`temporal_math.py:239-254`).
- Mutual information drift: adjacent pairs up to 6 pairs, `abs(active_mi - baseline_mi)/(abs(baseline_mi)+1)` (`temporal_math.py:257-281`).
- Relationship drift: `correlation_drift * 0.7 + mutual_information_drift * 0.3` (`temporal_math.py:65-67`).
- Lag relationship drift: best absolute correlation lag shift divided by `max_lag=8` (`temporal_math.py:284-310`).
- Regime shift: change points where right-window mean exceeds left-window mean by >0.12; score `min(point_count,3)/3` (`temporal_math.py:313-324`).
- Topology propagation: `lag * 0.65 + regime_shift * 0.35` (`temporal_math.py:327-330`).
- Evidence score: active indicator fraction * 0.7 + mean evidence values * 0.3; trigger default 0.15 (`temporal_math.py:333-347`).
- Confidence: `0.15 + evidence_score*0.45 + sufficiency*0.25 + consistency*0.15`, where sufficiency is `(sample_count/240)*0.7 + (feature_count/24)*0.3` clipped (`temporal_math.py:350-372`).
- Temporal instability index: `state_drift*.26 + relationship_drift*.15 + entropy*.14 + variance*.16 + acceleration*.11 + causal_evidence*.13 + topology*.05` (`temporal_math.py:375-394`).
- Decision state: Normal/Watch/Investigate/Act/Critical thresholds at 0.32, 0.52, 0.70, 0.85 with persistence and active-indicator guardrails (`temporal_math.py:397-412`).

Plain English: this file is real math, but it is not the current CSV upload result path observed in `_build_csv_result`.

## 6. Evidence Generation

### What Changed

Relationship changes come from top relationship candidates in `relationship_baselines.py:135-158`. Column changes come from `baseline_analysis.column_drift` (`baseline_analysis.py:74-84`). Evidence variables are selected by `_observation_variables_from_result`: relationship columns first, then column drift columns, deduped and capped at 16 (`upload_jobs.py:650-672`).

Plain English: evidence variables are not selected by contribution attribution from the runner; they are selected from relationship and column-drift records.

### Why It Matters

`why_flagged` is the first supporting evidence line when available (`sii_intelligence.py:199-203`). Supporting evidence itself is generated by driver attribution scoring (`driver_attribution.py:113-136`) or operator report observations when attribution is missing (`sii_intelligence.py:199`).

Driver attribution points are heuristic:

- review column drift: +3; watch: +1.5; persistent: +2 (`driver_attribution.py:153-163`)
- relationship change over 0.5: +1.5 to related categories (`driver_attribution.py:179-199`)
- selected pair-category bonuses: +1 or +2 (`driver_attribution.py:202-216`)
- timestamp/data quality/missing values: +0.75 to +2 (`driver_attribution.py:218-249`)
- top attribution requires score >=3, at least 2 evidence items, and corroboration (`driver_attribution.py:117-136`)

Plain English: “why it matters” is deterministic scoring and templated text, not causal proof.

### Replay Frames

Replay frames are sampled by row position and use top relative deviations from an early baseline (`upload_jobs.py:1347-1404`). The final frame includes relationship-change summaries and evidence refs if any relationship model changes exist (`upload_jobs.py:1400-1404`).

### Findings Ranking

Relationship findings are ranked by `(correlation_delta, coupling_strength)` descending and capped at 5 (`relationship_baselines.py:156-158`). Evidence runs are sorted by `(created_at, run_id)` descending in list views (`evidence_store.py:245-264`). Observation Center filters and displays these records; it does not re-rank by risk math (`ObservationCenterWorkspace.jsx:459-500`).

### Persisted Fields

Upload result and summary are persisted to runtime JSON/shared state (`upload_jobs.py:1195-1208`). Latest SII state is written by `write_latest_sii_state` (`sii_runner.py:635-652`). Evidence runs are upserted at upload completion (`upload_jobs.py:1213-1249`) and stored by `upsert_evidence_run` (`evidence_store.py:58-67`).

Evidence record fields include run metadata, row counts, variables, data conditions, primary drivers, evidence summary, observation type/status, drift metrics, structural state, deformation start, and historical fact (`upload_jobs.py:715-788`, `evidence_store.py:256-308`).

## 7. UI Mapping

### Gate State

The gate uses `system_interpretation` when present. `SystemBodyWorkspace` maps:

- Current State: `system_interpretation.facility_state_label` (`SystemBodyWorkspace.jsx:313-335`, displayed at `SystemBodyWorkspace.jsx:208`, `227`)
- Current Reading: `system_interpretation.relationship_summary.text` or `relationship_divergence.summary` or `state_derivation_reason` (`SystemBodyWorkspace.jsx:317-330`, displayed at `SystemBodyWorkspace.jsx:209`)
- Evidence Confidence: `system_interpretation.confidence` (`SystemBodyWorkspace.jsx:324`, displayed at `SystemBodyWorkspace.jsx:210`)
- Primary driver/focus: `system_interpretation.primary_driver` (`SystemBodyWorkspace.jsx:325-326`, passed at `SystemBodyWorkspace.jsx:223`)

If no backend `system_interpretation` exists, the component displays fallback text such as “Processing Upload” or “Awaiting Interpretation” (`SystemBodyWorkspace.jsx:338-373`).

### Relationship Divergence And Confidence

Backend `system_interpretation` computes relationship divergence from `baseline_analysis.top_relationship_changes` or replay frame changes (`system_interpretation.py:128-153`). Per relationship:

```text
confidence_score =
  min(1, baseline_n/24)*30
  + min(1, recent_n/12)*20
  + min(1, abs(coupling_strength))*20
  + min(1, abs(correlation_delta))*20
  + min(1, evidence_ref_columns/2)*10

relationship_drift_score =
  min(1, abs(correlation_delta))*70
  + min(1, abs(coupling_strength))*30
```

Reference: `system_interpretation.py:97-125`.

Severity labels:

```text
critical >= 85
high >= 65
elevated >= 35
contained otherwise
```

Reference: `system_interpretation.py:79-87`.

Confidence labels:

```text
high >= 75
moderate >= 45
low otherwise
```

Reference: `system_interpretation.py:89-95`.

Plain English: this is a display confidence for relationship divergence, not the same as runner confidence.

### What Changed / Why It Matters / Review Next / Supporting Evidence

These labels are not all visible in one component in the current code, but backend fields are:

- What changed: `sii_intelligence.primary_driver`, `relationship_evidence`, `baseline_analysis.top_relationship_changes[].summary`, and evidence record `variables`/`observation_type` (`sii_intelligence.py:255-314`, `upload_jobs.py:715-788`).
- Why it matters: `sii_intelligence.why_flagged`, generally first supporting evidence line (`sii_intelligence.py:199-203`, `sii_intelligence.py:276`).
- Review next: `sii_intelligence.recommended_operator_review`, `next_operator_move`, and `what_to_check` (`sii_intelligence.py:273-276`, `sii_intelligence.py:668-681`).
- Supporting Evidence: `sii_intelligence.supporting_evidence`, evidence record `evidence_summary`, replay frame `relationship_changes`, and `relationship_change_evidence_refs` (`upload_jobs.py:752-775`, `upload_jobs.py:1400-1404`).

Observation Center displays evidence record `evidence_summary`, `variables`, `data_conditions`, `drift_metrics`, `structural_state`, and `regime_label` (`ObservationCenterWorkspace.jsx:505-575`).

### Evidence Replay

Replay UI loads `/replay/timeline`, `/replay/{job_id}`, or embedded `latestUploadResult.replay_timeline` (`ReplayWorkspace.jsx:47-53`, `ReplayWorkspace.jsx:321-330`; replay router `replay.py:13-75`). Displayed metrics map to:

- Structure Timeline: `meta.frame_count` or timeline length (`ReplayWorkspace.jsx:214`)
- Baseline Separation: `frame.baseline_distance` or `frame.topology_state.drift_index` (`ReplayWorkspace.jsx:216`)
- Drift Velocity: `frame.drift_velocity` or `frame.subsystem_pressure.volatility_index` (`ReplayWorkspace.jsx:217`)
- Drift Acceleration: `frame.drift_acceleration` or `frame.propagation_state.propagation_acceleration` (`ReplayWorkspace.jsx:218`)
- Structural State: `frame.topology_state.stability_state` (`ReplayWorkspace.jsx:219`)
- Primary Contributors: `frame.primary_contributors` (`ReplayWorkspace.jsx:210-221`)
- Evidence confidence: `frame.cognition_state.confidence_tier` (`ReplayWorkspace.jsx:224`, `288`)

## 8. Failure And Edge Cases

- Insufficient baseline: baseline analysis returns no column drift and warning below 5 rows (`baseline_analysis.py:18-26`). Upload result marks `sii_reliable_enough_to_show` false unless baseline rows >=5, recent rows >=1, columns analyzed >=1, and evidence persisted (`upload_jobs.py:1065-1073`, `upload_jobs.py:1233-1238`).
- Noisy data: high variability warning from coefficient >0.25 (`data_quality.py:261-274`); noisy data is not smoothed.
- Sparse telemetry: per-room count <4 becomes review/insufficient telemetry (`upload_jobs.py:961-985`).
- Missing timestamps: if no timestamp column is detected, row order is used; data quality becomes `needs_review` (`data_quality.py:161-182`).
- Invalid timestamps: dropped if a timestamp column exists (`upload_jobs.py:524-529`).
- Non-numeric values: invalid numeric cells are blanked; rows remain if at least one usable numeric cell exists (`upload_jobs.py:541-555`).
- Constant columns: Pearson correlation returns `None` when denominator is zero (`relationship_baselines.py:27-39`), so relationship pair is skipped. Temporal math and runner use floors/pseudoinverse to avoid divide-by-zero.
- Very small uploads: empty or no usable rows raise errors (`upload_jobs.py:434-467`, `upload_jobs.py:562-563`); less than 20 rows uses minimal replay path but still calls the same replay builder (`upload_jobs.py:1030-1032`, `upload_jobs.py:1407-1410`).
- Very large uploads: cleaned rows are passed through to SII ingestion without an analysis-row sampling cap; relationship columns are capped at 32 and relationship baseline/recent windows at 12000/6000 rows (`relationship_baselines.py:66-98`).

## Known Limitations / Assumptions

- Current CSV upload does not call `evaluate_temporal_math`; temporal formulas exist but are not the observed upload path in `_build_csv_result`.
- No interpolation is performed despite time-series terminology.
- Baselines are early-window heuristics, not operator-confirmed normal periods.
- Runner confidence measures data completeness/history depth, not clinical/statistical certainty.
- Review window is a hardcoded operational heuristic based on risk score and urgency.
- Per-room state uses an early-vs-recent mean/variance heuristic on up to 4 numeric columns.
- Relationship detection ignores pairs with baseline correlation below 0.65, so newly emerging relationships from weak baselines can be missed.
- `sii_reliable_enough_to_show` is always initialized false and becomes true only after evidence persistence confirms and baseline reliability is true.

## What Is Not Currently Mathematical / Heuristic Only

- Driver category names, likely driver text, next operator move, and evidence sentences (`driver_attribution.py:9-53`, `driver_attribution.py:323-392`).
- Telemetry profile classification by column-name tokens (`upload_jobs.py:1413-1448`).
- Room urgency thresholds `0.08` and `0.25` from the early-vs-recent room drift heuristic (`upload_jobs.py:987-1007`).
- Review window strings and base hours (`sii_runner.py:764-780`, `sii_intelligence.py:499-533`).
- System interpretation state labels such as Cascade Risk and Structural Degradation from compound UI flags (`system_interpretation.py:186-191`, `system_interpretation.py:270-291`).
- Observation Center summaries are text templates based on observation type (`ObservationCenterWorkspace.jsx:84-102`).

## Safe Claims From Current Math

- Neraium computes cleaned-row counts, dropped-row reasons, numeric profiles, missing-value counts, and timestamp coverage from uploaded CSVs.
- It compares early baseline windows to recent windows for numeric mean drift.
- It computes Pearson correlation shifts for numeric column pairs and ranks top relationship changes by correlation delta and baseline coupling strength.
- It computes replay drift as relative deviation from early-row means and shows top contributing variables per sampled frame.
- The backend SII runner computes a covariance/Mahalanobis-based instability score when covariance is valid, with fallback normalized drift/transition/variability scoring.
- Confidence in the runner is a deterministic function of history length plus current/recent vector completeness, capped when missingness is present.

## Claims Not Yet Safe To Make

- It is not safe to claim root cause. Driver attribution is deterministic evidence ranking and templated language.
- It is not safe to claim true time-to-failure prediction. Review window is an operational triage heuristic.
- It is not safe to claim interpolation, smoothing, or resampling of telemetry.
- It is not safe to claim learned normal behavior beyond early-window baseline statistics for the uploaded dataset.
- It is not safe to claim relationship divergence is causal; it is correlation/covariance movement.
- It is not safe to claim frontend severity labels are all direct model outputs; some are display-layer thresholds and fallbacks.
