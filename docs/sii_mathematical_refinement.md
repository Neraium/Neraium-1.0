# SII Mathematical Refinement

## Scope and invariants

This refinement strengthens mathematics inside the existing Phase 1–4 SII
modules. It does not introduce a new phase, architectural layer, opaque model,
causal claim, diagnosis, prediction of failure, or maintenance recommendation.

All additions are:

- deterministic for identical inputs and configuration;
- additive to existing result contracts;
- inspectable as values, formulas, source references, and limitations;
- evaluated before any baseline or behavioral-memory write;
- non-causal and subject to human review.

## Refinement map

| Existing module | Refinement | Traceable result |
|---|---|---|
| `behavioral_graph` | weighted graph Laplacian, localized energy, weighted-degree and betweenness centrality, neighborhood consistency, structural entropy, component evolution, weighted Jaccard stability | `graph_mathematics` |
| `expected_behavior` | Theil–Sen regression with deterministic time-ordered lag selection, holdout validation, slope/intercept ranges, and residual/model/data uncertainty | model `validation`, `model_parameters`, and evaluated `uncertainty` |
| `physics_reasoning` | configured response-delay windows, expected response windows, physical tolerances, and operating-mode overrides | `reasoning_trace.response_characteristics` |
| `propagation_analysis` | per-edge lag windows, end-to-end path lag consistency, competing-path comparison, upstream/downstream candidate roles, and independent simultaneous groups | `candidate_paths.*.lag_consistency`, `change_roles`, and propagation uncertainty |
| `behavioral_evolution` | robust velocity, acceleration, curvature, baseline-distance recovery trajectory, derivative contraction, and snapshot-center trend | `temporal_characterization` and derivative/recovery/stabilization views |
| `multiscale_analysis` | deterministic scale-profile slope and direction-reversal characterization | `behavior_patterns` |
| canonical uncertainty | separate data, model, relationship, operating-context, and propagation components | `uncertainty.components` and named component aliases |
| `baseline_evolution` and `behavioral_model` | stable-evolution confirmation, active-instability exclusion, configured aging context, and robust accepted-run baseline pooling | `baseline_evolution_assessment`, learning trace, and signal `method_metadata` |

The original fields remain available. New fields do not replace legacy
compatibility values.

## Graph mathematics

For each node, the comparison defines a graph signal

```text
x_i = current weighted degree_i - active weighted degree_i
```

The comparison graph uses, for each observed edge, the larger active/current
weight. The reported Dirichlet energy is

```text
x' L x = sum over edges (i,j) of w_ij * (x_i - x_j)^2
```

The result also reports:

- one-half of each incident edge energy at each node as localized energy;
- weighted total variation;
- degree, weighted-degree, and unweighted shortest-path betweenness centrality;
- incident-edge directional consistency at each node;
- normalized Shannon entropy of weighted node degree;
- weighted Jaccard similarity and normalized L1 edge-weight change;
- deterministic connected-component split and merge counts.

This follows the graph-signal-processing principle that graph smoothness can
represent spatially structured sensor change. The implementation deliberately
does not copy the cited paper's damage classifier, KL divergence, or EWMA
detector because those would require separately validated reference
distributions and monitoring calibration. See Cheema et al.,
[Computationally-Efficient Structural Health Monitoring using Graph Signal Processing](https://doi.org/10.1109/JSEN.2024.3366346),
IEEE Sensors Journal 24(7), 2024.

## Expected behavior

The response model remains the inspectable Theil–Sen linear model:

```text
slope = median((y_j - y_i) / (x_j - x_i))
intercept = median(y_i - slope * x_i)
```

For each configured candidate sample lag, the model:

1. aligns the predictor at `t - lag` with the response at `t`;
2. fits on the earlier time-ordered segment;
3. evaluates relative median absolute error on the later holdout segment;
4. selects the smallest lag among equal minimum errors;
5. refits the selected lag on all eligible training pairs.

The persisted model contains every candidate's holdout score, the selected lag
in samples and seconds when regular timestamps support conversion, empirical
10–90% slope/intercept ranges, residual MAD scale, and residual quantiles.
Evaluation intervals combine the inspectable parameter range with empirical
residual offsets. They are not probability or causal intervals.

The pairwise-median regression basis is documented by Sen,
[Estimates of the Regression Coefficient Based on Kendall's Tau](https://doi.org/10.1080/01621459.1968.10480934),
Journal of the American Statistical Association 63(324), 1968.

Configuration remains optional:

```python
{
    "candidate_lags_samples": [0, 1, 2, 3],
    "validation_fraction": 0.20,
    "minimum_validation_samples": 5,
    "maximum_validation_relative_mad": 0.75,
}
```

## Physical response configuration

Existing priors remain valid. A prior may additionally provide condition groups
named:

```text
response_delay
expected_response_window
allowable_physical_variability
operating_mode_sensitivity
```

A delay/window condition can use the normal declarative operator contract or
the shorthand `minimum_seconds` and `maximum_seconds`. Numeric equality can use
`absolute_tolerance`, `relative_tolerance`, or a `tolerance` mapping. An
operating-mode entry may override any response group for an exact observed
mode. No delay, window, tolerance, mode rule, or engineering meaning is
hardcoded.

## Propagation mathematics

Each supported directed association carries an expected lag and allowable
window. The window is taken from the relationship's configured response window
or is constructed from the configured absolute/relative lag tolerance.

A path is retained only when every edge:

- has supported direction metadata;
- has lag evidence;
- meets configured strength, mode, and sensor-health requirements;
- preserves observed temporal precedence;
- falls inside its expected lag window.

The path reports the sum of expected edge lags, the summed allowable window,
the observed end-to-end delay, edge fit scores, and end-to-end fit. Competing
paths are ordered only to make their evidence comparable; none is selected as
causal.

Activated signals are separated into:

- earliest upstream behavioral-change candidates;
- downstream-consistent response candidates;
- independent simultaneous candidates with no supported path between them;
- unconnected activated signals.

Every role explicitly carries `causal_claim=false`.

## Temporal and multiscale mathematics

For reliable monotonic timestamps, derivatives use elapsed seconds; otherwise
they are explicitly per ordered sample. Velocity is a Theil–Sen slope with
first-difference dispersion. Acceleration and curvature are median successive
derivative rates. Each includes sample support, robust dispersion, and an
empirical 10–90% interval.

Recovery uses the Theil–Sen slope and Kendall pair concordance of absolute
normalized distance from the active baseline. Stabilization requires
contraction in both recent absolute velocity and its robust dispersion, with at
least one strict contraction. These characterize observed trajectories only;
they do not extrapolate future state.

Across eligible scales, the engine records direction reversals and the
Theil–Sen slope of normalized change magnitude. It distinguishes:

- stable across scales;
- transient events;
- persistent instability;
- gradual evolution;
- recurring or oscillatory scale patterns;
- scale-specific or row-scale-only consistency.

Row-count fallback never claims elapsed-time persistence.

## Uncertainty decomposition

The canonical uncertainty section preserves its legacy fields and adds five
independent components:

```text
data_uncertainty
model_uncertainty
relationship_uncertainty
operating_context_uncertainty
propagation_uncertainty
```

Each component has its own status, source references, traceable metrics, and
limitations. Components are not weighted, averaged, or converted to
probability.

## Baseline evolution

Before learning, the existing baseline gate now classifies the observed
context as one of:

- stable baseline context;
- stable evolution candidate;
- behavioral drift or active instability;
- temporary operational change;
- configured infrastructure-aging context;
- indeterminate baseline change.

Infrastructure aging is never inferred from telemetry alone. It can only be
reported as configured context when a caller identifies explicit engineering
prior IDs in `infrastructure_aging_prior_ids`; it remains non-diagnostic.

A stable evolution candidate requires repeated accepted/deferred evidence
before activation, with a default minimum of two runs. Active residuals,
structural graph change, temporal instability, conflicting scales, poor data,
sensor limitations, or incompatible operating context prevent learning.

After all gates pass, historical signal center and scale use square-root
sample-weighted medians of accepted run summaries. Scale is the larger of the
weighted within-run robust scale and robust between-run center dispersion.
Rejected, deferred, unstable, or unvalidated observations are not pooled into
the active baseline.

## Validation

Focused regression coverage is in
`tests/test_sii_mathematical_refinement.py`. It verifies:

- exact Laplacian behavior for coordinated graph change;
- deterministic recovery of a known two-sample response lag;
- configured delay, variability, and mode-sensitive prior evaluation;
- path lag consistency and independent simultaneity;
- recovery-trajectory derivative evidence;
- transient, gradual, and recurring multiscale profiles;
- separate uncertainty lineage;
- repeated confirmation before stable baseline evolution.

The existing Phase 2–4, robustness, pipeline, and compatibility suites remain
the backward-compatibility authority.
