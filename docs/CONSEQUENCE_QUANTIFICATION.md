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

`services.measurable_consequence` checks persistence, explicitly comparable
operating context, ownership of every source relationship, exactly one mapped
resource series, and an exact single finding
window. It excludes observations outside that window without interpolating new
boundary samples. Unknown resources, ambiguous multiple resource series, missing
units, absent persistence, or insufficient intervals produce `not_quantifiable`.

Resource mapping requires explicit `resource_type` and a matching rate unit.
A bare `gpm`, `kW`, or `scfm` unit, a tag name, or even the canonical
`electrical.active_power` name does not supply that resource identity. When
`consequence_profile_key` is supplied, it must agree with both resource and rate
unit. Conflicting source-unit fields or multiple eligible resource series withhold
quantification.

| Profile | Explicit resource | Rate unit | Cumulative unit |
| --- | --- | --- | --- |
| `water_gpm` | `water` | `gpm` | `gal` |
| `electricity_kw` | `electricity` | `kW` | `kWh` |
| `steam_lb_per_hr` | `steam` | `lb/hr` | `lb` |
| `chemical_feed_gal_per_hr` | `chemical` | `gal/hr` | `gal` |
| `compressed_air_scfm` | `compressed_air` | `scfm` | `scf` |

Historical API aliases `steam_lb_hr` and `chemical_gal_hr` remain available.
The adapter preserves all five profiles; this change does not expand the
connector registry's existing canonical concepts or unit-normalization vocabulary.

### Connection configuration and acquisition gaps

HTTPS and historian connection create/update configuration accepts an optional
`consequence` object in the existing stored `configuration` / `safe_config` JSON.
It is analytical configuration, not a provider query parameter. Each entry is keyed
by the explicitly mapped canonical signal UUID, scoped to that connection:

```json
{
  "consequence": {
    "signals": {
      "a19db5be-5ca1-5373-a9e4-6957e9f54c43": {
        "resource_type": "water",
        "consequence_profile_key": "water_gpm",
        "rate_unit": "gpm",
        "max_gap_seconds": 120
      }
    }
  }
}
```

The 120-second value is an example requiring source-specific justification, not a
recommended cadence. Configuration requires all four fields, a finite positive
numeric gap, an exact resource/profile/unit match, and at most 64 signal entries.
The operational analysis service reads the scoped connection configuration and
carries it into the canonical signal catalog. Cross-connection metadata binding
is rejected. No database migration is needed.

The adapter passes the catalog's explicit `max_gap_seconds` to the package. For
upload/custom catalogs without that field, an explicitly supplied expected-behavior
`max_gap_seconds` can provide the acquisition policy. Missing or invalid limits
produce `not_quantifiable`; the platform never substitutes the package default,
polling interval, or an inferred sample cadence. Expected-behavior generation no
longer invents a 3600-second limit. No Siemens Building X cadence is assumed.

Provenance records the effective gap, policy method/version, policy source,
connection ID when available, and exact signal metadata. Adjacent intervals longer
than the limit are skipped; no boundary samples or missing intervals are
interpolated. If every interval is unsupported, no amount or duration is emitted.
Otherwise duration and amount cover only contributing intervals. Changing connection
configuration does not recalculate an existing completed analysis window.

### Commercial flow examples

For resort chilled-water circulation, explicitly configure `water` / `gpm` /
`water_gpm`. For wastewater throughput, use the same explicit `water` classification
under the package contract; it describes a flow volume, not water consumption,
waste, a leak, or avoidable loss. The UI labels this quantity **Water flow**.

The existing connector volumetric-flow concept normalizes values to `L/s`.
With an explicit `rate_unit: "gpm"`, the adapter uses the existing telemetry unit
normalizer to convert aligned observed and expected rates from `L/s` to `gpm`
before invoking the package. Original model observations remain in provenance,
alongside conversion identity/version and the converted package inputs. Unsupported
conversions withhold quantification; units are never merely relabeled.

Both commercial certification fixtures use a validated expected-response model,
seven hourly samples, and a persistent finding with comparable operating context.
An observed-minus-expected difference of +10 or -10 gpm yields approximately
+3,600 or -3,600 gal over 21,600 seconds (ordinary floating-point unit conversion
roundoff is retained). Missing resource configuration yields `not_quantifiable`.
An explicit 1800-second gap limit rejects all six hourly intervals.

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
The frontend passes recorded summary fields through and never integrates observations.
Upload evidence snapshots also preserve the exact canonical consequence object.
Certification tests disable quantification and expected-behavior evaluation during
artifact replay and repeated Findings API reads, and compare the results exactly
with the generated object and the shared frontend fixtures.

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
span excluded gaps. `not_quantifiable` has an explicit reason/limitation, no
cumulative amount, and no invented duration; it is distinct from a supported zero.
The standalone calculation endpoint retains the package API semantics (including
its 3600-second default when no gap is supplied); it does not certify an acquisition
or persist a finding. Runtime finding certification requires the explicit policy
described above.

## Dependency and deployment

`backend/requirements.txt` pins the package's immutable source archive and SHA-256.
This needs no Git binary or credentials in either production Docker build context.
Merge the package PR first, then the platform PR. The source pin remains reproducible
after merge. No PyPI release, mainline merge, or production deployment is performed
by opening these PRs. Local development can install a checkout with `pip install -e
/path/to/neraium-consequence` after installing backend requirements.
