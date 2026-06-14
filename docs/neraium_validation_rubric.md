# Neraium Validation Rubric

Neraium should be evaluated as a structural intelligence and interpretation engine, not as a conventional predictive-maintenance platform.

## Correct Evaluation Frame

The core question is not whether Neraium can forecast a specific component failure months in advance. The current system is designed to:

- detect change in telemetry behavior
- detect relationship drift between signals
- identify structural divergence from a learned baseline
- surface anomalies that would be difficult to notice manually
- explain what changed, why it matters, and what evidence supports the observation

Predictive capability should therefore be marked `unknown` unless a test explicitly measures future-event prediction against labeled outcomes. It should not be scored as poor simply because the product is not primarily a long-horizon failure forecaster.

## Separate Scores

Use separate maturity scores instead of one blended platform grade.

| Category | Current evidence basis | Suggested status |
|---|---|---|
| Core SII concepts | structural drift, relationship drift, baseline divergence, instability scoring | promising, needs broader validation |
| Mathematical sophistication | covariance/Mahalanobis scoring, relationship baselines, temporal and drift metrics | moderate to strong prototype |
| Explainability | operator-facing summaries, confidence, driver attribution, evidence lineage | current differentiator |
| Detection capability | regression tests for stable, noisy, missing, and progressive degradation cases | partially validated |
| Predictive capability | requires labeled future failure or intervention outcome datasets | unknown |
| Production readiness | deployment, monitoring, security, failover, and operational hardening | early beta |
| Industrial robustness | requires the full stress-test matrix across messy, noisy, large, and heterogeneous telemetry | not fully proven |

## Evidence Rules

No evidence is not the same thing as negative evidence.

- Mark untested capabilities as `unknown`, not `poor`.
- Score production readiness separately from intelligence quality.
- Treat enterprise IoT platforms as deployment-maturity comparators, not core-intelligence comparators.
- Require real or synthetic stress tests before making claims about messy-data tolerance.
- Preserve false-positive and false-negative results separately, because high sensitivity without calibration is not the same as reliable intelligence.

## Validation Priority

The highest-value next proof is a robustness matrix that measures:

- missing values and null cells
- corrupted or malformed rows
- noisy but stable telemetry
- sensor dropouts and stuck sensors
- out-of-order, duplicate, and irregular timestamps
- heterogeneous rooms or assets with different sensor coverage
- scale from small files to million-row uploads
- false-positive rate on stable operating regimes
- true-positive rate on injected drift, relationship collapse, covariance shift, and progressive degradation

Until that matrix is regenerated after the current calibration fixes, Neraium should be described as an evidence-backed structural intelligence prototype with promising core behavior and incomplete industrial validation.
