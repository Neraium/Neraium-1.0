# Consequence Quantification

Consequence Quantification extends Neraium's existing relationship-evidence pipeline. It is not a separate anomaly detector, leak detector, diagnostic engine, or recommendation engine.

## Boundary

The layer receives evidence that already contains an observed engineering rate and an expected engineering rate for aligned timestamps. It may quantify the physical magnitude associated with that deviation when the telemetry is sufficient.

It does **not** infer cause.

Valid outcomes are:

1. `quantified` — enough valid aligned evidence exists to calculate a measurable consequence.
2. `not_quantifiable` — the relationship finding may remain valid, but the available evidence does not support a physical accumulation.

A relationship finding must never be downgraded merely because the consequence cannot be quantified.

## Current integration

The implementation lives in `backend/app/services/consequence_quantification.py` and is exposed through the existing Findings router:

- `GET /api/findings/consequence/profiles`
- `POST /api/findings/consequence/quantify`

This keeps consequence calculation downstream of the existing finding/evidence path.

## Calculation

For each valid adjacent observation pair, Neraium computes the residual:

`observed - expected`

It then applies timestamp-aware trapezoidal integration using the resource profile's rate period. This supports irregular cadence without pretending missing evidence exists.

Invalid observations are removed. Intervals beyond a configured maximum gap are excluded rather than interpolated.

The result records the exact contributing intervals, source relationship IDs, and source tag IDs so the final amount can be reproduced from evidence.

## Initial resource profiles

| Profile | Rate | Accumulated unit |
| --- | --- | --- |
| `water_gpm` | gpm | gal |
| `electricity_kw` | kW | kWh |
| `steam_lb_hr` | lb/hr | lb |
| `chemical_gal_hr` | gal/hr | gal |
| `compressed_air_scfm` | scfm | scf |

Profiles are deliberately generic. Wastewater and chilled-water systems are applications of the same engine, not separate product modes.

## Evidence language

Supported language includes:

- associated measurable deviation
- observed excess relative to expected behavior
- associated cumulative volume
- associated additional electrical consumption

Do not convert this into causal language such as leak volume, failure loss, root cause, probable cause, suspected cause, or cause not determined.

## Platform UI contract

When a canonical finding includes a `consequence` object with `status: quantified`, the evidence dashboard should render a **Measurable Consequence** block containing only values actually supplied by the evidence package, such as:

- observed deviation
- persistence duration
- cumulative amount and unit
- support level
- relationship contribution when mathematically supplied

When the object has `status: not_quantifiable`, the UI may show `Consequence not quantifiable from available evidence.` It must never synthesize a numeric value.

## Extraction boundary

The service has intentionally minimal dependencies so it can later be extracted into a dedicated repository/package (proposed name: `Neraium/neraium-consequence`) without changing its evidence contract. Until repository creation is available to the connected GitHub tooling, the authoritative implementation remains in the platform repository so integration can proceed without a disconnected prototype.
