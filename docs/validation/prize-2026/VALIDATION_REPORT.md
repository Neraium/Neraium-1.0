# Current-system technical performance validation

Frozen commit: `97d267d317fcce4b4424cf2141e97e87680acfc0`. Execution date: 23 September 2026.

The current engine demonstrated the specified persistent-versus-transient behavior
on controlled fixtures. Important limitations remain: context sensitivity to row-key
order, incomplete like-mode evidence, incomplete recognition of partial flatlining,
and upload timings above existing references. These results do not establish field
accuracy, prediction, diagnosis, physical root cause, prescribed action, live-field
validation, water savings, or algorithmic novelty. No production logic, threshold,
governance rule or qualification criterion was modified.

## Scope, provenance and methods

Read [METHODOLOGY.md](METHODOLOGY.md) for the inspected implementation, prior evidence,
pre-execution protocol, endpoints, generators, qualification boundaries and exclusions.
[REPRODUCE.md](REPRODUCE.md) provides commands and environment reconstruction.
The initial tracked worktree was clean. Frozen file hashes were checked before and
after the new battery. The new harness and reporting files are additive and uncommitted.

The main battery contains **145 generated sequences / 1,200 primary windows**, plus
**58 archived synthetic CHW windows**, plus **145 final-window repeats**: **1,403
calls**. Primary calls comprise **1,218 returned results and 40 expected input
rejections**; repeat calls comprise **140 returned results and five repeated
rejections**. No primary result contained a failed module or nonfinite output number.
All input hashes verified, and no call mutated its input. These counts exclude
regression tests, upload cases, processing benchmarks and subsequent replay probes.

All new analytical-performance telemetry is controlled/synthetic. The only real
source-system telemetry inspected was a **previously saved Siemens sandbox export**;
it did not qualify for a new relationship-performance evaluation. No customer field
telemetry with verified provenance and outcome labels was available for this battery.

## Persistent change, controls and sensitivity

| Family | Sequences | Primary windows | Temporal-support windows | Governed persistent windows | Rejections |
| --- | --- | --- | --- | --- | --- |
| alternating | 10 | 80 | 0 | 0 | 0 |
| recovery | 10 | 120 | 30 | 30 | 0 |
| sensitivity | 84 | 672 | 144 | 144 | 0 |
| stable | 10 | 80 | 0 | 0 | 0 |
| stationary_noise | 10 | 80 | 0 | 0 | 0 |
| stress | 11 | 88 | 9 | 9 | 40 |
| transient | 10 | 80 | 0 | 0 | 0 |

The four primary negative-control families total **40 sequences / 320 windows**:
**zero temporal-support or promotion outcomes**. The zero-displacement grid adds
12 controlled sequences with no support. These are observed fixture counts, not
an estimated field false-positive rate. Ten recovery sequences stopped current
promotion immediately on return to reference behavior: **0/40 post-return windows**
retained temporal support. Raw observations preserve every pre-support window.

| Absolute correlation displacement | Sequences | Supported by final window | First support window |
| --- | --- | --- | --- |
| 0 | 12 | 0 | None |
| 0.05 | 12 | 0 | None |
| 0.1 | 12 | 0 | None |
| 0.15 | 12 | 12 | 6 |
| 0.2 | 12 | 12 | 6 |
| 0.25 | 12 | 12 | 6 |
| 0.3 | 12 | 12 | 6 |

The 48 sustained cases at .15–.30 all reached temporal support at window six.
The 24 nonzero cases at .05 and .10 did not; these are below the documented temporal
displacement floor. Zero-displacement cases also did not. Phase variants and idealized
sinusoids are highly controlled, not independent installations or evidence of a
universal detection rate. An abrupt promotion and a temporal confirmation are
separate endpoints; neither is counted as proof of a physical fault.

## Archived controlled chilled-water replay

Source: 17,280 rows, 12 signals, 576 fixed reference rows and 58 chronological
288-row windows. Source bytes are bundled as `raw/battery/historical-input.csv.gz`.
Its SHA-256 matches the preserved generator ground truth. Units are explicitly
unknown in this run; the older campaign's explicit unit map is retained separately.

| Target | Controlled scenario | Continuous-support windows | Recurrence-support windows | Promoted-change windows |
| --- | --- | --- | --- | --- |
| A | continuous | 10 | 0 | 10 |
| B | recurring | 0 | 8 | 0 |
| C | transient | 0 | 0 | 0 |
| D | stable | 0 | 0 | 0 |
| E | alternating | 0 | 0 | 0 |

No additional pair was promoted or supported as recurring. B first supported
recurrence at zero-based window 49. Repeated supported windows are not independent
events. This is a current-engine rerun of an existing designed fixture, not unseen
field validation. The scorer reads `recurrence_evidence.supported` from raw outputs;
the runner's convenience recurrence list used an incorrect field name and is not
used for these results. The original runner, summary and all outputs are preserved.

## Operating context, degraded data and response behavior

The strict paired interface rejected all 40 primary malformed cases: missing cells,
nonfinite values, duplicate timestamps, reversed timestamps and undersized windows
(eight each). Rejection is not successful analysis of those data.

The irregular positive-interval case gained support in windows 6–8. Its windows
extend beyond a day and can overlap; this is not evidence of independent temporal
replicates or assurance for arbitrary gaps. Fully flatlined and outlier-contaminated
paired cases produced no temporal promotion. Level-only compensation produced no
relationship promotion; changed response correlation gained support in windows 6–8.
These mathematical analogues do not establish performance on physical compensation.

The unseen-stage case was marked **weak comparability / known operational change**,
with **insufficient like-mode historical rows** and a global fallback. Its injected
relationship change still gained temporal support in windows 6–8. Therefore temporal
support must not be advertised as proof of a like-for-like comparison.

All 14 upload cases completed, including partial missingness and imperfect timestamps:

| Upload fixture | Rows | Drift label | Gate | Data confidence | Finding classifications | Conditions |
| --- | --- | --- | --- | --- | --- | --- |
| stable | 1200 | info | READY | high | insufficient_evidence | 0 |
| noise | 1200 | info | READY | high | insufficient_evidence | 0 |
| missing_1pct | 1200 | info | DEGRADED_READY | limited | insufficient_evidence | 0 |
| missing_5pct | 1200 | info | DEGRADED_READY | limited | insufficient_evidence | 0 |
| missing_20pct | 1200 | info | DEGRADED_READY | limited | insufficient_evidence | 0 |
| missing_50pct | 1200 | info | DEGRADED_READY | low | insufficient_evidence | 0 |
| dropout | 1200 | review | DEGRADED_READY | low | None | 0 |
| flatline | 1200 | info | READY | high | insufficient_evidence | 0 |
| duplicate | 1200 | info | DEGRADED_READY | limited | insufficient_evidence | 0 |
| out_of_order | 1200 | info | DEGRADED_READY | high | insufficient_evidence | 0 |
| irregular | 1028 | info | READY | limited | insufficient_evidence | 0 |
| outliers | 1200 | info | READY | limited | None | 0 |
| relationship_change | 1200 | review | READY | limited | context_limited_relationship_change | 1 |
| level_compensation | 1200 | info | READY | high | insufficient_evidence | 0 |

The stable and noisy uploads returned an **insufficient-evidence finding**, not a
physical-change condition; they must not be represented as either zero UI findings
or proven physical false alarms. The changed-relationship upload returned one
context-limited condition. Dropout returned review/low confidence without a condition.
No interpolation is claimed: source missingness was retained, with zero imputed cells.

**Observed weakness:** the final 300/1,200 samples of the partial-flatline fixture
were constant, yet data confidence remained high and the gate READY. Out-of-order
data was DEGRADED_READY while the separate data-confidence field remained high.
Quality labels and qualification fields must be interpreted together; successful
ingestion alone is not a robustness or correctness guarantee.

All 1,218 returned primary results had overall status `complete`, but all had limited
mode-conditioned baseline, Phase 4 and configured-physics sections; 1,152 also had
limited operating modes and eight had limited relationship-graph analysis. Missing
model/context/prior evidence was not filled in. Top-level completion is not evidence
that every analytical capability was qualified.

## Repeatability, governance and replay

**140/140 successful in-process final-window repeats** matched the specified graph,
governed evidence and supplied-reference projection; the five rejected repeats
returned identical errors. The separate state-chain audit checked **1,258 primary
records** with zero hash or state-handoff mismatches.

**Fresh JSON replay: 3/4 matched; one failed.** A diagnostic replay retained **985
differing fields** for CHW window 49. Operating-context feature selection depends on
row dictionary insertion order: sorted JSON keys changed the selected setpoint
context despite unchanged values, declared columns and canonical input hash.
Restoring row keys to the original CSV column order reproduced the original evidence
hash. This is a bounded reproduction, not deletion of the failed trial. The observed
support/promotion flags did not change in that diagnostic, but context and evidence
identity can. The failure remains a material replay/provenance limitation.

Code inspection supporting this finding: `context_signals` in
`backend/app/services/operating_modes.py` collects columns in encountered row-key
order; `describe_mode` assigns multiple signals to a shared role using last assignment.
No source change was made. Raw discrepancy outputs, paths, hashes and the restored-
order diagnostic are retained. Reproduction from the bundled CSV preserves original
header order; the default JSON replay check intentionally continues to report failure.

Governance coverage includes identity isolation, immutable evidence bases, context
expiry/invalidation, human review boundaries, state separation and evidence transport.
Software fixture tests are not regulatory certification or production security assurance.

## Scale and processing performance

Existing generators: small = 240 rows / 6 process signals; medium = 1,200 / 14;
high-signal = 3,000 / 24. Each also includes an equipment-stage column. These are
baseline-learning computational stages and engine comparison calls, not complete
browser-to-cloud jobs. Raw outputs and every repetition are retained.

| Case | Path | Runs | Median wall s | Wall range s | Median CPU s | Distinct semantic hashes |
| --- | --- | --- | --- | --- | --- | --- |
| small | baseline | 3 | 0.123 | 0.102–0.137 | 0.069 | 1 |
| small | comparison | 3 | 1.887 | 1.681–2.131 | 1.012 | 1 |
| medium | baseline | 3 | 2.332 | 2.322–2.401 | 1.275 | 1 |
| medium | comparison | 3 | 11.723 | 10.419–11.859 | 6.185 | 1 |
| high-signal | baseline | 3 | 11.631 | 9.571–11.688 | 5.836 | 1 |
| high-signal | comparison | 3 | 37.002 | 30.128–38.756 | 16.476 | 1 |

All three repetitions within each path shared its existing benchmark semantic
fingerprint. That scrubbed fingerprint is distinct from the stricter JSON replay test.
Peak process RSS across these stages reached 311,758,848 bytes, a process high-water
mark rather than isolated per-call allocation.

Full local upload-path observations (four process signals):

| Source rows | Analysis rows | Reported processing s | External wall s | Existing reference s | Within reference | Rows accounted |
| --- | --- | --- | --- | --- | --- | --- |
| 10000 | 10000 | 48.925 | 54.774 | 20.0 | False | 10000 |
| 100000 | 100000 | 156.317 | 161.794 | 60.0 | False | 100000 |
| 1000000 | 100000 | 396.823 | 400.525 | 300.0 | False | 1000000 |

All source rows were accounted for and all scale fixtures had `detected=false` under
the existing benchmark's composite endpoint. **All three timing references were
exceeded under concurrent load.** The 10,000-row reference is observational; 100,000
and million-row limits are existing guards. The million-row memory-delta guard passed,
but prior process high-water marks limit interpretation of the delta. Do not claim
million-row full-resolution analytics: its analysis sample was bounded to 100,000.

Historical ingestion separately retained **100,000 canonical rows / 12 signals**,
with **10,000 analysis rows**, and returned `ready_with_limitations`. Two uninstrumented
runs took 98.190 and 81.895 seconds;
two instrumented runs took 91.159 and 92.312 seconds.
Its peak process RSS was 157,143,040 bytes. This measures intake,
normalization and canonical persistence, not relationship detection on every row.

Timings are observations on shared local hardware, with overlapping test processes,
not deployment capacity guarantees or a fair before/after optimization comparison.

## Existing regression outcomes and residual verification gaps

The broad run was intentionally interrupted after **425 passes and two failures**
(427 completed; 2,583 initially selected; 27 deselected). Both failures were existing
15-second job-completion waits: `test_completed_comparison_uses_distinct_dataset_and_analysis_ids_and_scopes_findings`
and `test_upload_status_propagation_progresses_from_queued_to_complete`.
It is **not a completed full-suite run**.

Focused selection (`raw/focused-test-files.json`): **861 passed; 0 failed; 0 errors; 0 skipped; 861 completed test cases.**
Failure names: None recorded.

Follow-up without the other validation workloads (two timeout tests and the unchanged
100,000-row guard): **3 passed; 0 failed; 0 errors; 0 skipped; 3 completed test cases.**
Failure names: None recorded.
The isolated 100,000-row observation took **43.004 seconds reported processing / 45.117 seconds external wall**, within its unchanged 60-second guard. The concurrent and isolated observations show workload sensitivity, not a permanent failure of that guard. The million-row case was not rerun in isolation.
Earlier failures are retained regardless of follow-up outcome. Consult both JUnit
files and raw logs; do not add overlapping regression runs into a unique test count.
Slow tests, full PostgreSQL integration, browser tests and cloud/field deployment
were not established by this run. No frontend changes were made.

## Siemens Building X evidence boundary

The saved readiness report describes sandbox historical access: 28/33 discovered
points had historical observations and 0/33 had current/latest values in that audit.
The separately saved export contains 25 records across 10 points: 21 good-quality
and four bad-communication records; four lack units. Per-point counts range from
one to 12. None qualifies for even a 16-row reference plus a separate 16-row comparison.
The report itself found no defensible named physical relationship candidate.

This supports a read-only historical connectivity proof with documented gaps. It does
not support live monitoring, customer-field validation, or a measured relationship-
detection rate on Siemens data. The broader readiness audit and smaller export are
different saved artifacts; their counts must not be combined as one dataset.

## Environment and reproducibility

Python 3.11.16; NumPy 2.2.6; pytest 9.0.3. Platform: `Linux-6.17.0-1013-aws-x86_64-with-glibc2.39`.
CPU: Intel(R) Xeon(R) Platinum 8259CL CPU @ 2.50GHz; 2 logical CPUs reported.
OpenBLAS/OMP threads were set to one and PYTHONHASHSEED to zero. The host reported
7,818 MiB RAM; effective cgroup CPU/memory limits were unavailable at standard paths.
Local temporary SQLite/runtime storage was used; no relevant production/cloud
configuration variables were inherited. Full package versions, immutable external
package reference and hashes, original commands, source freeze and artifact checksums
are included. Timing and generated run clocks are not expected to be byte-identical.

## What evidence of technical performance do you have to-date?

Neraium’s evidence to date is controlled software validation and saved sandbox connectivity evidence, not field-validated performance. We froze the current engine and retained inputs, outputs, exceptions, source hashes and replay commands. A focused regression run passed all 861 tests.

The main battery executed 1,403 engine calls. None of 40 stable, noisy, transient or alternating control sequences gained temporal persistence support (320 comparison windows). All 48 sustained synthetic cases with correlation displacements of 0.15–0.30 gained support at the sixth comparison window; smaller tested displacements did not. These are designed fixtures, not population accuracy estimates.

The included 58-window replay of archived synthetic chilled-water telemetry produced continuous support in 10 windows and recurring support in 8, with neither on its stable, transient or alternating target pairs.

All 140 successful in-process repeats matched the specified evidence outputs. Fresh JSON replay matched 3 of 4 selected cases; the remaining case exposed dictionary-order sensitivity in operating-context evidence. Restoring source-column order reproduced its original hash.

A million-row upload completed, with analysis bounded to 100,000 rows, in 400.5 seconds under concurrent local load—exceeding the existing 300-second guard. The 100,000-row guard passed when rerun without the other validation workloads. Degraded-data tests exposed limits, including high confidence on a partially flatlined fixture.

Saved Siemens Building X sandbox data demonstrates historical access, but its sparse export is insufficient for persistent-relationship validation. The report retains failures, limited outcomes and incomplete regression coverage. It supports no prediction, diagnosis, root-cause, prescribed-action, live-field-performance or algorithmic-novelty claim.

Application answer length: **1866 characters**, below the requested 2,200.
Every numerical application claim maps to a raw artifact in
[CLAIM_TRACEABILITY.json](CLAIM_TRACEABILITY.json). The report's detailed counts are
computed by `scripts/summarize_prize_validation.py`; no successful-case filtering was used.
