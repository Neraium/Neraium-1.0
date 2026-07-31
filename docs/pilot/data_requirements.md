# Hydronic Pilot Data Requirements

## Required identity and time fields

- A timezone-aware `timestamp` (or an explicitly mapped equivalent).
- Stable `site_id` and `system_id` values in the facility context.
- Stable raw tag names and their normalized signal names.
- Units and expected sample rate for each mapped signal.

## Minimum useful telemetry

Provide at least three connected measurements for one defined system boundary. A strong first system includes:

- supply and return temperature;
- supply and return pressure or differential pressure;
- flow;
- pump run status and speed or command;
- valve position or command;
- equipment enable and setpoint;
- electrical power or current when available.

For filtration and treatment systems, add filter differential pressure, tank level, makeup flow, conductivity, pH, ORP, turbidity, and backwash state where applicable. For heat exchangers, include both entering/leaving temperatures and flow on each available side.

## Operating context

Provide state signals that distinguish expected modes: occupied/unoccupied, enabled/disabled, lead/lag pump, scheduled rotation, startup/shutdown, economizer/free-cooling state, backwash, cleaning, setpoint changes, and seasonal changeover. Mode labels prevent expected transitions from being compared with incompatible baseline periods.

## Historical event file

The backtest event CSV requires:

- `event_at`: timezone-aware alarm, work-order, inspection, or visible-failure time;
- `event_id`: stable event identifier;
- `system_id`: system boundary involved;
- `event_type`: alarm, work order, inspection, or failure;
- `related_signals`: pipe-separated normalized signal names when known;
- `summary`: short factual description.

Do not manufacture event timestamps after seeing Neraium output. Freeze the event file and its hash before running the benchmark.

## Readiness thresholds

- At least 30 days of representative history; 90 days is preferred when modes vary by schedule or season.
- At least 95% timestamp coverage and 90% accepted-row coverage for the primary system.
- Enough samples to observe each common operating mode repeatedly.
- A named facility engineer who can verify mappings and review outcomes.
- Timestamped alarm/work-order history for the same period.

Missing or flatlined data is retained as an explicit limitation. Neraium must withhold unsupported interpretation rather than fill gaps with assumed engineering facts.
