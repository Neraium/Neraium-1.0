# Correctness verification

Verification is against the current workspace frozen before production edits,
not against an assumed clean checkout. `raw/frozen-golden-manifest.json` fixes the
compressed baseline captures; `raw/baseline-source-hashes.json` fixes source bytes.

## Comparison contract

The harness retains complete returned payloads as compressed JSON. It compares
serialized governed projections **exactly**, with no float tolerance and without
sorting dictionary keys or lists. Datetimes use their ISO representation. This
checks relationship populations and ordering, statistics, mode/context results,
persistence and learning states, sufficiency, findings, authority and provenance.

Only observational diagnostics are excluded from the governed projection:
`performance`, `processing_time_seconds`, `runtime_seconds`,
`total_runtime_seconds`, and `step_timings`. They remain in the full raw captures.
The complete aggregate work counters inside `performance.totals` are separately
compared, including relationship-pair, context, lag and window counts. Historical
profile-sample and near-duplicate comparison limits are also explicitly checked. Metadata
clocks are frozen by the harness; source timestamps, model identities, lineage,
evidence IDs, uncertainty, classifications and thresholds are not normalized away.

Historical captures include raw-source and canonical-artifact SHA-256 values,
complete ingestion records and all returned analysis rows. Fresh checks also
materialize compressed source and canonical files, asserting that their actual
bytes match the digests frozen before optimization. Those artifact bytes are
materialized later; their immutable expected digests are from the original run.

## Workload and state coverage

- Historical ingestion: 10k, 100k and 250k rows, canonical values and provenance.
- Baseline candidate construction: 10k and 100k rows, ordered mode membership,
  distributions, lag relationships, expected models and approval boundaries.
- Unified analysis: 10k and 100k rows, complete relationship/temporal/covariance
  evidence and conservative context/sensor-health limitations. No module failures
  occur in these goldens; limited analytical states remain limited.
- Incremental: an explicitly verified active v1 model, followed by three 240-row
  windows. The model remains available and learning remains blocked by the
  observations, including the injected violation. Historical training is outside
  new-window latency.
- Governance: context summaries and three existing evidence-package fixtures
  covering active packages, context availability and missing quantified
  persistence, plus canonical fingerprints. These are fixture packages, not a
  claim of newly promoted production findings or established consequences.

Full payload comparison includes every consequence/authority field produced by
these paths. No new consequence calculation, promotion rule, or actuator path is
introduced. The corpus does not prove every possible domain or promoted outcome;
existing Phase 2–4 safeguard and evidence tests provide additional coverage.

## Focused regression baseline

The selected 36 files (`raw/regression-files.txt`) completed before editing:
**349 passed, 30 failed**. All 30 failures involve pre-existing retired-upload or
replay HTTP contracts (410 responses and downstream missing response keys).
They are documented, not repaired during this pass.

The earlier broad repository run was interrupted after **269 passed, 95 failed**
(446.02 seconds). Its complete partial log is retained as `raw/before-regression.log`.
It is not counted as a completed or passing full-repository suite.

New equivalence tests retain the original numerical/parser algorithms as references
and test 3,000 malformed/random input strings, Unicode, signed zero, cancellation,
large offsets, underflow-scale values, mode tie ordering, exact covariance
contractions, input immutability, bounded caching, and NumPy error-policy isolation.

Final counts and comparison results are recorded in `raw/equivalence.json` and
`raw/regression-comparison.json` after the final verification run.

## Final results

- **103 exact governed-output comparisons passed**, including all frozen repeats,
  optimization checkpoints, original-code controls, final runs, archived baseline
  iteration results, isolated-memory runs, and fresh-process outputs.
- All aggregate analytical work counters matched. No relationship statistics,
  states, sufficiency/context/consequence fields, findings, authority boundaries,
  provenance semantics, or key/list ordering changed in those captures.
- All nine final workloads passed in fresh processes with `PYTHONHASHSEED=8675309`.
  The affected baseline workloads were repeated after the last conversion change.
- Completed post-change selected suite: **382 passed, the same 30 failed**.
  `raw/regression-comparison.json` records **zero new failures** and no resolved
  failures. This suite preceded the final two-line conversion refinement; the
  affected baseline goldens, fresh processes, and **37 differential tests** passed
  afterward, including 100k-element exact arithmetic cases.
- `compileall` completed for the changed production modules and benchmark tools.
  `git diff --check` passed. All 27 frozen output files retain their original hashes.
- Preservation checks cover 475 pre-existing Python sources: only the four intended
  production files changed. The unrelated tracked diff matches the initial diff
  byte-for-byte (`raw/preservation-verification.json`).

Expected raw-output differences are diagnostic CPU/wall/RSS measurements only;
these are retained, not silently discarded. Initial harness failures and the
slower rejected parser attempt remain documented and archived.
