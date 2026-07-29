# Neraium Pilot Operator Runbook: Initial Baseline Import

## Purpose

This runbook defines the read-only pilot intake flow. Neraium learns normal operating behavior from representative historical data; it does not actuate equipment or replace engineering judgment.

## Standard flow

1. Open `Data` or select `Import Historical Dataset` from Operations Brief.
2. Under `Establish Initial Baseline`, choose a representative historical CSV file.
3. Review the selected filename and choose `Continue`.
4. Observe Upload Data, Validate Signals, Learn Relationships, Establish Baseline, and Begin Learning.
5. When complete, open the baseline or return to Operations Brief.

## Expected states

- Before selection, the import surface explains the historical-data requirement and exposes a labeled file control.
- During transfer, Upload Data is the active stage.
- During processing, the active stage and Processing details reflect backend status.
- On success, all completed stages are marked complete and the established baseline can be opened.
- If processing fails after transfer, the transfer remains complete, only the failed stage is marked `Failed`, and later stages are `Not started`.

## Recovery actions

- To process the stored file again after an import failure, select `Retry Import`.
- To start a new upload, select `Choose Another File`.
- For `Server unavailable`, retain the selected or stored file state and retry after service recovery.
- Do not describe a completed file transfer as an upload failure.

## Baseline interpretation

- Temporary abnormalities do not redefine normal without persistent, verified operating history.
- Findings are evidence for engineer review, not autonomous control, guaranteed prediction, or root-cause diagnosis.
- Insufficient evidence remains explicitly insufficient; the interface does not invent a finding.

## Deterministic bad-data simulation set

Use these fixtures to verify graceful degradation:

- `tests/fixtures/telemetry_corruption/missing_timestamps.csv`
- `tests/fixtures/telemetry_corruption/flatlined_signal.csv`
- `tests/fixtures/telemetry_corruption/out_of_order.csv`

Run:

```bash
python -m pytest -q tests/test_telemetry_integrity_simulations.py
python scripts/pilot_rehearsal_check.py
```

Expected result:

- Upload jobs return a terminal complete or failed contract with an operator-visible message.
- Stage labels and recovery actions follow the semantics above.
- No hidden control action or actuation occurs.
