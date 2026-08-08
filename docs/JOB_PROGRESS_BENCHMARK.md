# Job progress instrumentation benchmark

## Result

The benchmark was run on 2026-08-08 with the repository Python environment:

```text
./.venv/bin/python scripts/benchmark_historical_ingestion.py \
  --rows 25000 --signals 48 --analysis-rows 10000 --iterations 2
```

The deterministic historian fixture was 12,405,592 bytes with 25,000 rows and
48 signals. Each case ran twice in alternating order.

| Measurement | Without progress callback | With progress instrumentation |
| --- | ---: | ---: |
| Median ingestion time | 15.733242 s | 15.842420 s |
| Observed difference | not applicable | 0.109178 s (0.694%) |
| Median durable-update simulations | 0 | 25 |
| Average update frequency | 0 Hz | 1.578052 Hz |
| Median RSS delta | 22,296,576 bytes | 29,329,408 bytes |

The measured time overhead was below one percent. The 7,032,832-byte difference
between median before/after RSS deltas is a coarse allocator/order signal, not a
precise retained-memory measurement. Each instrumented run serialized 204,199
cumulative bytes across 25 snapshots; the largest single snapshot was 9,042
bytes. The average interval was 0.633697 seconds because stage transitions are
written immediately, while repeated counters within a stage retain the
two-second throttle.

## Method

[`scripts/benchmark_historical_ingestion.py`](../scripts/benchmark_historical_ingestion.py)
generates a repeatable multi-family historian export, then runs the complete
historical trust pipeline with and without a `ProgressReporter`. Both cases
perform the same raw/canonical artifact persistence. The instrumented callback
updates and serializes the complete progress snapshot on every would-be durable
write, approximating the application-side CPU and allocation cost of existing
runtime/S3 state persistence.

The benchmark records process RSS before and after each run. RSS deltas are
coarse and allocator/order dependent, so they are useful only as a regression
signal. The local benchmark does not model remote S3 network latency; deployment
latency is bounded operationally by the same transition-plus-two-second write
throttle and 25 observed writes for this workload.
