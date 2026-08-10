# Dataset processing performance

## Scope and guarantees

This work profiles and optimizes the existing baseline-creation and comparison-analysis paths. It does not change finding policy, finding wording, evidence values, classifications, confidence, persistence decisions, mode matching, operator guidance, or SII output. The optimized and reference paths are compared after removing only runtime metadata and internal performance reports.

Performance data is stored under `processing_trace.performance` for internal diagnostics and tests. It is not added to the normal operator UI and contains counts and timings only, never raw telemetry, signal names, or values. Trackers and numeric caches are created per job and retain a strong reference to their exact row collection, so reuse cannot cross datasets, jobs, attempts, facilities, systems, or baselines.

## Profiling methodology

The initial profile used a deterministic 3,000-row historian workload with 24 process signals plus one operating-state signal. It exercised the real baseline learning and SII comparison modules. Wall and process CPU durations were captured per stage; `cProfile` was then used to attribute repeated calls inside the leading stages. The same workload and output were evaluated before and after each optimization.

The reproducible benchmark runner provides three scaling cases:

| Case | Rows | Process signals |
| --- | ---: | ---: |
| Small | 240 | 6 |
| Medium | 1,200 | 14 |
| High-signal | 3,000 | 24 |

Run all cases from the repository root:

```bash
.venv/bin/python scripts/benchmark_dataset_processing.py --iterations 3 --output /tmp/dataset-processing-benchmark.json
```

Use `--case small`, `--case medium`, or `--case high-signal` for an individual workload. Paths alternate order between iterations and the report uses median wall/CPU duration. Every case computes SHA-256 fingerprints of runtime-metadata-free intelligence output and fails immediately if reference and optimized results differ. CI validates that the benchmark runs and produces valid output, but does not assert noisy absolute timing values.

Peak memory is the operating system's whole-process RSS high-water mark. It is useful as an approximate ceiling, not as an isolated allocation measurement; a prior run in the same process can determine the reported peak.

## Measured bottlenecks before optimization

The first full-pipeline capture produced these rankings.

### Baseline creation

| Rank | Stage | Wall time | Finding |
| ---: | --- | ---: | --- |
| 1 | Relationship learning | 4.106 s | Re-parsed two complete columns for every pair and mode; 2.28 million numeric conversions under `cProfile`. |
| 2 | Baseline statistics | 0.487 s | Re-parsed each signal for the global and mode-conditioned distributions. |
| 3 | Expected-model fitting | 0.349 s | Rebuilt pair alignment for retained edges. |
| 4 | Operating context | 0.186 s | Required work; not a leading repeat-work source. |

Baseline total was **5.173 s wall / 5.172 s CPU**. It considered 570 candidate/eligible mode-conditioned pairs, deeply analyzed 532 retained relationships, and evaluated 6,916 lags. Approximate process peak RSS was 100,716,544 bytes.

### Comparison analysis

| Rank | Stage | Wall time | Finding |
| ---: | --- | ---: | --- |
| 1 | Sensor health | 4.082 s | 630 pair projections repeatedly parsed the same columns; peer drift and timestamp alignment dominated. |
| 2 | Temporal / lag analysis | 3.162 s | More than 33,000 general-purpose NumPy histogram calls dominated rolling entropy. |
| 3 | Covariance analysis | 1.354 s | Dense numerical work; no safe semantic-preserving rewrite was justified in this change. |
| 4 | Multiscale analysis | 1.002 s | Rebuilt the same per-window numeric projections across scales. |
| 5 | Behavioral modeling | 0.684 s | Required downstream modeling work. |
| 6 | Empirical thresholds | 0.682 s | Repeated signal and relationship window parsing. |

Comparison total was **11.504 s wall / 11.496 s CPU**. It considered, accepted, and deeply analyzed the same 300 pairs. Approximate process peak RSS was 133,636,096 bytes.

The comparison relationship-screening stage itself took only 0.057 s. That measurement did not justify new correlation-based pruning, especially because low ordinary correlation can still be relevant to nonlinear or structural detection. Existing structural eligibility rules, bounded source-order inventories, minimum overlap, zero-variance handling, and the baseline learner's cheap first-pass correlation gate remain unchanged. Instrumentation now reports candidate, eligible, deep, temporal, and multiscale counts so a future screening change can be driven by evidence rather than assumption.

## Optimizations applied

1. Baseline learning parses each signal column once per job. Global/mode statistics, pair alignment, lag analysis, and expected-model fitting reuse those deterministic numeric projections.
2. Sensor health parses bounded assessment columns once and reuses them across signal checks, peer drift, timestamp alignment, and relationship-context enrichment.
3. Empirical-threshold and multiscale modules use stage-local numeric projection caches instead of repeatedly converting rows to floats for each window or pair.
4. Rolling entropy uses a vectorized equal-width histogram specialized to the exact existing `numpy.histogram(..., bins=12)` rules. Boundary-correction tests compare it with the reference implementation at `1e-15` tolerance, and end-to-end SII output remains identical.
5. Completed baseline models declare `behavioral-baseline-artifacts.v1` and an explicit reusable-artifact manifest. Comparison relationship checks reuse the persisted graph only when the artifact version is current (or when reading a compatible legacy v1 model); an explicit incompatible version fails safely instead of being silently reused.
6. Baseline relationship comparison caches parsed active columns within that one comparison job, eliminating repeated serialization/conversion without retaining state after the job.
7. Small Python repeat work was removed where it appeared in profiles, including rebuilding affected-signal sets and re-enriching the same relationship context.

No multiprocessing or thread pool was added. The dominant gains came from eliminating repeated CPU work, while process-level concurrency would duplicate large row structures and increase peak memory and determinism risk. No alternate dataframe engine or new acceleration dependency was introduced.

## Results

On the same full-pipeline 3,000-row/high-signal workload:

| Path | Before | After | Improvement |
| --- | ---: | ---: | ---: |
| Baseline creation | 5.173 s | 2.695 s | **47.9%** |
| Comparison analysis | 11.504 s | 6.699 s | **41.8%** |

Leading stage changes were:

| Stage | Before | After | Improvement |
| --- | ---: | ---: | ---: |
| Baseline relationship learning | 4.106 s | 1.986 s | 51.6% |
| Baseline expected-model fitting | 0.349 s | 0.055 s | 84.1% |
| Sensor health | 4.082 s | 1.082 s | 73.5% |
| Temporal / lag analysis | 3.162 s | 2.036 s | 35.6% |
| Multiscale analysis | 1.002 s | 0.511 s | 49.0% |
| Empirical thresholds | 0.682 s | 0.459 s | 32.7% |

Candidate/deep pair and lag counts were unchanged. The full reference and optimized intelligence structures were identical after removing runtime-only fields.

The final standalone one-iteration high-signal benchmark independently measured baseline-learning work at 4.289 s before and 2.569 s after (40.1%), and comparison analysis at 12.596 s before and 7.639 s after (39.4%). Baseline relationship throughput rose from 157.0 to 268.1 pairs/second. An all-cases run reported a shared process high-water mark of 158,019,584 bytes once both paths had executed. In the full-pipeline capture, process peaks were 103,219,200 bytes for optimized baseline and 138,403,840 bytes for optimized comparison. The reported memory values reflect whole-process high-water behavior and the bounded per-job column caches; no claim of peak-memory reduction is made.

## Instrumentation contract

Each stage records wall duration, process CPU duration, and applicable counters. Across the full upload and analysis path the report covers:

- validation, schema/timestamp processing, semantic mapping, canonical build, and canonical persistence;
- operating-context construction, baseline statistics, relationship learning, and expected-model fitting;
- signal drift, relationship analysis, operating modes, data conditions, sensor health, and empirical thresholds;
- mode-conditioned comparison, relationship graph, fixed/adaptive persistence, temporal/lag, multiscale, covariance, physics, and behavioral modeling;
- evidence fusion, baseline artifact reuse, result finalization, and evidence persistence.

Applicable totals include rows, signals, candidate/eligible/deep pairs, windows, lags, scales, models, evidence candidates, and cache/artifact reuse. The report also contains a compact, duration-ranked summary suitable for internal logs or diagnostics.
