# Data Requirements

## Required Telemetry Fields
- `timestamp`
- `room_id` or equivalent room identifier
- `temperature`
- `humidity`

## Strongly Recommended (If Available)
- `vpd`
- `hvac_runtime` and/or `hvac_status`
- `dehumidifier_runtime` and/or `dehumidifier_status`
- `airflow` and/or fan runtime/status signals
- `irrigation_event` markers and/or irrigation runtime/status

## Data Quality Requirements
- Timestamps should be parseable and time-ordered.
- Room identifiers should be stable across records.
- Signals should be consistently named over time.
- Missing values should be minimized for relationship and propagation analysis.

## Minimum Pilot Readiness
- At least temperature + humidity + timestamp + room identifier per room.
- Prefer room-level runtime/status context (HVAC/dehumidification/airflow) to improve evidence lineage and propagation pathway clarity.

## Notes
Neraium uses these signals for structural cognition, environmental topology interpretation, replay evidence, continuation window tracking, and convergence/recovery review. It is not used for automated control outputs.
