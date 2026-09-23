# Dataset provenance

Original: `/home/ubuntu/Data.csv`

SHA-256: `29a2db4e54d5f5278d2c05732d62cf877f939f87312e035ddb700c385c3550a8`

Size: 4,537,154 bytes. Recorded before inspection at `2026-09-23T06:54:21.208962+00:00`.

Engine: `97d267d317fcce4b4424cf2141e97e87680acfc0`. Full freeze and environment: `raw/freeze.json`.

The user supplied this file as previously unseen real full-scale wastewater telemetry. That description is provenance supplied by the user; source identity and plant scale require independent documentation, examined only after analytical output freeze. Prior model-training exposure cannot be verified. The CSV itself contains no facility identifier, publication citation, units, timezone, calibration records, operating-event labels or independent ground truth.

Source schema: Time, Influent flowrate, DO, NH4, NO3, N2O, Temperature, N2O emission rate. There are 74,172 data rows, from `2018-06-14 07:30:00` through `2019-03-01 00:00:00`, in unspecified source-clock time. Cadence counts and per-variable validity, ranges and zeros are in `raw/qualification.json`. The long record is not assumed to represent continuous sensor validity.

Derived `raw/normalized.csv` changes timestamp formatting only and preserves all numeric cell strings and source row order. The wrapper's complete-case exclusion is documented in `raw/quality-view.json`, including source row positions. All finite values, including negative flow, zeros, outliers and constant stretches, remain eligible under the existing input policy. Units remain null throughout the blind analysis.

External source contextualization, if established, is recorded separately after output freeze. It is not independent ground truth for the engine's relationship-change findings.

## Post-freeze source verification

A byte-identical file was independently downloaded from [Zenodo DOI 10.5281/zenodo.21135508](https://zenodo.org/records/21135508). The deposit identifies real full-scale wastewater telemetry from Denmark. The exact match, attribution, license, metadata row-count discrepancy and absence of independent event labels are documented in POSTHOC_CONTEXT.md and raw/posthoc/. This verification occurred only after blind outputs and repeats were sealed.
