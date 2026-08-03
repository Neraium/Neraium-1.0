# Operating Context v1

## Purpose and architecture

Operating Context v1 extends the canonical Evidence Package v1 with descriptive,
auditable facts about the conditions surrounding an exact-baseline comparison. It
does not change correlation mathematics, relationship selection, or package identity.

The data path is deliberately source-agnostic:

1. A connector or upload adapter receives a source tag/column.
2. Ingestion records normalized units, telemetry classification, and a canonical
   telemetry role in the existing telemetry signal catalog.
3. While complete rows are still available, the comparison completion flow creates
   full-window summaries keyed only by canonical role.
4. The Evidence Package builder consumes those persisted summaries. GET routes do
   not re-read CSVs, query connectors, or recalculate context.

Connector- and site-specific tag mapping belongs upstream of the analytical layer.
Operating Context never resolves roles from raw names. The current upload classifier
is the existing semantic-mapping adapter; configured BAS, SCADA, PLC, historian,
database, time-series, and API adapters can provide the same catalog contract.
Ambiguous or missing mappings are not guessed.
Broad scheduled-load and weather categories do not themselves prove process demand
or environmental temperature: those physical roles require more specific semantic
classification metadata.

## Schema

Eligible new packages contain `operating_context` with schema version
`operating-context-v1`:

- `comparison_state`: nullable label, controlled state type, and deliberately
  unknown state confidence.
- `load_context`: baseline/comparison mean and range for canonical
  `process_demand`, including normalized unit and source lineage.
- `equipment_configuration`: summaries only for unambiguous canonical equipment
  enable/state roles.
- `control_context`: summaries for unambiguous canonical control-command/setpoint
  roles.
- `environmental_context`: summaries only when a canonical environmental role exists.
- `baseline_window` and `comparison_window`: persisted timestamp bounds.
- `transition_context`: deterministic direction and documented method.
- `comparability`: controlled level, explicitly defined score/method, matched
  dimensions, and unavailable dimensions.

Controlled enums cover operating state (`steady`, `ramping_up`, `ramping_down`,
`transitioning`, `unknown`), transition direction (`increasing`, `decreasing`,
`stable`, `mixed`, `unknown`), comparability (`high`, `medium`, `low`, `unknown`),
and source (`telemetry`, `analysis_metadata`, `baseline_model`, `replay`,
`not_available`). Pydantic rejects additional values.

## Deterministic calculations

Baseline mean/min/max come from the selected persisted Behavioral Digital Model's
full-window signal characteristics. Comparison mean/min/max are calculated once from
the complete comparison rows during completion. A role is usable only when exactly
one signal maps to it in each period.

Transition direction uses canonical process demand. It compares the median of the
first 10% of samples with the median of the last 10%. A difference is stable when its
absolute value is no greater than the larger of 5% of the observed range or 2% of the
early median. Five ordered segment medians detect material changes in both directions
and classify those series as mixed; otherwise the early/late sign determines increasing
or decreasing. No relationship
drift or raw first/last sample is used. State confidence remains `unknown` with a null
score because this is a descriptor, not an operating-state matching model.

Comparability uses range overlap. For each usable dimension, overlap is intersection
width divided by the smaller observed range. Process demand is required. `high`
requires at least 0.8 overlap for every available checked dimension, `medium` requires
nonzero process-demand overlap, and `low` means zero process-demand overlap. The score
is the arithmetic mean of the explicit overlap ratios. Without process demand the
result is `unknown` and has no score. Exact baseline identity alone never contributes.
Overlap is calculated only when both periods have identical normalized engineering
units (or the canonical role is explicitly dimensionless). Missing or mismatched units
make the dimension unavailable; Operating Context v1 performs no unit conversion.

## Evidence, compatibility, and unsupported data

Stable supporting evidence records preserve demand ranges, available control means,
both windows, and the comparability result in deterministic order. Entries include
canonical role, source variable lineage, unit, and calculation method; they contain no
expected engineering range.

The Evidence Package remains `evidence-package-v1`. UUIDv5 inputs, package number,
revision, endpoints, legacy finding projection, relationship values, and replay are
unchanged. Stored old packages validate with a nullable `operating_context`; old or
internal-window analyses do not receive fabricated context. Missing equipment,
staging, mode, setpoint, or environmental mappings produce empty lists and explicit
unavailable dimensions.

## Known limitations and deferred work

This version supports unambiguous canonical roles only and intentionally omits
multi-signal aggregation and unit conversion. The Adaptive Operating-State Engine is
deferred. This change does **not** implement clustering, seasonal state discovery,
weather normalization, causal propagation, physics consistency, ranked hypotheses,
field dispositions, historical precedent, Knowledge Conflicts, Knowledge Reviews,
or governance rollout.
