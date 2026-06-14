# Platform Strengthening Plan

## Objective

Move Neraium from usable beta toward industrial-grade telemetry intelligence by making uploads resilient to messy source data, requiring persisted evidence for operational claims, calibrating confidence against data quality, and enforcing performance guardrails.

## Reliability Contract

- Uploads must not crash on missing values, duplicate or unsorted timestamps, irregular sampling, bad numeric fields, constant sensors, sparse telemetry, or large files.
- Every upload must emit a data-quality report with rows received, rows used, rows dropped, drop reasons, quality counts, reliability score, and reliability rating.
- SII findings are displayable only when the baseline is reliable and evidence persistence succeeds.
- Confidence must be capped by reliability rating, baseline rows, sparse rows, row-drop ratio, irregular sampling, and evidence count.
- Findings must link to telemetry source rows, variables, baseline/recent windows, and drift or relationship-change metrics.

## Implemented In This Pass

- Added `reliability_score`, `reliability_rating`, and structured `quality_metrics` to `data_quality`.
- Added constant/stuck sensor detection to numeric profiles.
- Added source-row and timestamp anchors to relationship evidence.
- Persisted source-row anchors in evidence records.
- Added upload-intelligence fields for `what_changed`, `why_it_matters`, `review_next`, `data_quality_warning`, and `reliability_rating`.
- Added confidence caps for weak data quality, weak baselines, sparse telemetry, high row-drop ratios, irregular sampling, and missing evidence.
- Added frontend claim-support normalization so unsupported SII claims are not marked renderable without both reliability and persisted evidence.
- Added backend robustness and benchmark tests covering messy data, evidence reliability, stable/noisy data, missing data, drift, relationship collapse, dropout, 10k rows, 100k rows, and gated 1M rows.

## Benchmark Targets

| Upload size | Default target | Test behavior |
|---|---:|---|
| 10k rows | <= 20s | Runs in default benchmark matrix |
| 100k rows | <= 60s | Runs by default |
| 1M rows | <= 300s | Runs when `NERAIUM_RUN_1M_BENCHMARK=1` |

The 1M guard is intentionally opt-in for normal CI because it creates a large in-memory synthetic CSV. Release validation should run it before production deployments.

## Remaining Hardening Work

- Move synthetic benchmark generation to streaming temp files so the 1M guard can run without holding the full CSV in memory.
- Add per-room baseline models when rooms have different sensor availability or different operating schedules.
- Add an explicit noise model so high stable noise lowers confidence without becoming structural drift.
- Add persisted evidence deep links from UI panels to exact source-row windows.
- Add longitudinal benchmark history so runtime and memory regressions are trended, not just threshold checked.
