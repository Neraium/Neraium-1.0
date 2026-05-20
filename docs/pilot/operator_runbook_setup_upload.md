# Neraium Pilot Operator Runbook (Setup + Upload)

## Purpose
This runbook defines the operator flow for pilot intake without changing infrastructure authority. Neraium remains read-only and non-actuating.

## Standard flow
1. Open `Setup & Data Connections`.
2. Complete `Setup`:
   - Enter required `Source type` and `Endpoint`.
   - Review `Signal Mapping`.
   - Run `Read-Only Check`.
   - Click `Finish Setup`, then `Go to Upload`.
3. Complete `Upload`:
   - Select CSV (preferred pilot path) or JSON.
   - Click `Process Upload`.
4. Review `Status`:
   - Confirm `Pilot Readiness Check`.
   - Confirm baseline state and latest analysis timestamp.

## Expected states
- Setup:
  - Step title progresses `Connection Info -> Signal Mapping -> Quick Verify`.
- Upload:
  - `No Upload Selected` appears before file selection.
  - Upload transitions to processing states and reaches `COMPLETE` or `FAILED`.
- Status:
  - Session and control plane are visible.
  - Adaptive context is visible (learning/baseline/confidence).
  - Pilot readiness checklist reports pass/warn per check.

## Recovery actions
- Validation error:
  - Use `Select New File`.
  - Re-upload a valid CSV/JSON telemetry export.
- Processing error:
  - Use `Retry Upload`.
  - If partial batch success exists, use `Retry Failed Files`.
  - If runner completion mismatch appears, use `Reprocess Job`.
- Baseline not active:
  - Continue telemetry ingestion until baseline transitions from pending to active.
- No active analysis:
  - Upload data or resume a previous session.

## Deterministic bad-data simulation set
Use these fixtures to verify graceful degradation:
- `tests/fixtures/telemetry_corruption/missing_timestamps.csv`
- `tests/fixtures/telemetry_corruption/flatlined_signal.csv`
- `tests/fixtures/telemetry_corruption/out_of_order.csv`

Run:
```bash
python -m pytest -q tests/test_telemetry_integrity_simulations.py
```

Expected result:
- Upload jobs always return a terminal contract (`COMPLETE` or `FAILED`) with an operator-visible message.
- No hidden control actions or actuation occurs.
