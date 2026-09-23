# Limitations and boundaries

- This is a local backend performance pass on the dirty workspace identified in
  `BASELINE.md`. It is not a deployed service capacity test. Existing work is
  preserved and not included in performance commits.
- Synthetic workloads have three numeric channels. They exercise scale in rows,
  correlated signals, recent relationship change, context, temporal evidence,
  baseline candidates, and governed packages. They do not characterize hundreds
  of signals or every industrial domain. Regression tests supply additional edge
  cases; they are not substitutes for production data benchmarks.
- Existing limits remain unchanged: temporal math uses at most 5,000 rows,
  covariance runner retains at most 1,024 vectors by default, historical profiling
  samples at most 4,096 values per signal, and the canonical analysis handoff has a
  two-million-cell limit. All input rows are still processed by historical
  ingestion. Throughput must not be mistaken for deep evaluation of every pair
  at every historical timestamp.
- Larger-scale coverage is 250,000-row historical ingestion. The full unified
  engine is measured through 100,000 rows. No million-row or high-channel-count
  capacity claim is made.
- Local SQLite/filesystem I/O and in-memory Phase 4 storage are covered. Remote
  historian latency, production PostgreSQL, S3, connector scheduling, and network
  throughput are not represented by the microbenchmarks.
- Peak RSS is Linux process high-water RSS. It includes inputs, warm-up, setup,
  previous output retention, and allocator reuse. It is not per-call allocated
  bytes. Before/after processes use the same measurement policy.
- CPU and wall-clock results vary on this shared host. Three measurements after
  warm-up, full min/max ranges, and unsuccessful runs are retained. Small changes
  within that dispersion should not be claimed as proven improvements.
- Metadata clocks are fixed by the benchmark only. Production run IDs/timestamps
  remain clock-derived. Determinism means identical governed payloads for fixed
  metadata, source input, configuration, and starting state, with list/key order
  retained. Diagnostic timers and resource counters are reported separately.
- The incremental benchmark measures new comparison windows against seeded
  behavioral memory, not end-to-end live connector-to-browser latency. Existing
  `telemetry_analysis_service.run_post_ingestion_analysis` already returns a
  terminal persisted result before querying telemetry for the same deterministic
  window ID. This pass does not introduce a cross-tenant or cross-run result cache.
- Evidence-package fixtures cover active and insufficient quantified persistence
  and operating-context availability. They do not establish new measurable
  consequences. No authority, consequence, threshold, uncertainty, provenance,
  or promotion rule is changed.

- Isolated ingestion-memory checks supplement the repeated-process RSS values:
  one warm-up and one measured job, before artifact serialization, in separate
  original/optimized processes. They are footprint checks, not extra samples
  selected for throughput claims. Repeated-process maximum RSS did not improve
  for every workload and remains visible in the benchmark tables.
- The complete selected suite has 30 pre-existing retired-route contract failures;
  the overall repository is not certified green. The broad repository run was
  interrupted and is explicitly reported as partial. No frontend/browser tests
  were needed for these backend-only changes.
- No long-duration live-store growth, remote connector capacity, or high-signal-count
  throughput claim is made. Canonical JSON/provenance I/O, overlapping window
  projections, mode construction, and rolling temporal statistics remain costs.
- Parser gains depend on input format. Some malformed numeric-looking strings can
  require an extra conversion attempt; exact legacy parsing behavior is preserved.
