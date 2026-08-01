# Golden Nugget historical assessment

The Golden Nugget workflow is the pilot path for answering one bounded question:

> Did Neraium surface a persistent, evidence-backed relationship change before a known tower event?

It is intentionally separate from live monitoring and from the legacy single-period upload path.

## Workflow contract

1. `POST /api/pilot-assessments/intake` accepts a baseline CSV and a later comparison CSV.
2. Intake profiles every column and returns inferred timestamp and signal mappings. Missing, text-only, and otherwise unusable columns are returned before analysis.
3. `PUT /api/pilot-assessments/{id}/mapping` records the timestamp, canonical signal name, source column in each period, engineering unit, system name, and analysis role.
4. `POST /api/pilot-assessments/{id}/analyze` applies the baseline quality gate. It withholds the baseline when coverage, duration, timestamps, or independent usable signals are insufficient.
5. Accepted data is divided into startup, shutdown, staging, stable operation, stable low load, and stable high load. Only like-for-like stable modes can support a finding.
6. Each relationship change reports before/after behavior, magnitude, persistence windows, first surfaced timestamp, limitations, and a SHA-256-bound CSV containing the exact source rows used.
7. `POST /api/pilot-assessments/{id}/event` is rejected until analysis reaches a terminal state. The analysis record explicitly states that no event timestamp was used.
8. Engineer feedback is appended with an immutable ID, category, note, actor, and timestamp.
9. `GET /api/pilot-assessments/{id}/report.html` exports the pilot assessment.

## Baseline refusal

The current deterministic gate requires:

- at least 48 usable timestamped baseline records;
- at least 12 hours of baseline duration;
- at least 80% timestamp coverage;
- no more than 5% duplicate timestamps; and
- at least two independent analysis signals after flatline, sparse, noisy, duplicate, and alignment checks.

A withheld baseline produces a quality report but no finding.

## Evidence thresholds

Relationships are assessed only within the same stable operating mode and system. A candidate needs a usable baseline relationship, a material correlation or response-slope change, and support in at least two post-change windows with at least 60% persistence after onset.

The record export for every supporting relationship contains:

- period (`baseline` or `comparison`);
- original CSV source-row number;
- timestamp;
- assigned operating mode; and
- the two exact signal values used.

## Backtest interpretation

The event backtest reports when Neraium first surfaced each finding, lead time relative to the known event, observable persistence through the event, and whether complete post-repair evidence windows stopped supporting the change. If the supplied data cannot answer a persistence or recovery question, the result is `null` with an explicit limitation rather than an inferred answer.
