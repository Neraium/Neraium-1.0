# Wastewater retrospective validation report

Engine commit: `97d267d317fcce4b4424cf2141e97e87680acfc0`. Source SHA-256: `29a2db4e54d5f5278d2c05732d62cf877f939f87312e035ddb700c385c3550a8`.

Production analytical logic, thresholds, baseline rules, persistence, recurrence, governance and operating-context rules were unchanged. All results below come from the frozen chronological run; external contextualization is separate. See METHODOLOGY.md, DATASET_PROVENANCE.md and LIMITATIONS.md.

## Exact accounting

Metric | Count
--- | ---
attempted windows | 253
returned windows | 253
comparison rows | 72156
module failures | 0
governed persistent pair windows | 4
evaluated pair windows | 5265
eligible pair windows | 5265
temporal pair windows | 505
recurrence pair windows | 82
promoted pair windows | 4
changed without temporal or recurrence pair windows | 1060
windows with temporal support | 208
windows with recurrence support | 77
source rows | 74172
valid complete case rows | 74171
excluded rows | 1
reference rows | 2015
unique rows analyzed | 74171
distinct pairs | 21
distinct temporal pairs | 12
distinct recurring pairs | 6
distinct governed persistent pairs | 2

Source span: 259.6875 days, 2018-06-14 07:30:00 through 2019-03-01 00:00:00, unspecified source clock. The 2,015 retained reference rows precede every comparison; unique rows are counted once. Counts of evaluated pair-windows repeat the same relationship over time.

## Result status and qualification

**window status**

```json
{
  "limited": 253
}
```

**limited modules**

```json
{
  "operating_modes": 253,
  "mode_conditioned_baseline": 253,
  "physics_reasoning": 253,
  "phase_4": 253
}
```

**temporal status**

```json
{
  "unconfirmed": 4760,
  "supported": 505
}
```

**change types**

```json
{
  "stable": 3694,
  "new": 190,
  "strengthened": 1018,
  "disrupted": 153,
  "weakened": 210
}
```

**insight categories**

```json
{
  "context_limited_relationship_change": 1149,
  "insufficient_evidence": 46
}
```

**consequence status**

```json
{
  "not_quantifiable": 1195
}
```

**pair window context**

```json
{
  "unavailable": 5265
}
```

**pair window quality**

```json
{
  "high": 2562,
  "limited": 2703
}
```

Insufficient-evidence insight classifications are counted above exactly as emitted. Unconfirmed graph persistence and context-limited insights are separately reported; neither is silently relabeled a confirmed transient. Changed-without-support counts use engine change_type excluding stable/unchanged and no temporal or recurrence support. Graph promotion and governed persistence counts are not interchangeable with temporal support.

## Per-relationship evidence

Relationship | Evaluations | Temporal supported windows | Recurrence supported windows | Governed persistent windows | First temporal support (source clock)
--- | ---: | ---: | ---: | ---: | ---
DO / Influent flowrate | 253 | 0 | 0 | 0 | None
DO / N2O | 253 | 0 | 0 | 0 | None
DO / N2O emission rate | 253 | 4 | 6 | 0 | 2018-10-18 02:00:00
DO / NH4 | 245 | 160 | 0 | 0 | 2018-06-29 07:25:00
DO / NO3 | 253 | 0 | 0 | 0 | None
DO / Temperature | 253 | 0 | 0 | 0 | None
Influent flowrate / N2O | 253 | 0 | 0 | 0 | None
Influent flowrate / N2O emission rate | 253 | 0 | 0 | 0 | None
Influent flowrate / NH4 | 245 | 0 | 3 | 0 | None
Influent flowrate / NO3 | 253 | 10 | 17 | 0 | 2018-09-08 07:25:00
Influent flowrate / Temperature | 253 | 6 | 0 | 0 | 2018-09-13 07:25:00
N2O / N2O emission rate | 253 | 0 | 0 | 0 | None
N2O / NH4 | 245 | 5 | 0 | 0 | 2019-01-31 07:25:00
N2O / NO3 | 253 | 5 | 0 | 3 | 2019-02-11 07:25:00
N2O / Temperature | 253 | 11 | 2 | 0 | 2018-10-15 07:25:00
N2O emission rate / NH4 | 245 | 0 | 0 | 0 | None
N2O emission rate / NO3 | 253 | 1 | 0 | 0 | 2018-09-15 07:25:00
N2O emission rate / Temperature | 253 | 7 | 0 | 0 | 2018-09-18 07:25:00
NH4 / NO3 | 245 | 25 | 0 | 1 | 2018-06-29 07:25:00
NH4 / Temperature | 245 | 144 | 22 | 0 | 2018-06-28 07:25:00
NO3 / Temperature | 253 | 127 | 32 | 0 | 2018-06-29 07:25:00

Full runs, first/last support times and correlation ranges are in FINDINGS.md and raw/assessment.json; raw/edge-results.jsonl retains every pair-window evidence projection and links to full checkpoints. All governed insight records are in raw/insights.jsonl.

## Data quality

Variable | Finite cells | Invalid cells | Minimum | Maximum | Zero cells
--- | ---: | ---: | ---: | ---: | ---:
Influent flowrate | 74171 | 1 | -3.1 | 2808.0 | 9
DO | 74172 | 0 | 0.03 | 10.85 | 0
NH4 | 74172 | 0 | 0.0 | 20.11 | 1245
NO3 | 74172 | 0 | 0.0 | 12.73 | 1320
N2O | 74172 | 0 | 0.0 | 2.1048 | 4774
Temperature | 74172 | 0 | 9.48 | 27.13 | 0
N2O emission rate | 74172 | 0 | 0.0 | 60.37 | 18324

One source flow cell is `???` (data row 54). Existing complete-case governance excludes that row. There are 2851 negative finite flow readings, retained unchanged. Six gaps account for 619 absent five-minute slots relative to a continuous grid. They are not manufactured or interpolated.

Gap start | Gap end | Seconds | Absent 5-minute slots
--- | --- | ---: | ---:
2018-09-01 10:05:00 | 2018-09-01 11:00:00 | 3300.0 | 10
2018-10-18 02:00:00 | 2018-10-19 02:05:00 | 86700.0 | 288
2018-10-28 02:00:00 | 2018-10-28 02:10:00 | 600.0 | 1
2018-12-20 09:50:00 | 2018-12-20 10:20:00 | 1800.0 | 5
2019-01-05 15:50:00 | 2019-01-05 18:10:00 | 8400.0 | 27
2019-02-27 01:00:00 | 2019-02-28 01:05:00 | 86700.0 | 288

Longest constant string-valued source stretches (descriptive audit, not added exclusions):

Variable | Rows | Value | Start | End
--- | ---: | --- | --- | ---
DO | 62 | 0.14 | 2019-02-20 12:35:00 | 2019-02-20 17:40:00
NH4 | 1187 | 0 | 2018-06-14 07:30:00 | 2018-06-18 10:20:00
NO3 | 51 | 3.62 | 2018-08-28 07:00:00 | 2018-08-28 11:10:00
N2O | 212 | 0.0003 | 2018-09-14 18:25:00 | 2018-09-15 12:00:00
Temperature | 79 | 17.54 | 2018-11-08 21:55:00 | 2018-11-09 04:25:00
N2O emission rate | 186 | 0 | 2018-09-17 21:30:00 | 2018-09-18 12:55:00

## Integrity, repeatability and performance

The primary chronological replay took 548.540 seconds including checkpoint serialization. It used one engine process with OPENBLAS_NUM_THREADS=1, OMP_NUM_THREADS=1 and PYTHONHASHSEED=0. Python/platform/packages: raw/freeze.json; CPU details: raw/hardware.txt. This is a shared-machine observation, not a benchmark guarantee.

Input hashes were independently reconstructed for 253 windows. All numeric cells and source order were verified unchanged by normalization. Source and production hashes were verified unchanged. Checkpoint predecessor links, state handoff, row nonoverlap and chronology were checked. Fresh-process repeats matched 3/3 selected windows (first, middle, last). Scope: Full relationship graph excluding runtime_seconds, governed sii_evidence, supplied_reference; ordered input dictionaries retained. Fresh process from original run; each selected window uses its original incoming states.

The primary run log retains numerical runtime warnings. The supplementary descriptive audit initially failed to parse the nonnumeric flow cell; the audit was corrected to handle it, with no change to engine execution or inclusion policy. This development failure is retained in raw/quality-details.json. Production outputs were not repaired or tuned.

## Reproduction and evidence map

Follow METHODOLOGY.md. Exact commands: raw/commands.json. Initial freeze: raw/freeze.json. Prespecified protocol/configuration: raw/protocol.json and raw/config.json. Output freeze: raw/analytical-output-freeze.json. Full engine results and chained state provenance: raw/checkpoints/*.json. Input: raw/normalized.csv, indexed by the checkpoint source row lists. Source quality and exclusions: raw/qualification.json, raw/quality-view.json and raw/quality-details.json. Derived counts: raw/assessment.json. Verification: raw/repeatability.json and raw/final-verification.json.

No accuracy, sensitivity, specificity, false-positive rate, physical loss, emission reduction or economic benefit is inferred. External source matching and event context are discussed only in POSTHOC_CONTEXT.md.

## Additional evidence sufficiency accounting

Of 5,313 possible pair-window slots, 5,265 contain graph edges. The 48 absent slots are the six NH4 relationships in eight windows with constant NH4. They are unavailable correlations, not stable controls. The relationship-analysis module still reports complete in those windows; read coverage alongside status. See raw/omitted-pairs.json.

Mutually exclusive support categories (distinct from change-type categories):

```json
{
  "temporal_False_recurrence_False": 4711,
  "temporal_True_recurrence_False": 472,
  "temporal_False_recurrence_True": 49,
  "temporal_True_recurrence_True": 33
}
```

Graph support channels can overlap. There are 46 insufficient-evidence insight observations and 1,149 context-limited insight observations, not deduplicated incidents. No measurable consequence was quantifiable in any of the 1,195 insights. Read the promoted/governed table at the start of FINDINGS.md before the broader temporal-support runs.
