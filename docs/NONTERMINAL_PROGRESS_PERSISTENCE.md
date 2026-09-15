# Nonterminal progress persistence

## Change boundary

`upload_jobs.write_job` normalizes the job under its publication lock and calls
`_scope_job_payload`, which retains scope, attempt ownership, and terminal-state
protections. Non-baseline jobs whose status/stage updates the latest state enter
`write_upload_status_progress`. Only its nonterminal branch, after
`write_upload_status` and the canonical terminal check, opts into the narrow
evidence lookup for `persist_latest_upload_state`.

`read_progress_evidence_run` reads the requested run through the existing
scope-filtered database accessor and verifies the payload scope. For provisional
queued/pending/processing evidence without historical observation keys, finding
identity, or review context, it checks only that run's finding/event indexes and
applies the existing product and annotation projection to the current record.
This preserves the whole latest-state evidence object, including provenance and
the default history fields, without hydrating historical runs.

Completed/rich evidence, records with history-dependent observation fields,
existing finding cases, review events, and required cold legacy imports retain
the full reader. Terminal completion and final evidence publication do not opt
into the new lookup. Their existing reader, finding materialization, analytical
semantics, and publication ordering are unchanged. Database connection,
transaction, commit, JSON mirror, and durability implementations are unchanged.

## Before/after profile

Same disposable hydraulic fixture: one queued current run plus twelve completed
local `hydraulic-response-v1` evidence records, remapped to fresh IDs and an
isolated scope. The existing profiling harness was rerun before and after the
implementation. The base runtime was production image
`sha256:3f5685151d4a400889ec9b3711abf4a2815dd65599132c4168637ef80b071aa6`
at revision `af28224f45232250a39b92d804946f66fd372fdf`. The candidate used the same
image with a read-only backend source overlay; no candidate image was built.

Local ext4; SQLite DELETE journal, synchronous FULL; 2 CPU / 3 GiB container
limit. Initialization and warmup excluded. Controls are five writes with detailed
recording/cProfile disabled; trivial observer wrappers remain. Operation counts
come from one representative canonical-stage write. Linux syscall counts were
captured in a separate strace execution.

| Measurement | Before | After |
|---|---:|---:|
| Median write wall time, recording disabled | 461.209 ms | 87.130 ms |
| Median canonical-stage write, detailed profiling enabled (3 samples) | 753.796 ms | 117.878 ms |
| SQLite connections | 132 | 17 |
| Schema initializations | 60 | 8 |
| Top-level SQL `execute` calls | 578 | 67 |
| Schema `executescript` calls | 60 | 8 |
| SQL trace callbacks, including script statements and trigger repeats | 2,586 | 347 |
| SELECT statements | 166 | 13 |
| Filesystem stat syscalls | 5,333 | 712 |
| SQLite `fcntl` lock operations | 9,172 | 1,220 |
| Publication RLock acquisitions | 3 | 3 |
| JSON decoded | 3,009,565 bytes | 28,658 bytes |
| Full JSON mirror writes | 4 | 4 |
| Mirror bytes written | 75,047 | 75,047 |
| History loads / hydration passes | 1 / 1 | 0 / 0 |
| Finding materialization calls | 13 | 0 |
| `fdatasync` calls | 16 | 16 |
| SQLite page/journal `pwrite64` calls | 132 | 132 |

The median write is **81.1% faster (5.29×)**. Most schema/metadata amplification
disappears while the actual persistence/durability work stays the same. The
remaining schema initializations belong to the unchanged current-state DB
helpers. Cold legacy or rich evidence paths intentionally retain their costs.

These are local measurements, not a production EFS benchmark. The host ext4
filesystem was nearly full; profiling and scheduling add noise. EFS network
round-trip latency and concurrent database contention were not reproduced, so
the reduction does not establish a new production end-to-end runtime.

The coordinating Demo-Neraium workspace retains the harness, raw profiles,
syscall traces, command manifests, fixture provenance, and `before-after.json`
under `.runtime/demo-neraium/write-job-profile/`. The comparison directories are
`ext4-h12-real-beforepr`, `ext4-h12-real-afterpr`, and their `-strace-` equivalents.
The candidate runner adds only `--engine-source /home/ubuntu/Neraium-1.0` to the
same `--storage ext4 --history 12 --real-history` fixture; fresh tags prevent
overwriting either measurement.

## Focused validation

54 persistence tests passed across:

```text
tests/test_progress_evidence_lookup.py
tests/test_atomic_terminal_job_state.py
tests/test_upload_state_contract.py
tests/test_upload_session_service.py
```

The twelve new parameterized cases cover whole-record equality against the full
reader at three progress stages, UI provenance, absence of history/finding
hydration, scope isolation, incorrect/stale attempts, retries, terminal
monotonicity, final completion/result provenance, required rich/compatibility
history, and cold legacy import. After strengthening the historical-context and
legacy-import fixtures and verifying the hydration observer, all twelve were
rerun and passed in 2.82 seconds.

One existing Demo hydraulic integration scenario passed in **16.57 seconds**:

```text
tests_engine/test_real_engine_scenarios.py::test_hydraulic_evidence_is_produced_by_pinned_real_engine
```

It ran against an isolated local candidate backend overlay on the pinned base
image with disposable tmpfs state and the existing 300-second adapter timeout.
The base-image identity setting came from the prepared preview configuration;
this was a source-overlay integration, not validation of a new release digest.
An initial invocation stopped at identity verification before any analysis
because that local setting was omitted; the corrected invocation above passed.

An additional fixture using embedded legacy operator feedback exposed existing
recursion in `_migrate_legacy_events_if_unambiguous` → `record_finding_feedback`
→ `read_finding_case`. A separate disposable reproduction confirmed it on the
unchanged production image before any progress lookup. That behavior is outside
this optimization and remains unchanged; the historical-context regression
uses canonical review events. The command and evidence are retained in
`legacy-reproduction-command.json` and `legacy-reproduction.log`.

No broad unrelated suites, production changes, infrastructure changes, timeout
changes, or durability changes were made.
