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
