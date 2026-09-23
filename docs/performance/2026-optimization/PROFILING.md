# Profiling

Separate cProfile executions follow benchmark warm-up and measured trials; profiler
runs are not counted in benchmark medians. Binary profiles and cumulative/self-time
reports are in `raw/*-profile.txt` and `raw/*.prof`. Inclusive times overlap and
must not be summed as independent stage costs.

Initial measured ranking:

| Workload | Profiled cost | Interpretation |
|---|---:|---|
| 10k unified engine (initial probe) | runner 5.78s / 16.16s | 1,024 covariance updates; repeated small-array operations and contraction planning |
| 10k unified engine (initial probe) | temporal 3.90s / 16.16s | rolling entropy 2.25s; correlation drift 1.10s |
| 10k unified engine (initial probe) | mode context 1.49s; multiscale 1.53s | repeated numeric projections and row-level context construction |
| 100k unified engine | parsing 9.53s / 42.82s | 2.7 million numeric parser calls; multiscale and mode analysis dominate larger histories |
| 100k baseline | correlations 3.52s / 11.43s | Python loops under distributions, lags, and relationship fitting |
| 100k baseline | mode identification 2.28s / 11.43s | 94,591 calls to Counter.most_common; dominant signature does not change |
| 10k historical ingestion | accumulator 0.96s / 3.32s | per-character unit-marker scanning and value parsing |
| 10k historical ingestion | stable JSON 0.64s / 3.32s | canonical serialization, row digests; provenance work must be retained |
| Three incremental windows | runner 3.50s / 5.01s | small-array overhead dominates; einsum path planning alone 0.25s |

The initial probe had a harness clock-comparison failure, retained under
`raw/harness-attempt-1/`; its profile still measures unmodified production code.
Subsequent profiles accompany the successful golden captures.

Coverage of requested categories: parsing/normalization appears in
`parse_numeric_value`, `_parse_number`, `normalize_rows`, and dataframe construction;
dataframes in telemetry normalization; statistics and repeated baseline work in
`_correlation`, `_signal_characteristics`, and mode construction; relationship graph
in `_learn_relationship_graph` and engine stages; covariance in `sii_runner`; temporal
persistence and rolling calculations in `temporal_math` and adaptive persistence;
operating context in mode analysis and the governance workload; serialization,
provenance, filesystem and SQLite I/O in ingestion and candidate persistence; copying
in phase-4 model/snapshot handling (`deepcopy`). All costs remain available in the
raw profiles, including small paths that were deliberately not optimized.

## Post-change profile and remaining costs

`raw/profile-categories.json` exposes calls, self time and inclusive time for all
requested categories across the before/after profiles. Empty categories mean that
entry point was not exercised in that particular workload, not an estimated zero
for production. Profiling overhead and host variation mean these values rank work;
unprofiled benchmarks establish speed changes.

At 100k rows, the final baseline profile is 8.34s: distributions 3.21s,
relationships 1.73s, and mode identification 0.62s. Correlation now spends much of
its 2.21s in conversion (1.43s). Further reuse of immutable numerical projections
would require carefully scoped lifetime and mutation contracts.

The final 100k engine profile is 39.78s: multiscale analysis 10.04s, mode analysis
9.27s, numeric parsing 6.15s, covariance runner 4.14s, and temporal math 2.79s.
These are overlapping inclusive costs. Repeated context construction, numeric
projections across module/window boundaries, and rolling entropy/correlation remain
significant. Cross-run caching is not justified by an unchanged row count alone:
window membership, authenticated scope, model version, and evidence lineage matter.

The final 100k ingestion profile is 20.37s: stable JSON 4.58s, signal accumulation
3.46s, source-row iteration 2.41s, and numeric parsing 1.94s. Serialization, hashing,
and provenance writing remain required work. The later end-to-end control shows
only a 1.5% median ingestion throughput increase, within timing dispersion; this
pass does **not** claim a strong historical-throughput improvement. Its stronger
historical-ingestion result is the independently checked memory reduction.
