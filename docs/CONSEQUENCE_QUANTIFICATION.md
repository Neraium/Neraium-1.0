# Measurable consequence

The sole consequence engine is the standalone `neraium-consequence` package,
extracted from this repository's PR #124 / merge
`74a7d4bf86d2f55f51a8a4cded2bef612cffbe3e`. The original
`app.services.consequence_quantification` implementation is removed.

## Data flow

Telemetry -> quality gates -> operating context -> validated expected relationship
model -> persistent finding with an exact evidence window -> timestamped
observed/expected rates -> `neraium_consequence.quantify_consequence` -> canonical
finding `measurable_consequence` -> immutable canonical artifact -> bounded product
projection -> Finding Review / Evidence Record `EvidenceDashboard`.

`expected_behavior.evaluate_expected_behavior` exposes a time series from the
already selected, validated, operating-mode-matched expected-response model.
It retains invalid/missing predictor rows. It performs no consequence integration.
Models with a nonzero sample lag withhold the series until timestamp-based lag
alignment is supported. A median expected value is never expanded into a series.

`services.measurable_consequence` checks persistence, ownership of every source
relationship, exactly one mapped resource series, and an exact single finding
window. It excludes observations outside that window without interpolating new
boundary samples. Unknown resources, ambiguous multiple resource series, missing
units, absent persistence, or insufficient intervals produce `not_quantifiable`.

Resource mapping requires an explicit catalog `consequence_profile_key` plus
matching `canonical_unit`/`engineering_units`/`unit`, or an explicit `resource_type`
plus matching rate unit. The existing canonical `electrical.active_power` identity
with `kW` also maps exactly. Raw tag names and correlation deltas never establish
resource identity. Connector catalog admission continues to enforce its existing
canonical schema; adding resource identities to that catalog is separate work.
Upload/catalog callers can use explicit metadata for all five package profiles.

Supported profiles: `water_gpm`, `electricity_kw`, `steam_lb_per_hr`,
`chemical_feed_gal_per_hr`, `compressed_air_scfm`. Historical API aliases
`steam_lb_hr` and `chemical_gal_hr` remain available.

## Contract and evidence boundary

`measurable_consequence` is recorded on canonical conditions/insights, retained by
Evidence Package serialization and finding workflow snapshots, and exposed in the
Findings API. Historical records without it receive an explicit insufficient state;
read paths do not reconstruct historical amounts with a newer model.

Both outcomes retain package methodology/version and supplied provenance. The
adapter also retains the exact expected-model evidence, signal mapping, and finding
window. Canonical attachment runs after presentation text sanitization to avoid
rewriting source identifiers. Product projections may bound detailed evidence;
the existing projection qualification and canonical artifact remain authoritative.
The frontend selects summary fields and never integrates truncated observations.

The result contains no inferred cause, probable cause, root cause, diagnosis,
automated corrective action, optimization advice, or monetary savings. Existing
legacy fields in surrounding platform code are not extended by this integration.
Support level is preserved when explicitly supplied; it is not synthesized from a
model score. Missing support displays as "Not supplied".

## API

- `GET /api/findings/consequence/profiles`
- `POST /api/findings/consequence/quantify`

These authenticated calculation endpoints delegate directly to the package. A POST
calculates supplied evidence; it does not mutate a finding or bypass the canonical
pipeline's ownership gates. Zero or one observation returns `not_quantifiable`.
Observation values are preserved through request parsing so invalid numeric and
quality values reach package validation rather than being silently coerced.

Quantified summary (full result also contains interval decisions and provenance):

```json
{"status":"quantified","resource_type":"water","direction":"above_expected","cumulative_amount":12840.0,"cumulative_unit":"gal","duration_seconds":21600,"support_level":"high","methodology":"timestamp_aware_trapezoidal_integration","methodology_version":"1.0.0"}
```

Insufficient summary:

```json
{"status":"not_quantifiable","statement":"Consequence not quantifiable from available evidence."}
```

A supported zero is quantified. Amounts retain their sign; mixed deviations may
cancel. Duration sums contributing intervals, while the calculation window can
span excluded gaps. The default maximum gap is 3600 seconds; acquisition systems
should provide their stricter continuity limit through expected-behavior config.

## Dependency and deployment

`backend/requirements.txt` pins the package's immutable source archive and SHA-256.
This needs no Git binary or credentials in either production Docker build context.
Merge the package PR first, then the platform PR. The source pin remains reproducible
after merge. No PyPI release, mainline merge, or production deployment is performed
by opening these PRs. Local development can install a checkout with `pip install -e
/path/to/neraium-consequence` after installing backend requirements.
