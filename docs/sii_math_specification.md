# SII Mathematical Specification

## Scope and notation

This specification describes Phase 1 as implemented by `evaluate_sii`. It records existing formulas without claiming physical causation. Unless stated otherwise, a baseline window is earlier in row order and an active/recent window is later in row order. Upload parsing sorts usable timestamps first when timestamps are available; absent reliable timestamps, row order is not elapsed time.

Notation:

- `x_i`: value of one signal at row `i`.
- `x̄_B`, `x̄_A`: baseline and active means.
- `s`, `σ²`: population standard deviation and variance as used by the implementation.
- `clip(z,a,b)`: bound `z` to `[a,b]`.
- `r_B`, `r_A`: baseline and active Pearson correlations.
- `n_B`, `n_A`: paired baseline and active sample counts.
- `ε`: numeric floor specified for the formula.

All confidence outputs in this document are deterministic heuristic scores or qualitative sufficiency bands. They are not posterior probabilities.

## Component status summary

| Component | Status | Primary implementation | Minimum |
|---|---|---|---|
| Signal drift | Active | `services/baseline_analysis.py` | 5 input rows; usable values in both windows |
| Cumulative-counter delta | Active | `services/cumulative_counters.py` | 8 numeric samples for detection; 3 deltas per drift window |
| Pearson relationship graph | Active | `services/relationship_baselines.py` | 12 rows, 2 eligible columns, 3 paired values per window |
| Relationship importance | Active | `services/relationship_baselines.py` | A comparable Pearson edge |
| Operating-mode assessment | Active contextual annotation | `services/operating_modes.py` | 2 rows; explicit features for non-limited result |
| Sensor health/data confidence | Active contextual adjustment | `services/sensor_health.py` | Rule-specific |
| Fixed persistence | Active | `engine/analysis.py` | 3 recent rows |
| Covariance/Mahalanobis | Active | `services/sii_runner.py` | 8 baseline vectors and baseline completeness ≥ 0.65 |
| Temporal math | Active | `engine/temporal_math.py` | Default 16 usable rows, 1 numeric feature; pair metrics need 2 features |
| Multiscale analysis | Planned Phase 2 | — | Not active |
| Learned thresholds | Planned Phase 2 | — | Not active |
| Physics priors | Planned Phase 3 | — | Not active |
| Candidate propagation paths | Planned Phase 3 | — | Not active; temporal topology scalar remains active |
| Evidence fusion | Planned Phase 3 | — | Not active; existing composites remain separate |
| Behavioral digital model | Planned Phase 4 | — | Not active |

## Input and missing-value behavior

`evaluate_sii` accepts dictionary rows or matrix rows and creates both views without changing values. Numeric eligibility comes from `numeric_profiles` or the explicit internal `config.numeric_columns` list.

- Baseline drift skips missing, non-numeric, and non-finite cells separately in each window.
- Pearson relationships use pairwise-complete observations. A pair needs at least 3 observations in each window.
- Temporal math retains any row with at least one numeric value, then replaces missing cells with that column's matrix mean. An all-missing column mean becomes `0`.
- Runner vectors retain partially missing rows as `NaN`; all-missing vectors are excluded. NaN-safe fallback calculations are used. For covariance matrices and current covariance vectors, missing values are converted to `0` after completeness has been measured.
- No analytical result converts row counts to elapsed duration when timestamps are unavailable or irregular.

## 1. Signal drift

### Windows and adaptive baseline

For `N ≥ 5` rows:

```text
W_B = min(100, max(1, floor(N/2)))
W_A = min(100, N - W_B)
```

The active window is the last `W_A` rows. Candidate baseline windows of length `W_B` are searched before the active window. For signal `j` in candidate window `w`:

```text
stability_j(w) = std_j(w) / max(|mean_j(w)|, 1)
stability(w) = mean_j(stability_j(w))
```

The lowest-variability candidate is selected. Returned display stability is `1 / (1 + stability(w))`.

Inputs: numeric-profile columns and matrix rows. Output: baseline bounds and per-signal drift. Minimum: 5 rows. Missing values are skipped. Limitation: selection is row-based, unconditioned by operating mode in Phase 1, and a low-variability period is not necessarily a physically normal period.

### Mean and absolute drift

```text
absolute_change = x̄_A - x̄_B
```

### Percent drift with a near-zero guard

Baseline denominator floor:

```text
floor_B = max(10^-6, 0.25 * std_B, 0.05 * mean(|x_B|))
```

Then:

```text
percent_change = 100 * absolute_change / |x̄_B|, if |x̄_B| ≥ floor_B
percent_change = null, otherwise
```

### Standardized change

For combined baseline and active values:

```text
standardized_change = |absolute_change| / max(std(B ∪ A), 10^-6)
```

### Direction and flag

```text
direction_floor = max(0.01 * |x̄_B|, 0.01)
direction = up    if absolute_change > direction_floor
          = down  if absolute_change < -direction_floor
          = flat  otherwise
```

When percent change exists: `review` at `|percent_change| ≥ 20`, `watch` at `≥ 10`, otherwise `normal`. When percent change is unavailable: `review` at standardized change `≥ 3` with non-flat direction; `watch` at standardized change `≥ 1.5` or absolute change `> 0.01`; otherwise `normal`.

These flags are behavioral thresholds, not physical alarms.

### Slope, velocity, and acceleration

For values indexed `i=0..n-1`, ordinary least-squares slope is:

```text
slope(x) = Σ(i-ī)(x_i-x̄) / Σ(i-ī)^2
```

```text
drift_velocity = slope(active)
drift_acceleration = slope(active) - slope(baseline)
```

These derivatives are per row, not per unit time.

### Baseline signal persistence

```text
tolerance = max(0.05 * |x̄_B|, 0.05)
persistence_score = count(|x_A - x̄_B| > tolerance) / n_A
```

The trajectory summary labels an active signal persistent at score `≥ 0.6` and accelerating when `|drift_acceleration| > 0.01`. This summary does not establish elapsed duration.

### Cumulative counters

A column is treated as cumulative only if its name matches a counter/totalizer hint, it has at least 8 numeric samples, net change is positive, at least one step is positive, at least 98% of adjacent steps are nonnegative within `10^-9`, and it is not constant.

```text
delta_t = x_t - x_(t-1), if both exist and delta_t ≥ 0
delta_t = missing, otherwise
```

The raw counter is excluded from structural relationships. A derived `<column>_delta` feature is used only with at least 6 usable deltas; drift output needs at least 3 deltas in each comparison window. Negative reset steps are missing, not evidence.

## 2. Pearson relationship analysis and graph

### Windows and bounds

```text
split = max(6, floor(0.70 * N))
baseline = rows[0:split]
active = rows[split:N]
```

Baseline rows are capped at 12,000, active rows at the latest 6,000, and eligible relationship columns at the first 32 in source order. Sampling/column limiting is reported. Cumulative counters, ignored categories, and non-operator relationship categories are excluded; eligible counter deltas may be added.

### Pearson correlation

For pairwise-complete values:

```text
r = Σ(x_i-x̄)(y_i-ȳ) / sqrt(Σ(x_i-x̄)^2 * Σ(y_i-ȳ)^2)
```

If either spread is zero, the pair is unavailable. Each window needs at least 3 paired values.

### Edge measurements

```text
baseline_strength = |r_B|
current_strength = |r_A|
correlation_delta = |r_A - r_B|
signed_correlation_delta = r_A - r_B
change_percentage = 100 * (current_strength - baseline_strength) / baseline_strength
```

`change_percentage` is null when baseline strength is `≤ 10^-9`.

Direction is `inverted` for opposite signs when both strengths are at least `0.25`; otherwise `positive` at `r_A ≥ 0.1`, `negative` at `r_A ≤ -0.1`, and `weak_or_flat` otherwise.

### Change classification

- `disrupted`: sign flip and both strengths `≥ 0.35`.
- `missing`: baseline strength `≥ 0.65` and current strength `< 0.35`.
- `weakened`: baseline strength `≥ 0.65` and current strength is at least `0.25` lower.
- `new`: current strength `≥ 0.65` and baseline strength `< 0.35`.
- `strengthened`: current strength is at least `0.25` higher.
- `stable`: otherwise.

Promotion additionally requires `correlation_delta ≥ 0.25`, operator-primary eligibility, and conservative strength gates: baseline `≥ 0.65` for disrupted/missing/weakened; baseline `≥ 0.5` and current `≥ 0.65` for strengthened; current `≥ 0.75` for new.

### Edge confidence

```text
sample_factor = min(1, min(n_B,n_A) / 12)
change_factor = min(1, correlation_delta / 0.75)
confidence = max(0.2, 0.65 * sample_factor + 0.35 * change_factor)
```

Band is high at `≥ 0.75`, moderate at `≥ 0.45`, limited otherwise. This score is not a probability or significance test.

### Relationship importance

Factors are bounded to `[0,1]`:

```text
magnitude = min(1, correlation_delta)
confidence = edge confidence
persistence = min(1, min(n_B,n_A)/24)
downstream_scope = min(1, 0.35*number_of_inferred_system_labels + 0.15*number_of_columns)
severity = maximum signal/name heuristic for the two columns, default 0.35
novelty = 1.0 disrupted/missing/new; 0.8 weakened/strengthened; 0.2 stable; 0.55 otherwise
data_quality = min(confidence, max(0.2, persistence))
equipment_process = 1.0 when equipment/process involved, otherwise 0.25
```

```text
raw = 0.22*magnitude + 0.16*confidence + 0.12*persistence
    + 0.10*downstream_scope + 0.16*severity + 0.09*novelty
    + 0.08*data_quality + 0.07*equipment_process
importance = 100 * raw * context_factor
```

`context_factor` is `0.35` for context-only, `0.82` when a context driver is involved, and `1.0` otherwise. Context-only scores are capped at `34`. The importance value ranks evidence; it is not physical criticality.

### Graph output

Nodes represent eligible metrics plus optional inferred system-label nodes. Metric-to-metric edges contain the Pearson fields, paired counts, source anchors, operating-mode context, sensor-health context, and data-confidence context. The graph is explicitly non-causal. Phase 1 returns edge classifications but does not calculate changed-edge fraction, connected changed components, degree changes, or subsystem concentration; those are Phase 2.

## 3. Operating-mode context

The assessor uses the same 70/30 row split and at most 12,000 baseline plus 6,000 active rows. It recognizes interpretable header/classification roles: maintenance, cleaning, setpoint, equipment state/stage, valve state, speed, load/occupancy, environment, schedule, and special events.

Numeric band boundaries are empirical one-third and two-third order-statistic positions over the combined context rows. Each window's median is labeled low/typical/high. Discrete states use deterministic majority with lexical tie breaking. Timestamps add day/night (`06:00–17:59` is day) and weekday/weekend context.

Mode match is:

- `strong`: no feature differences.
- `weak`: any state-role difference, or all explicit features differ.
- `partial`: some but not all explicit features differ without the weak rule.
- `unavailable`: no shared explicit feature.

Confidence is high with at least 2 shared explicit features and limited with 1. Phase 1 attaches this context to relationships but does not reselect a mode-conditioned baseline. Therefore an operating-mode difference can bound interpretation but does not alter Pearson or signal-drift formulas.

## 4. Data quality, sensor health, and telemetry confidence

### Data-quality score

The score begins at 100. It subtracts 12 without timestamps; 30 for fewer than 12 rows or 12 for fewer than 50; up to 28 from drop ratio; up to 18 for rows with missing values; up to 14 for invalid numeric rows; 8 for irregular sampling; up to 18 for stuck sensors (`6` each); 16 for an unreliable baseline; and 16 for a normalization-suppressed window. The result is clipped to `[0,100]`.

Bands: strong `≥82`, usable `≥62`, weak `≥40`, not reliable otherwise. These are deterministic quality ratings.

### Sensor-health rules

Active rules preserve existing outputs:

- constant non-state profile → `flatline_or_stuck`;
- normalization completeness `<0.8` → sparse baseline coverage;
- repeated run with at least 8 values, more than one distinct value, and run length `≥max(8, 0.5n)` → frozen precision;
- abrupt step with at least 10 values and maximum adjacent change `> max(10*median(nonzero steps), 4*median absolute deviation from the median), 10^-9)` → abrupt-step limitation;
- strong peer baseline (`|r_B|≥0.8`) with at least 6 pairs per window may produce gradual residual-shift context when linear residual trend has `R²≥0.85` and sufficient span;
- recent zero-lag vs lags `±1..±3` can mark timestamp misalignment when baseline `|r_B|≥0.7`, at least 10 pairs exist, best lag magnitude is `≥0.75`, and improvement is `≥0.25`.

Sensor conditions do not alter Pearson coefficients or ranking order. They add context and lower qualitative data confidence. Sparse coverage forces low; other conditions impose at most limited. No condition diagnoses sensor failure.

### Upload intelligence cap

When normalization suppresses a window, existing presentation confidence and Neraium score are capped at 55 and telemetry integrity is marked reduced. This applies to the compatibility/presentation layer and does not mutate analytical component values.

## 5. Fixed persistence

### Row-support persistence

For each non-normal drift direction, over at least 3 recent rows:

```text
threshold = max(0.01 * |x̄_B|, 0.01)
support = count(x_A > x̄_B + threshold) for upward drift
support = count(x_A < x̄_B - threshold) for downward drift
support_percent = 100 * support / usable_recent_rows
persistent = support_percent ≥ 70
```

This is a row-count gate. It does not claim elapsed persistence when sampling is irregular or unknown.

### Covariance distance persistence and accumulation

For the latest distance history window:

```text
dynamic_threshold = mean(distance_history) + std(distance_history)
persistence_condition = at least 3 distances above dynamic_threshold
accumulation = Σ distance_window
accumulation_condition = len(distance_window) ≥ 3 and accumulation ≥ 3*dynamic_threshold
corroborated = persistence_condition and accumulation_condition and structural_drift_score ≥ 0.08
```

Adaptive persistence is not active; Phase 1 returns these preserved gates and the fixed row-support view separately.

## 6. Covariance and Mahalanobis analysis

The upload runner window is `min(50, max(2, min(48, retained_vector_count//2 or 2)))` for both baseline and recent capacities. Its rolling history holds at most the sum of those capacities.

### Fallback motion measures

```text
safe_baseline_j = 1 if |mean_B,j| < 10^-6 else |mean_B,j|
fallback_drift = clip(mean_j(|mean_A,j - mean_B,j| / safe_baseline_j), 0, 1.5)
fallback_transition = clip(mean_j(|x_t,j - x_(t-1),j| / safe_baseline_j), 0, 1.5)
fallback_variability = clip(nanstd(active_matrix) / max(mean(safe_baseline),1), 0, 1)
fallback_score = clip(0.55*fallback_drift + 0.30*fallback_transition
                      + 0.15*fallback_variability, 0, 1)
```

### Regularized covariance

Covariance uses population normalization (`bias=True`). Let `v` be the mean of positive covariance diagonal entries, or `1` if none:

```text
λ = max(0.05*v, 0.001)
Σ_reg = Σ + λI
```

A covariance pass needs at least 8 baseline rows and baseline completeness at least `0.65`. Pseudoinverse is used.

### Mahalanobis distance and baseline limit

```text
d_M(x) = sqrt(max((x-μ_B)^T pinv(Σ_reg) (x-μ_B), 0))
limit = max(mean(d_M(B)) + 3*std(d_M(B)), 1)
excess = max(0, d_M(x_t) - limit)
structural_drift_score = clip(excess / limit, 0, 1)
```

If fallback drift `<0.08` and covariance shift `<0.8`, structural drift is reset to `0`.

### Covariance shift, motion, and curvature

```text
covariance_shift = ||Σ_A,reg - Σ_B,reg||_F / max(||Σ_B,reg||_F, 10^-6)
drift_velocity = d_M(t) - d_M(t-1)
drift_acceleration = drift_velocity(t) - drift_velocity(t-1)
trajectory_curvature = clip(|drift_acceleration| / max(|drift_velocity|,10^-6), 0, 1)
```

These motion values are per ingested row, not per unit time.

### Technical runner score

With `motion_gate = max(structural_drift_score, 0.25*min(covariance_shift,1))` only when corroborated (otherwise the second term is zero):

```text
technical = clip(
  0.45*structural_drift_score
  + 0.20*min(|velocity|,1)*motion_gate
  + 0.15*min(|acceleration|,1)*motion_gate
  + 0.15*min(covariance_shift,1)*(1 if corroborated else 0.25)
  + 0.05*min(curvature,1)*motion_gate,
  0, 1)
```

Technical score is capped at `0.19` unless both persistence and accumulation pass. If not corroborated and fallback drift `<0.08`, adjusted fallback is capped at `0.20`. Final runner instability is `max(0.35*adjusted_fallback, technical)` when covariance is valid, otherwise the fallback score.

Regime thresholds: warmup for fewer than 3 vectors; LOCK_IN/CRITICAL at instability `≥0.72` or transition pressure `≥0.9`; UNSTABLE/ALERT at `≥0.52` or `≥0.62`; TRANSITION/WATCH at `≥0.24` or `≥0.28`; stable otherwise.

### Legacy runner instability index

This separately preserved presentation index uses drift `D`, transition/relationship `R`, covariance-shift/entropy proxy `E`, confidence-weighted runner score `C`, and topology proxy `T`:

```text
C = clip(runner_confidence,0,1) * clip(runner_instability,0,1)
T = clip(0.7*covariance_shift + 0.3*trajectory_curvature,0,1)
index = clip(0.35D + 0.25R + 0.15E + 0.15C + 0.10T,0,1)
```

The legacy component name `causal_evidence` is retained for compatibility; the value is not causal evidence and the canonical engine makes no causal claim.

## 7. Temporal analysis

Default component configuration: baseline fraction `0.35`, minimum baseline rows `12`, maximum rows `5,000` (latest rows), maximum lag `8`, evidence trigger `0.15`. The upload adapter sets the existing configurable `max_rows` input to `2,048` to keep bounded upload runtime; direct entrypoint callers retain the component default unless they supply a config. Default minimum usable history is `16` rows. Baseline count is `max(12, floor(0.35N))`, clamped to `[4,N-2]`.

### State drift

For active row `t` and feature `j`:

```text
s_j = 1 if std_B,j < 10^-6 else std_B,j
z_t,j = |x_t,j - mean_B,j| / s_j
state_drift_t = clip(mean_j(z_t,j) / 4, 0, 1)
```

### Variance growth

Rolling active window is `max(6, min(24, active_rows//3))`:

```text
baseline_variance_j = max(var_B,j, 10^-6)
ratio_t,j = var(active_window_t,j) / baseline_variance_j
variance_growth_t = clip(mean_j(max(ratio_t,j-1,0)) / 3, 0, 1)
```

### Entropy growth

Each column uses a 12-bin histogram and Shannon entropy:

```text
H(x) = -Σ p_k log2(p_k + 10^-12)
H_B = max(mean_j(H(B_j)), 10^-6)
entropy_growth_t = clip(max(mean_j(H(active_window_t,j))-H_B,0)/(H_B+1),0,1)
```

### Temporal Pearson drift

For at least 2 features, baseline and rolling active correlation matrices are compared. Active correlation requires at least 3 rows. Rolling window is `max(8,min(32,active_rows//2))`:

```text
correlation_drift_t = clip(nanmean(|R_t - R_B|) / 1.5, 0, 1)
correlation_drift_score = mean_t(correlation_drift_t)
```

### Mutual information drift

For up to 6 adjacent feature pairs, 10-bin two-dimensional histograms estimate:

```text
MI(X,Y) = Σ p_xy log2(p_xy/(p_x p_y + 10^-12) + 10^-12)
delta_pair = |MI_A - MI_B| / (max(|MI_B|,10^-6) + 1)
MI_drift = clip(mean(delta_pair),0,1)
```

The temporal relationship score is:

```text
relationship_drift = clip(0.7*correlation_drift + 0.3*MI_drift,0,1)
```

This is a descriptive histogram estimator, not a calibrated independence test.

### Lag relationship drift

Only the first two temporal features are used. For lags `-8..8`, the best lag maximizes absolute Pearson correlation with at least 4 aligned samples:

```text
lag_shift = best_lag_A - best_lag_B
lag_drift = clip(|lag_shift|/8,0,1)
```

Lag sign is temporal ordering evidence only, not causality.

### Regime-change score

For a state-drift series of at least 10 values, `w=max(4, floor(n/10))`. A point is recorded when the mean of the following `w` values exceeds the preceding `w` mean by more than `0.12`. At most five points are returned:

```text
regime_score = clip(min(number_of_points,3)/3,0,1)
```

### Existing topology-propagation scalar

```text
topology_propagation = clip(0.65*lag_drift + 0.35*regime_score,0,1)
```

This is a two-component scalar and does not represent a path or cause. Phase 3 propagation analysis is inactive.

### Rate of change

For state drift `d` with at least 3 active values:

```text
velocity = d[-1] - d[-2]
acceleration = (d[-1]-d[-2]) - (d[-2]-d[-3])
```

Again, units are per row.

### Temporal evidence accumulation

The vector includes state drift, relationship drift, variance growth, entropy growth, absolute acceleration, MI drift, lag drift, and regime shift. Topology is excluded from the active-count denominator.

```text
active = count(component ≥ 0.15)
persistence_hits = count(component ≥ 0.22)
persistence = persistence_hits / number_of_components
accumulation_score = clip(0.7*active/number_of_components
                          + 0.3*mean(components),0,1)
```

### Temporal consistency and confidence

```text
consistency = clip(1 - (std(components)/(mean(components)+10^-6))/2,0,1)
sufficiency = clip(0.7*N/240 + 0.3*feature_count/24,0,1)
confidence = clip(0.15 + 0.45*accumulation_score
                  + 0.25*sufficiency + 0.15*consistency,0,1)
```

Confidence band is high at `≥0.8`, medium at `≥0.6`, low otherwise. It is not probability.

### Temporal instability index

```text
I = 0.26*state_drift
  + 0.15*relationship_drift
  + 0.14*entropy_growth
  + 0.16*variance_growth
  + 0.11*|acceleration|
  + 0.13*temporal_confidence
  + 0.05*topology_propagation
```

All components and the result are clipped to `[0,1]`. The compatibility label `causal_evidence` holds temporal confidence and does not mean causality.

Decision guardrails preserve existing thresholds: persistence `<0.28` or fewer than 2 active indicators prevents escalation above Watch; Critical requires index `≥0.85`, at least 4 active indicators, persistence `≥0.55`; Act requires `≥0.70`, at least 3, persistence `≥0.42`; Investigate requires `≥0.52`, at least 2, persistence `≥0.32`; Watch begins at `0.32`.

### Lead-time compatibility output

The temporal engine forms `0.45*state_drift + 0.30*relationship_series + 0.25*entropy_series`, finds the first active row at `≥0.22`, and returns rows from that point to the current row plus its source timestamp when available. This is an onset-location heuristic. It is not an estimate of time to equipment failure.

The runner's older `projected_time_to_failure*` keys are compatibility aliases for a conditional review window. They do not represent a failure prediction and are excluded from new terminology.

## 8. Fusion and findings in Phase 1

There is no cross-module SII fusion formula in Phase 1. Signal, relationship, covariance, temporal, operating-context, health, and persistence outputs remain separately traceable. Existing runner and temporal internal composites are preserved under their own module names.

Canonical `findings` is empty in Phase 1. Existing frontend condition/finding generation remains in the compatibility presentation contract and retains its current persistence/evidence guards. Phase 3 will add a documented deterministic fusion method before canonical finding generation is activated.

## Limitations common to active components

- Most derivatives and persistence gates are row-based, not time-normalized.
- Pearson detects linear association and is non-causal.
- Histogram MI depends on binning and sample size.
- Lag ordering is non-causal and currently limited to the first two temporal features.
- Mode assessment annotates but does not condition the baseline in Phase 1.
- Covariance missing values are zero-filled after a completeness gate.
- Heuristic thresholds have not been learned from historical false-positive distributions.
- No current component is a physics simulation, digital twin, calibrated probability, root-cause model, repair recommender, or exact failure-time predictor.
