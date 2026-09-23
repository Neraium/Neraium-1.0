# Retrospective wastewater validation methodology

The source was located and hashed before analytical inspection. `raw/freeze.json` records its absolute path, SHA-256, bytes, timestamp, engine commit, tracked source hashes, package versions, platform and configuration. No external dataset documentation was read before execution. Existing prize evidence is preserved separately and unchanged.

Schema/validity inspection preceded protocol selection. The frozen protocol (`raw/protocol.json`) selects the first seven source-clock days as a fixed reference and every subsequent consecutive one-day interval through the last observation, including a partial final interval. This is an orchestration choice, not a change to production baseline rules. No outcome-based period selection or alternative baseline search is performed. The first week is a reference, not a certified healthy period. Daily boundaries are anchored to the first observation rather than civil midnight.

The unchanged `neraium_historical.daily_replay.DailyReplay`, `QualitySource`, and `EngineAdapter` from the historical-analysis repository invoke the current checkout's authoritative `app.engine.sii_engine.evaluate_sii`. Production defaults apply. The wrapper carries the independent engine-owned persistence and recurrence states forward, beginning with null states. Failed attempts retain prior state under existing behavior. All attempts, full results, hashes and predecessor checkpoints are saved. No future comparison values enter earlier engine inputs.

Only the timestamp format is normalized in a derived CSV, from month/day/year 12-hour clock to exact `YYYY-MM-DD HH:MM:SS`. No timezone is invented. Headers, order and numeric cell strings are preserved. Existing `QualitySource` excludes a row if any selected telemetry cell is blank, nonnumeric or nonfinite; it retains every exclusion and source row position. This is the existing historical wrapper's complete-case policy, not imputation. Physically questionable but finite values are retained. Unknown units remain null. No clipping, interpolation, resampling, sorting, additional filters or synthetic observations are used.

Report graph temporal support, recurrence support, promoted edges, governed persistent flags and governed insights separately. Counts of pair-window observations are not counts of independent events. Consecutive supported windows may be grouped descriptively; that grouping does not introduce a new detector or qualification rule. First support time means the final source observation of the first supported window, not inferred onset. Duration between first and last supported window completion is a retrospective observation span, not proof of uninterrupted physical change.

Analytical output hashes are sealed before any external publication or metadata lookup. Post-hoc source contextualization cannot change inputs, baseline, units, outputs or qualification. Without independent event ground truth, no accuracy, sensitivity, specificity or false-positive rate is calculated. Measurable consequence is reported only if the engine supports it; raw correlation displacement has no physical unit and does not establish harm or benefit.

## Reproduction

Use the exact engine commit and historical-wrapper source hashes in the manifests and installed dependency versions in `raw/freeze.json`. Preserve dictionary/source-column order (the earlier controlled campaign identified order sensitivity). From this repository, with the original source at its recorded path and a fresh output package containing the recorded initial `raw/freeze.json`:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONHASHSEED=0 .venv/bin/python scripts/validate_wastewater_real.py
.venv/bin/python scripts/summarize_wastewater_real.py
```

The runner refuses to overwrite an existing protocol. Archive the original output before an independent rerun; do not delete or overwrite this evidence package. Checkpoint manifests capture wrapper code hashes, exact configuration, source identity and state links. `raw/normalized.csv` plus reference/source-row provenance reconstructs every input. Checkpoints preserve full engine responses and ordered state objects. The original file remains untouched.

## Reporting and verification commands

After the primary runner completes, and before external lookup, run the preselected evidence repeats:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONHASHSEED=0 .venv/bin/python scripts/verify_wastewater_real.py
```

The recorded blind-phase seal identifies the exact outputs present before external lookup. The summarizer performs no engine calls and may run concurrently with verification. To regenerate descriptive reports from frozen outputs:

```bash
.venv/bin/python scripts/report_wastewater_real.py
.venv/bin/python scripts/supplement_wastewater_report.py
```

Run the supplement once after rendering the base report (it appends reporting sections). `raw/omitted-pairs.json` is a source/result coverage audit: enumerate all 21 combinations of seven signals, subtract each window's emitted pairs, and inspect numeric constancy in that window's retained input rows. No omitted edge is manufactured. The source-quality audit and omitted-pair audit do not change analysis inputs.

The complete evaluation set and unchanged numerical outputs were sealed before external lookup; descriptive summaries were finalized afterward. No additional engine evaluation was performed after external lookup. Analytical configuration was selected after schema/validity inspection rather than before receiving the dataset; its first-week/day policy was fixed before any analytical results were available.
