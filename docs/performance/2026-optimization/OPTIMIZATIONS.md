# Optimizations

This pass preserves analytical thresholds, qualification and persistence criteria,
mode and baseline semantics, evidence sufficiency, uncertainty, provenance,
authority boundaries, and read-only behavior. No approximation or parallel
execution is introduced.

Implemented changes; each passed its targeted frozen-output comparison before the next optimization:

1. **Baseline arithmetic and mode selection.** Reuse the fixed most-common mode
   rather than searching the same Counter for each unretained signature. Preserve
   first-seen tie ordering. Move sufficiently long correlation product loops into
   NumPy while keeping Python's original means and sequential accumulation order;
   do not substitute a pairwise sum, BLAS dot product, or correlation estimator.
   Reuse correlations already computed at zero lag and self lag one. Post-change
   profiling then exposed array conversion as a remaining cost: an alternating
   CPU-time microbenchmark supported replacing `asarray` with `fromiter` for these
   flat float lists. Exact arithmetic tests and both baseline goldens were rerun;
   the earlier complete baseline measurements remain under `raw/iteration-1/`.
2. **Numeric parsing.** Accept an already complete numeric string directly with
   the same float conversion and finite-value check. Preserve the existing
   normalization/fallback for units, commas, percentages, missing markers,
   malformed text, and Unicode. Cache no raw telemetry across jobs.
3. **Historical-ingestion allocations and unit checks.** Release duplicate and
   timestamp work tables after their consumers finish. Keep canonical writing,
   raw preservation, duplicate policy, and hashes unchanged. Use an equivalent
   compiled ASCII unit-marker check, retaining Unicode's original isalpha rule.
4. **Covariance contraction planning.** Reuse shape-only contraction plans for
   repeated Mahalanobis calculations. Keep the same NumPy contraction ordering,
   covariance/inverse calculations, window membership, and values. Bound the cache
   and never store telemetry or tenant-specific data in it.

Attempts and exclusions:

- Initial harness capture failed on datetime serialization, then correctly flagged
  clock-derived run IDs and step timings. The corrected harness freezes metadata
  clocks and compares analytical payloads separately from diagnostic timers.
- Copying the in-memory store lock failed. The driver now copies only its data into
  a new isolated store, retaining production locking unchanged.
- The first incremental fixture produced limited memory. Its results are retained
  under `raw/harness-attempt-2`; the replacement asserts an active trained model.
- Broad baseline regression was interrupted after 446 seconds with 95 failures
  and 269 passes, predominantly retired-upload API contract failures. The log is
  retained. Complete selected regression files are recorded separately.
- The initial unconditional numeric fast path made unit-bearing strings slower in
  the targeted microbenchmark. Its patch and samples are retained. The final
  implementation normalizes separators first and checks the suffix before trying
  a whole-string conversion; malformed-input equivalence remains exact.
- Cross-run baseline/result caching was not added: moving historical windows,
  authenticated scope, model version, provenance, and live event state all matter.
  Existing deterministic-window idempotency remains in place.
- Rolling statistics, spectral processing, and evidence serialization remain
  candidates for future work. Numerical reduction changes and concurrency are not
  justified without stronger equivalence and workload evidence.

All four production files were clean at intake; only their performance changes are included in the implementation commit. No pre-existing user edits were staged with them. The final differential suite has 37 passing cases, including 100k-element bit-for-bit correlation checks.
