# Frozen current-system validation protocol

System under test: Neraium commit `97d267d317fcce4b4424cf2141e97e87680acfc0`.
The starting tracked worktree was clean. `raw/freeze.json` records the source hashes,
environment, installed package versions and freeze time. No analytical production
source, thresholds, qualification criteria or governance policy was changed.

## Inspection and evidence selection

Inspection covered the active upload pipeline and `evaluate_sii`, supplied-reference
input validation, relationship graph and temporal/recurrence logic, operating context,
sensor health, existing tests, benchmark scripts, historical ingestion, governance
and replay documentation. The engine combines signal comparisons, relationship
comparisons, contextual comparability, data-quality/health gates and governed evidence.
It is not evaluated here as a predictor or diagnostic system.

The repository's older `backend/benchmarking/structural_benchmark_engine.py` and
`backend/validation/cognition_validation_framework.py` contain proxy labels based on
frame or lineage counts. These labels are not used as measured performance evidence.
The hydronic pilot manifest is a scenario specification, not proof that all listed
physical events have been validated. Its event-matching backtest is not used to
support prediction or lead-time claims.

The adjacent historical-analysis repository is an orchestration/reporting wrapper
around the authoritative engine. Its preserved campaign used an earlier engine
commit. We inspect that record, retain its ground truth and rerun the unchanged
synthetic telemetry through this checkout's engine, carrying both engine-owned
states. We do not treat the wrapper's episode counts as persistence decisions.
`raw/prior-evidence/inventory.json` identifies and hashes inspected source artifacts.

The archived Siemens Building X readiness report is sandbox connector evidence.
The saved export is inspected locally for sufficiency; no fresh authenticated
requests are made. Its records are not padded, interpolated, or joined into an
invented multivariate dataset. The report's ready/partial/blocked labels overlap;
they are not a partition of points or performance rates. Original long CHW and
wastewater files without verified field provenance are not promoted into real-world
validation evidence. No real customer-field accuracy claim is supported.

## New controlled battery

`raw/battery/plan.json` and `protocol-seal.json` were written before the new calls.
All cases use unchanged engine defaults. The sensitivity grid has two baseline
correlations (−0.65, +0.65), two displacement directions, seven magnitudes
(0, .05, .10, .15, .20, .25, .30), and three phase variants. Each sequence has eight
nonoverlapping comparison windows against one fixed reference. Orthogonal sine
and cosine components produce the specified correlation while preserving means
and variances. Each window has 96 rows at five-minute cadence. These phase variants
are not independent real systems; their similar results do not establish population
sensitivity or error bounds. Unknown units are declared explicitly as null.

Ten variants each cover stable, stationary Gaussian-noise, transient, alternating,
and recovery sequences. Only Gaussian cases use independently drawn noise per day;
other variants vary waveform phase. The transient displacement is +0.20 in one window; alternating displacements are
±0.20 and the recovery sequence starts with +0.20. The
alternating case changes direction every window, and recovery returns to reference
behavior after eight changed windows. The primary negative-control endpoint is any
**temporal persistence support**, separately from abrupt promotion or generic findings.
There is no pooled "accuracy" statistic or post-hoc pass threshold for the sweep.

Stress sequences exercise missing and nonfinite values, duplicate/reversed timestamps,
15-row windows, irregular positive intervals, a flatlined signal, an outlier,
level-only compensation, changed response correlation and an unseen equipment stage.
Rejection is expected at the documented strict paired-input boundary for the first
five invalid cases. Accepted data-quality cases remain descriptive: a returned result
is not proof that a finding is correct. The compensation fixtures hold the output
marginal distribution while either offsetting the other signal's level or changing
its correlation. These are mathematical response analogues, not a physical controller
simulation or validation of equipment compensation diagnosis.

Every input, full output, exception, input hash, input-mutation check and elapsed time
is recorded in `raw/battery/cases.jsonl.gz`. Each sequence's last call is repeated
with its original incoming states. Equality compares the whole relationship graph
except its `runtime_seconds`, governed `sii_evidence` and supplied-reference provenance.
A separate fresh-process replay verifies fixed cases and the complete input-state chain.
It does not claim byte identity for runtime-bearing full engine responses.

The archived controlled CHW replay retains all 12 signals and 17,280 rows, uses
576 reference rows followed by 58 nonoverlapping 288-row windows, and starts both
states at null. The source bytes are bundled compressed, with their original hash.
The scorer reads authoritative edge support directly and reports all target scenarios
and any other promoted pairs. Scenario labels were available to the evaluator;
this rerun is not independently blinded or an unseen benchmark.

## Ingestion, performance and regression

A separate upload-path battery retains input CSV text and complete outputs for
14 cases, including missingness levels of 1%, 5%, 20% and 50%, dropout, stuck data,
noise, irregularity, duplicate and unordered times. It uses current ingestion behavior
rather than repairing data to satisfy paired mode. These outputs are observational;
nonempty findings on stable fixtures must not be hidden behind a zero-persistence result.

Performance uses existing repository fixture generators and processing functions,
with three repetitions at each existing small/medium/high-signal size. Every timing,
CPU measurement, memory high-water mark and semantic fingerprint is retained. Upload
scales additionally use the existing robustness generator and existing time ceilings.
The historical-ingestion benchmark separately measures complete canonical ingestion
and its bounded analysis sample. Generation is outside processing timers. Measurements
run on shared local hardware, alongside validation processes; they are not a cloud SLA,
concurrent-user throughput test, or a controlled comparison with previous hardware.
Memory high-water/delta measurements can be affected by earlier work in the process.

The default backend regression suite was started unchanged, then interrupted after
17 minutes to bound time spent on repetitive application workflows. Its 425 passes
and two timeout failures are retained; it is not a completed full-suite run. A focused
861-test selection is subsequently executed, with exact files preserved in
`raw/focused-test-files.json`. Pytest's existing
`not slow and not integration` selection is preserved and skips/deselections are
reported. Browser, cloud deployment, PostgreSQL integration and physical field
validation are outside this run. No frontend code changed.

## Provenance and limitations

The initial dependency capture tried `pip freeze`, but this existing uv environment
has no pip module. No dependencies were installed or changed; `importlib.metadata`
records exact installed versions instead. The first regression run began before
manifest serialization; source remained unchanged. New cases began after the freeze.

The runner's convenience `historical.json` recurrence list accidentally queried
`recurrence_supported` instead of the actual `supported` field. It is retained as
executed, and is explicitly non-authoritative for recurrence. The separate scorer
reads the correct field from complete raw responses. This is a reporting correction,
not a system change or analytical rerun.

SHA-256 checks provide local integrity and replay provenance, not independent
attestation or a signature from Siemens. Existing governance test results demonstrate
specified software behavior on fixtures, not regulatory certification or production
security assurance. No field labels, independently verified interventions, or measured
water savings are available in this validation.

The current CHW replay uses the same raw source and window sizes as the archived
campaign but declares all units unknown. The original campaign's explicit unit
mapping is preserved in `raw/prior-evidence/replay-config.json`. Consequently this
is a current-engine evaluation of unchanged telemetry, not an exact configuration
reproduction of the previous report. No configured engineering priors are supplied.

Temporal state is passed explicitly by the validation caller between windows. A
single independent call does not create chronological history. These runs do not
establish that every deployed caller persists and resumes that state correctly.

The fresh JSON replay failed for one archived CHW window. Additional diagnostic
calls changed row dictionary insertion order only; the original order restored
the original evidence hash. The failed primary replay remains in the evidence.
The canonical input hash is order-insensitive although context selection is not,
so preserving values and hashes alone does not establish replay equivalence.

The symmetric grid retains both direction labels at zero magnitude, which produces
duplicate zero-displacement inputs. Counts describe executed sequences, not unique
physical systems or statistically independent trials. No persistent-change detection
rate across a noise-amplitude distribution was estimated.
