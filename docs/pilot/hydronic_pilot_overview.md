# Hydronic Systems Pilot Overview

## Product claim under test

Neraium detects meaningful system-level change earlier than existing alarms, using data already collected, and shows the evidence behind every finding.

The first pilot is limited to complex water and hydronic systems inside large facilities: chilled-water and condenser-water loops, filtration systems, pumps, heat exchangers, pressure zones, and related water infrastructure. It is not a test of a universal infrastructure platform.

## What Neraium contributes

- Uses existing BAS, BMS, historian, controller, and maintenance data; no proprietary sensor package is required.
- Compares connected signals and relationship structure, not only individual thresholds.
- Conditions comparisons on operating mode where the available data supports it.
- Requires persistence and corroboration before surfacing a finding.
- Shows observed changes, source signals, time windows, limitations, and verification checks.
- Keeps operator feedback and case outcomes as append-only history without rewriting the original evidence.

Neraium is read-only. It does not control equipment, claim verified causation, or replace facility engineering judgment.

## Three pilot outcomes

1. At least one meaningful change is identified before the associated existing alarm, work order, or visible failure.
2. Facility engineers rate the evidence and suggested checks as understandable and useful.
3. The number of irrelevant findings remains within the pre-registered pilot threshold.

Success thresholds, exclusions, and calculation rules must be frozen before reviewing pilot outcomes. See [pilot_success_criteria.md](pilot_success_criteria.md).

## Workflow

1. Register the site, systems, equipment boundaries, signal mappings, units, and expected modes.
2. Import representative history and approve a baseline period.
3. Replay historical telemetry chronologically against timestamped alarms and work orders.
4. Start read-only live ingestion and review findings in the order `System Status -> Findings -> Evidence -> Outcome`.
5. Record case state, work-order reference, operator judgment, and eventual outcome.
6. Review weekly metrics and investigate every irrelevant or missed finding.

## Historical benchmark

Run the chronological backtest with:

```bash
PYTHONPATH=backend ./.venv/bin/python scripts/hydronic_pilot_backtest.py \
  telemetry.csv events.csv --output output/hydronic-backtest.json
```

The runner hashes its inputs and configuration and sends each analysis only rows available at that point in time. Event data requires `event_at`; recommended fields are `event_id`, `system_id`, `event_type`, `related_signals`, and `summary`.
