# Benchmarks

One warm-up and three measurements per workload. Every measured run is retained; no outlier removal. Timings exclude fixture generation, imports, runtime initialization, output capture, and profiling. Full samples, CPU times, RSS, work counters, and throughput are in `before.json`, `after.json`, and `comparison.json`.

| Workload | Before median [min–max] s | After median [min–max] s | Saved s | Latency reduction | Rows/s before → after | Peak RSS MiB before → after |
|---|---:|---:|---:|---:|---:|---:|
| baseline-10000 | 1.1135 [0.9065–1.2406] | 0.6129 [0.6122–0.6171] | 0.5006 | 45.0% | 8980 → 16316 | 134.9 → 135.3 |
| baseline-100000 | 10.3485 [8.6160–10.4085] | 5.4692 [5.1133–5.6614] | 4.8794 | 47.2% | 9663 → 18284 | 215.5 → 216.6 |
| engine-10000 | 7.5981 [5.4171–8.0032] | 4.2286 [4.0757–4.3196] | 3.3695 | 44.3% | 1316 → 2365 | 157.1 → 162.2 |
| engine-100000 | 14.6542 [13.5379–15.5197] | 13.5825 [13.4834–13.8391] | 1.0717 | 7.3% | 6824 → 7362 | 337.3 → 337.9 |
| governance-10000 | 0.0124 [0.0072–0.0158] | 0.0079 [0.0072–0.0080] | 0.0046 | 36.8% | 803801 → 1270945 | 154.8 → 155.4 |
| incremental-240 | 1.5402 [1.4488–1.6828] | 1.5673 [1.5483–1.8112] | -0.0271 | -1.8% | 467 → 459 | 138.4 → 141.5 |
| ingestion-10000 | 1.5571 [1.2481–1.5939] | 0.9783 [0.8699–1.0848] | 0.5788 | 37.2% | 6422 → 10222 | 147.9 → 145.3 |
| ingestion-100000 | 15.4857 [14.0314–15.4951] | 9.6541 [9.4481–9.7893] | 5.8317 | 37.7% | 6458 → 10358 | 339.1 → 320.3 |
| ingestion-250000 | 24.9769 [24.8865–25.3001] | 23.1594 [23.0760–23.5647] | 1.8175 | 7.3% | 10009 → 10795 | 623.3 → 629.3 |

Negative reductions are regressions/noise and are deliberately reported. RSS is process high-water memory including setup, warm-up and prior output retention, not isolated allocation peak. Shared-host timing dispersion limits causal claims for small differences. Incremental rows/s covers 720 new rows; per-window latency is the three-window total divided by three. Relationship throughput counts deeply analyzed unique pairs per call, not all lag/window sub-evaluations; those separate counters are retained in JSON.

The original baseline showed substantial host variation. The following later controls reload only the four original hot-path modules from the frozen commit, verifying their SHA-256 against the initial workspace manifest. All other current workspace code remains the same. Each control is followed by its optimized benchmark. These controls supplement, rather than replace, the original measurements.

| Workload | Later original-code median s | Optimized median s | Saved s | Latency reduction | Throughput gain | RSS reduction |
|---|---:|---:|---:|---:|---:|---:|
| baseline-100000 | 7.8567 | 5.4692 | 2.3876 | 30.4% | 43.7% | -0.2% |
| engine-10000 | 4.4493 | 4.2286 | 0.2208 | 5.0% | 5.2% | -2.9% |
| engine-100000 | 14.2156 | 13.5825 | 0.6331 | 4.5% | 4.7% | 0.8% |
| incremental-240 | 1.7356 | 1.5673 | 0.1684 | 9.7% | 10.7% | -0.7% |
| ingestion-100000 | 9.7962 | 9.6541 | 0.1421 | 1.5% | 1.5% | 7.9% |

Machine-readable control samples and ranges: `control.json` and `control-comparison.json`. Fresh-process runs use `PYTHONHASHSEED=8675309`; their samples are kept separately in `raw/fresh-*-benchmark.json` and are not pooled into the performance medians.

The repeated benchmark process retains/serializes large results between trials, so its high-water RSS can hide reduced ingestion working memory. The following independent checks use one warm-up and one measured job in separate original/optimized processes, reading RSS before serialization. Their timing samples are retained but are not used to claim throughput gains.

| Workload | Original isolated-job peak MiB | Optimized isolated-job peak MiB | Saved MiB | Reduction |
|---|---:|---:|---:|---:|
| ingestion-100000 | 257.3 | 199.5 | 57.8 | 22.5% |
| ingestion-250000 | 414.3 | 291.5 | 122.8 | 29.6% |

These are process high-water checks including setup and warm-up, not allocation traces. The full repeated-process peaks above remain reported, including regressions. See `memory-comparison.json` for the complete isolated samples.
