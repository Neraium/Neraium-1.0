# Platform Audit After Strengthening

Date: 2026-06-14
Repo: `Neraium/Neraium-1.0`
Audited branch: local `main`

## Executive Summary

Neraium is stronger than it was before the recent hardening pass, especially in upload cleaning, persisted evidence shape, and basic false-positive guardrails. The platform now ingests messy CSV telemetry more safely, records rows received/used/dropped, persists evidence records with real variables and source-row anchors, and uses a real backend-native SII runner on the upload path.

It is not yet fully trustworthy end to end. The main remaining risks are traceability and trust-boundary issues rather than raw ingestion failures. The code still contains fallback paths that can blur job/run identity, replay can fall back to the latest persisted upload instead of the requested job, non-production replay can still synthesize timelines, and the UI still contains generic/operator-facing statements that are not always tightly bound to persisted evidence. Confidence is better gated for display than it is fundamentally calibrated in the runner itself.

Overall assessment: stronger, but not production-tight.

## Scorecard

| Area | Score (1-10) | Status |
|---|---:|---|
| Upload robustness | 7 | Improved materially; large-scale and state-leak risks remain |
| SII engine integrity | 7 | Real runner is used; replay/demo/fallback surfaces still need stricter isolation |
| Evidence traceability | 5 | Evidence shape improved, but job/run fallback behavior is still risky |
| Confidence calibration | 5 | Display gating improved; runner confidence still under-models weak evidence/noise |
| False-positive resistance | 6 | Better than before; still heuristic and not fully benchmarked at production scale |
| Operator usefulness | 6 | Better evidence/finding surfaces, but still generic in several places |
| Mobile UI readiness | 5 | Multiple CSS fixes exist; no direct browser validation was run |
| Production readiness | 6 | Usable for controlled rollout, not yet fully trust-hardened |

## What Is Stronger Now

- Upload cleaning is substantially better. `_stream_csv_snapshot` now handles blank rows, malformed rows, invalid timestamps, duplicate timestamps, missing numeric values, invalid numeric cells, unsorted timestamps, whitespace-delimited files, and missing headers, while emitting counts and warnings (`backend/app/services/upload_jobs.py:447-623`).
- Upload results now persist structured ingestion accounting: `rows_received`, `rows_used`, `rows_dropped`, `drop_reasons`, and `quality_counts` (`backend/app/services/upload_jobs.py:1223-1231`, `1267`).
- Evidence persistence is no longer generic-only. `build_evidence_record_from_result()` persists `variables`, `drift_metrics`, `data_conditions`, and `source_rows` from backend result content (`backend/app/services/upload_jobs.py:765-841`).
- The production upload path uses a real backend SII runner. `run_sii_runner()` instantiates `BackendSiiRunner`, ingests numeric vectors, writes `latest_sii_state`, and exposes runner identity (`backend/app/services/sii_runner.py:19-23`, `386-470`).
- Replay/finding evidence chains are stronger. Relationship changes now flow into replay frames and evidence refs/source rows (`backend/app/services/upload_jobs.py:1481-1485`, `898-915`).
- The frontend upload contract only marks supported SII claims when the backend says the output is reliable enough to show and evidence persistence succeeded (`frontend/src/viewModels/uploadContract.js`).

## What Is Still Weak

- Traceability is not strict enough.
  - `replay_payload(job_id)` falls back to `read_latest_upload_result()` when the requested job is absent, so a wrong job id can still return another job’s replay (`backend/app/services/upload_jobs.py:1344-1357`).
  - `/api/replay/timeline` falls back from SII state to persisted upload replay, and in non-production it can synthesize a live timeline when no replay exists (`backend/app/routers/replay.py:27-39`).
  - Replay UI falls back to embedded replay from `latestUploadResult` when scoped replay is empty (`frontend/src/components/replay/ReplayWorkspace.jsx:81-99`).
  - Evidence feedback falls back to the latest evidence run if the requested `run_id` is missing (`backend/app/routers/evidence.py:81-89`).
- Confidence is still only partly calibrated.
  - `confidence_from_history()` uses history length and completeness, but not noise, evidence strength, baseline quality, or corroboration directly (`backend/app/services/sii_runner.py:784-798`).
  - Display gating uses `sii_reliable_enough_to_show`, but the underlying runner can still emit relatively strong internal confidence on weak evidence.
- Reported processing time is understated.
  - `processing_time_seconds` is captured before the heavy persistence/evidence write tail, then large JSON writes and evidence persistence happen afterward (`backend/app/services/upload_jobs.py:1206-1209`, `1269-1320`).
  - Result: operator-visible end-to-end latency is much higher than the reported processing time.
- Some room-level semantics changed without all tests or downstream expectations being aligned.

## Production Trust Risks

1. Cross-job replay contamination risk.
   `replay_payload(job_id)` can return the latest persisted replay instead of the requested job’s replay if the requested job is missing (`backend/app/services/upload_jobs.py:1344-1357`).

2. No-active-session stale-state leak.
   Full pytest currently fails because `/api/data/latest-upload?include_persisted=1` can return an interpreted active state instead of `no_active_session` (`tests/test_data_upload.py:1829-1844`). This is a real trust risk because stale persisted state can be presented as live/current context.

3. Feedback can attach to the wrong evidence run.
   Missing run ids on feedback can silently attach operator feedback to the latest run (`backend/app/routers/evidence.py:81-89`).

4. Replay can exist without strict evidence/run alignment.
   The Replay UI withholds the `Supporting Evidence` list unless run ids match, which is good, but the replay itself can still render via fallback replay data (`frontend/src/components/replay/ReplayWorkspace.jsx:245-258` and `81-99`).

## Fake/Synthetic Fallback Risks

- Production upload processing uses the backend-native runner, not demo payloads. I did not find a production upload path that imports demo/fake analysis into `process_csv_file()` or `run_sii_runner()`.
- Demo and synthetic replay still exist:
  - explicit `mode=demo` and `mode=aquatic_demo` (`backend/app/routers/replay.py:17-24`)
  - non-production synthetic live replay fallback when no timeline exists (`backend/app/routers/replay.py:33-39`)
- Current verdict:
  - Production upload/SII path: no fake/demo analysis found.
  - Replay surface: synthetic fallback still exists outside production and should stay visibly labeled and isolated.

## Upload Reliability

### Code Audit

- Clean telemetry: supported.
- Messy telemetry: supported with explicit cleaning and warnings.
- Sparse telemetry: accepted, but reliability/room semantics are still heuristic.
- Large telemetry: functionally supported, but with performance caveats.
- Safe failure behavior: partial completion path exists and preserves status/result artifacts instead of hard crashing (`backend/app/services/upload_jobs.py` partial-result path earlier in file; `process_next_queued_upload_job()` also marks failed jobs safely at `1742+`).

### Edge Cases

Current cleaner behavior from code and tests:

- Missing values: accepted; counted in `quality_counts`.
- Duplicate timestamps: dropped and counted.
- Unsorted timestamps: sorted before analysis, warning emitted.
- Bad numeric fields: blanked/ignored; row retained if any usable numeric remains.
- Stuck sensors: profiled and degraded in data quality.
- Sparse data: accepted, but semantics are weak and some expectations are drifting.
- Large uploads: accepted; performance is the main issue.

### Verdict

- Messy data readiness: moderate to good.
- Fail-safe behavior: good.
- Large-upload readiness: functional but not comfortable yet.

## SII Engine Path

Traced path:

`/api/data/upload` (`backend/app/routers/data.py:430-559`)
-> queued upload record and initial evidence placeholder (`441-477`)
-> worker dispatch (`431-432`, `135-147`)
-> `process_next_queued_upload_job()` (`backend/app/services/upload_jobs.py:1742+`)
-> `process_csv_file()` / `_build_csv_result()` (`backend/app/services/upload_jobs.py`)
-> `run_sii_runner()` (`backend/app/services/sii_runner.py:386-470`)
-> `write_latest_sii_state()` (`backend/app/services/sii_runner.py:699-721`)
-> `build_evidence_record_from_result()` + `upsert_evidence_run()` (`backend/app/services/upload_jobs.py:1288-1320`)
-> `latest-upload`, replay, evidence, and UI consumers.

Conclusion:

- Real SII runner is used on the production upload path.
- I did not find a production upload path that uses fake/demo/synthetic analysis instead of `BackendSiiRunner`.
- I did find replay/demo fallback surfaces that can confuse operators if not strictly labeled and separated.

## Evidence And Findings Consistency

### Current Status

Partially consistent, not strict enough.

What is consistent:

- Upload result `job_id` is used as evidence `run_id` in the main upload path (`backend/app/services/upload_jobs.py:1288-1303`).
- Replay supporting evidence is hidden unless the evidence run id matches the replay job id (`frontend/src/components/replay/ReplayWorkspace.jsx:245-258`).
- Evidence records can now persist real telemetry-derived fields: `variables`, `drift_metrics`, `data_conditions`, `source_rows` (`backend/app/services/upload_jobs.py:786-840`).

What is inconsistent or risky:

- Runtime snapshot divergence exists right now in the repo state:
  - `backend/runtime/latest_upload_result.json` is for job `92fa82ec...`
  - `backend/runtime/evidence/runs.json` currently contains older `d9189d...` and `b161e23...` records
- `replay_payload(job_id)` can return a different job’s latest replay when the requested job has no result (`backend/app/services/upload_jobs.py:1344-1357`).
- Feedback can fall through to the latest evidence run (`backend/app/routers/evidence.py:81-89`).
- Gate can still show generic “Review findings.” and “Change Detected” summaries that are not strictly bound to a persisted backend evidence packet (`frontend/src/components/workspaces/SystemBody/SystemBodyWorkspace.jsx:377-408`, `490-498`, `515-516`, `571-573`).

### Missing Or Generic Evidence Fields

Observed reasons:

- Evidence records do not currently persist `source_file` separately; they use `source_name`.
- `job_id/run_id` alignment is strong on the normal upload path, but fallback paths can bypass strict identity.
- Drift metrics are populated, but can still be sparse or generic when replay/baseline relationship detail is limited.
- Data quality is persisted indirectly via `data_conditions` rather than a full normalized evidence-quality packet.
- Time anchors and source rows are present when relationship evidence exists, but can collapse to broad upload start/end timestamps when detailed anchors are unavailable.

## Confidence Calibration Status

### What Works

- Display gating is stronger now:
  - `sii_reliable_enough_to_show` is only set true when baseline reliability and evidence persistence are both true (`backend/app/services/upload_jobs.py:1307-1312`).
- Small/sparse uploads are explicitly blocked from being “reliable enough to show” in the messy-data tests.

### What Does Not Fully Work

- Runner confidence is primarily driven by history depth and completeness, not by:
  - weak baseline quality
  - high noise
  - weak corroborating evidence
  - excessive missingness beyond completeness
  - disagreement between replay, baseline, and evidence layers
- `confidence_basis()` is also generic text: “from baseline and telemetry history depth” (`backend/app/services/sii_runner.py:839-841`).

### Verdict

- Confidence calibration status: improved but still heuristic.
- High confidence from weak evidence: reduced at the display layer, not fully prevented in the underlying runner math.

## False-Positive Resistance

### Available Automated Signal

Focused robustness suite:

- `tests/test_messy_upload_reliability.py`: passed
- `tests/test_sii_runner.py`: passed
- `tests/test_sii_robustness_regression.py`: passed
- `tests/test_upload_robustness_benchmark.py`: passed except the optional 1M skip

Focused combined run result:

- `101 passed, 5 failed, 1 skipped, 6 deselected` in `146.08s`
- The failures were in `tests/test_data_upload.py`, not in the robustness benchmark files themselves.

Benchmark interpretation:

- Stable clean telemetry: no benchmark failure seen.
- Stable noisy/missing telemetry: no benchmark failure seen.
- Injected drift: no benchmark failure seen.
- Relationship collapse: no benchmark failure seen.
- Sensor dropout: no benchmark failure seen.

Limits:

- I am relying on the existing synthetic benchmark/test corpus.
- I did not regenerate a new manual benchmark matrix beyond the automated tests and custom performance measurements.

### Verdict

- False-positive resistance is better than the documented pre-fix baseline.
- It is not yet proven strong enough for unrestricted operator trust.

## Performance Readiness

### Exact Measurements

Command: `PYTHONPATH=./backend ./.venv/bin/pytest -q tests/test_upload_robustness_benchmark.py::test_100k_upload_performance_guard -vv`

- Result: `1 passed` in `60.25s`

Command: custom measurement using `process_csv_content()` with generation time separated

| Rows | CSV generation | Wall processing | Reported `processing_time_seconds` | Memory delta |
|---|---:|---:|---:|---:|
| 10k | 0.067s | 28.473s | 0.551990s | 50,072 KB |
| 100k | 0.492s | 30.969s | 2.060802s | 44,800 KB |
| 200k | 1.056s | 30.175s | 3.936689s | 91,584 KB |

### Important Interpretation

- The backend-reported `processing_time_seconds` is not end-to-end time.
- The timer is captured before the heavy JSON persistence and evidence-write tail (`backend/app/services/upload_jobs.py:1206-1209` vs `1269-1320`).
- End-to-end operator latency is therefore much higher than the reported metric.

### 1M Status

- `tests/test_upload_robustness_benchmark.py::test_1m_upload_performance_guard` exists but is skipped unless `NERAIUM_RUN_1M_BENCHMARK=1`.
- I did not run the 1M benchmark in this audit.
- 1M readiness: unknown.

### Verdict

- 10k: ready
- 100k: borderline
- 200k: functionally feasible, but latency/measurement quality is not production-comfortable
- 1M: unknown

## UI And Mobile Readiness

### Trustworthiness

Gate, Findings, and Replay are more grounded than before, but not fully evidence-specific.

Generic or weakly grounded examples:

- Static trust language: `Observation grammar refined on 2026-06-04.` (`frontend/src/components/workspaces/SystemBody/SystemBodyWorkspace.jsx:257-260`)
- Backend interpretation mapping can reduce explanations to simplified/operatorized text (`377-388`).
- `buildRelationshipSummary()` can collapse to `Change detected.` when drift state exists but the selected text looks stable (`501-516`).
- `nextStep` is often a generic `Review findings.` (`393`, `496`).

Replay trust boundary is better:

- Supporting Evidence is withheld unless evidence run id matches replay job id (`frontend/src/components/replay/ReplayWorkspace.jsx:245-258`).

Replay trust weakness:

- Replay itself can still render from fallback replay data even when exact job/evidence alignment is absent (`81-99`).

### Mobile/Layout

What I verified:

- There are explicit CSS fixes for system-gate/mobile overflow/layout issues in:
  - `frontend/src/styles/system-body/system-body-layout-fix.css`
  - `frontend/src/styles/system-body/system-body-mobile.css`
  - `frontend/src/styles/system-body/system-body-hero.css`
- The recent commit history includes mobile fixes (`613ae48`, `fdd861a`).
- Frontend tests and build pass.

What I did not verify:

- I did not run manual browser or device validation for:
  - Gate content hidden behind cards
  - Views overlay hidden behind Gate
  - horizontal overflow in Safari/iOS
  - Safari bottom-toolbar overlap

Verdict:

- Mobile UI readiness: unknown-to-moderate, code-reviewed but not manually validated.

## Test Results

### Commands Run

1. `git diff --check`
   - Result: exit `0`, no output

2. `cd /home/ubuntu/Neraium-1.0 && PYTHONPATH=./backend ./.venv/bin/pytest -q tests/test_data_upload.py tests/test_messy_upload_reliability.py tests/test_replay_api.py tests/test_sii_runner.py tests/test_sii_robustness_regression.py tests/test_upload_robustness_benchmark.py`
   - Result: `5 failed, 101 passed, 1 skipped, 6 deselected, 1 warning in 146.08s`
   - Failures:
     - `test_facility_systems_uses_multi_room_state_after_upload`
     - `test_processing_helper_preserves_profile_metadata`
     - `test_processing_helper_distinguishes_calm_and_drifted_uploads`
     - `test_multi_room_intelligence_uses_room_specific_relationship_and_structural_explanations`
     - `test_mixed_room_regression_preserves_unstable_nominal_and_sparse_room_states`

3. `cd /home/ubuntu/Neraium-1.0/frontend && npm test -- --run src/App.test.js src/components/ObservationCenterWorkspace.test.js src/components/replay/ReplayWorkspace.test.js src/viewModels/__tests__/uploadContract.test.js src/viewModels/__tests__/uploadFlow.test.js src/viewModels/__tests__/uploadState.test.js`
   - Result: `6 passed`, `22 tests passed` in `10.20s`

4. `cd /home/ubuntu/Neraium-1.0/frontend && npm run build`
   - Result: success in `497ms`

5. `cd /home/ubuntu/Neraium-1.0 && PYTHONPATH=./backend ./.venv/bin/pytest -q`
   - Result: `6 failed, 259 passed, 1 skipped, 10 deselected, 5 warnings in 217.88s`
   - Additional failure beyond the focused run:
     - `test_latest_upload_always_returns_system_interpretation_for_no_active_session`

6. `cd /home/ubuntu/Neraium-1.0 && PYTHONPATH=./backend ./.venv/bin/pytest -q tests/test_upload_robustness_benchmark.py::test_100k_upload_performance_guard -vv`
   - Result: `1 passed` in `60.25s`

### Failure Classification

| Failure | Classification | Reason |
|---|---|---|
| `test_facility_systems_uses_multi_room_state_after_upload` | stale test expectation | `Sparse telemetry` wording changed to `Insufficient telemetry`; semantics are similar |
| `test_processing_helper_preserves_profile_metadata` | real regression | 3-row upload still reports `readiness=ready`, which weakens sparse-baseline caution |
| `test_processing_helper_distinguishes_calm_and_drifted_uploads` | stale test expectation | current heuristics now surface drift as `review`; this appears to match the strengthening direction |
| `test_multi_room_intelligence_uses_room_specific_relationship_and_structural_explanations` | stale test expectation | wording changed, but the sparse-room distinction still exists |
| `test_mixed_room_regression_preserves_unstable_nominal_and_sparse_room_states` | stale test expectation / heuristic shift | attribution generalized from `structural_drift` to `process_timing` |
| `test_latest_upload_always_returns_system_interpretation_for_no_active_session` | real regression | stale persisted state can override the expected no-active-session contract |

## Top 10 Next Fixes

1. Make replay strictly job-scoped: remove `latest_upload_result` fallback from `replay_payload(job_id)` when a job id is explicitly requested.
2. Fix latest-upload stale-state leakage so `no_active_session` is returned when no active session is intended, even if old persisted artifacts exist.
3. Remove evidence feedback fallback-to-latest-run; require explicit run identity.
4. Rework confidence calculation to include baseline reliability, noise, rows dropped, evidence strength, and corroboration quality, not just history depth/completeness.
5. Report end-to-end processing latency separately from internal analysis latency; current `processing_time_seconds` is too optimistic.
6. Add a strict backend contract that Gate/Replay/Findings can only show evidence-backed claims when `job_id/run_id` alignment is proven.
7. Persist a fuller evidence-quality packet in evidence runs, not just `data_conditions`.
8. Add explicit UI labeling whenever replay content is fallback-derived or non-production synthetic.
9. Reconcile stale tests versus intended strengthened behavior, especially room-state wording and attribution semantics.
10. Run manual mobile/browser validation on iPhone Safari and narrow CSS fixes to the exact remaining overlay/overflow issues.

## Bottom Line

Neraium is stronger now in the areas that were most obviously weak: upload cleaning, evidence shape, runner integrity on the upload path, and baseline false-positive guardrails.

The next problems are subtler and more important for trust: strict run/job identity, stale-state leakage, fallback isolation, and confidence calibration. Until those are fixed, the platform is improved but still not fully trustworthy for production-grade operator interpretation.
