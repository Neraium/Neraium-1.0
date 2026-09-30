# Historical PoV adapter

`app.services.historical_pov` is a dedicated read-only adapter for the existing
paired SII engine and `relationship-qualification.v2`. It does not change the
upload pipeline, mathematical contract, or thresholds. It reads no files itself,
writes no artifacts, and accepts no event labels, event timing, or outcomes.

## Interface

```python
from pathlib import Path
import json
from app.services.historical_pov import prepare_historical_pov, run_historical_pov

# The two files must contain only the blind export and reviewed declarations.
metadata = json.loads(Path("acquisition.json").read_text())
prepared = prepare_historical_pov(
    csv_bytes=Path("telemetry.csv").read_bytes(), metadata=metadata)
# Alternatively: prepare_historical_pov(rows=list_of_dicts, metadata=metadata)
result = run_historical_pov(prepared)

# Optional continuation: absolute slot count, not number of additional slots.
first = run_historical_pov(prepared, stop_after_slots=1)
remaining = run_historical_pov(prepared, checkpoint=first["checkpoint"])
```

`PreparedPoV` contains a detached immutable serialized source/plan/profile bundle.
`prepared.inspect()` returns a copy. Preserve that bundle and the returned result
with the original source. A checkpoint binds the full bundle and the previous
engine state; it cannot continue with another reference, declaration, or source.
It detects accidental changes, not maliciously re-signed state. Checkpoints
remain caller-owned trusted evidence, consistent with the engine contract.

Admission errors raise `PoVAdmissionError`, with `reason_code` and
`not_quantifiable=True`, before any analysis is run. Engine/continuation failures
also stop rather than silently replacing evidence with a new ledger.

## Minimal external declarations

The initial adapter supports **exactly two numeric signals and one explicitly
declared homogeneous global context**. It does not invent a context or try to
freeze data-dependent like-mode selections. Additional pairs or mode-conditioned
plans require a separately reviewed extension, not automatic fallback.
Do not split a multi-pair assessment into one-pair runs to evade the implemented
pair-family assurance allocation. This version is for one predeclared pair.

All keys below are required; unknown keys and extra CSV columns are rejected.
Values in this example are **hypothetical synthetic values, not Henderson facts**.
They are not a justification for any actual data. The small example is expected
to be statistically limited, even if all declarations hold.

```json
{
  "signals": {
    "s01": {
      "unit": "kPa", "bounds": [0, 100], "bounds_unit": "kPa",
      "bounds_basis": "Hypothetical instrument specification A."
    },
    "s02": {
      "unit": "degC", "bounds": [-20, 80], "bounds_unit": "degC",
      "bounds_basis": "Hypothetical instrument specification B."
    }
  },
  "timestamp": {
    "column": "timestamp", "mode": "timezone_aware",
    "basis": "Hypothetical synchronized fresh paired measurements in UTC."
  },
  "acquisition": {
    "namespace": "hypothetical-export",
    "identity": {"kind": "source_row", "fresh_nonreplayed_rows": true},
    "basis": "Hypothetical single export: each row is a fresh acquisition, no replay or interpolation."
  },
  "grouping": {
    "kind": "independent_acquisitions", "justified": true,
    "basis": "Hypothetical independently reset experimental runs, one paired acquisition per run."
  },
  "dependence_assumption": "independent_groups_conditional_on_context_and_schedule",
  "independence_basis": "Hypothetical independently initiated runs with no shared residual dependence conditional on context and schedule.",
  "schedule": {
    "assumption": "predeclared_noninformative",
    "basis": "Hypothetical fixed measurement/export schedule, no value-triggered retention or event-centered selection."
  },
  "context": {
    "selection": {},
    "basis": "Hypothetical common controlled operating context across all rows."
  },
  "coverage_period_seconds": 420,
  "plan": {
    "reference_epoch_rows": [8, 8],
    "comparison_rows": [16, 16, 16, 16, 16, 16],
    "basis": "Hypothetical fixed chronological counts chosen without seeing values or event information; justified seven-minute coverage.",
    "declared_before_analysis": true,
    "event_independent": true
  }
}
```

The CSV for this example has exactly `timestamp,s01,s02`, 112 rows, and enough
elapsed coverage (e.g. one-minute spacing). Spacing is **not** the justification
for independence. The declaration of independent resets is the hypothetical
justification. Merely copying this example does not establish it.

Where native acquisition/group identities exist, replace the relevant objects:

```json
{
  "identity": {"kind": "column", "column": "acquisition_key"},
  "grouping": {
    "kind": "column", "column": "independent_block_key",
    "justified": true,
    "basis": "Owner-reviewed explanation of independence between the named blocks."
  }
}
```

Here `identity` replaces `acquisition.identity`; `grouping` replaces the top-level
object. Include those key columns in the CSV/rows as nonempty strings. A group
may include dependent measurements and span reference epochs, but may not cross
from reference to comparisons or between comparison slots. Native acquisition
keys must identify real acquisitions consistently within the declared namespace.
The `source_row` alternative requires an explicit fresh/nonreplayed attestation;
its IDs bind this exact source and cannot detect repackaged duplicates across
different exports. Use stable native keys when that distinction is needed.

`timestamp.mode` also accepts `naive_historical_source_clock`, using exact
`YYYY-MM-DD HH:MM:SS` timestamps and retaining the engine's timezone limitation.
Clock semantics, acquisition/aggregation rules, context, bounds, grouping and
coverage must be documented by the owner. Bounds are support bounds from
instrumentation/configuration, never sample minima/maxima. `bounds_unit` explicitly
binds their units; the adapter performs no unit conversion.

`justified=true` is a mandatory owner declaration backed by `basis`, not a machine
proof of independence. Blank/missing/unknown declarations abstain. The adapter
does not interpret autocorrelation, cadence, duplicate values, or row counts as
evidence of independence. A false statement remains outside the integrity
contract; require substantive acquisition review before providing this metadata.

## Frozen plan and generated metadata

The owner and blind analyst agree the reference epoch/comparison record counts
and their basis **before examining relationship outcomes**. Counts partition all
source records in order with no gaps or discarded tail. Neraium generates:

* Source SHA-256 (exact CSV bytes, or canonical JSON for supplied rows).
* Assessment/profile IDs binding the source, complete declarations and adapter
  version; a separate exact acquisition-profile hash.
* Acquisition IDs from declared namespace and native keys, or attested fresh
  source-record identity; group IDs only from the declared grouping rule.
* Context, epoch and slot IDs, immutable source locators, and exact timestamp
  schedules. IDs and reference/slot plans never depend on detected outcomes.
* One-based source **record** mappings, excluding the CSV header. These are not
  physical line numbers: CSV quoted fields may span lines.

The immutable bundle retains the original CSV text (including BOM/line endings)
or original JSON rows and projected numeric rows. The result retains the source,
declarations, plan mappings and profile, so inputs can be reconstructed exactly.
No timestamp normalization, sorting, imputation, deduplication, value clipping,
sampling, or unit conversion is performed. Conversion from numeric strings to
binary64 values is explicit in the prepared projection; originals are retained.

Every reference/comparison must meet the existing 16–12,000-row paired boundary.
At least two reference epochs each require three observations and span at least
T; the pooled reference spans at least 2T; comparisons span at least T. All source
timestamps must be strictly increasing and match the declared clock mode. Every
slot is preflighted before evaluation. A changed profile/reference or overlapping
group is rejected; no new state is substituted to avoid a contradiction.

## Results and limitations

`slots` is chronological and contains the qualification assessment, directional
support, qualified persistence, descriptive persistence factor, correlations,
reference qualification ID, evidence limitations, supplied-reference provenance,
and producer-issued evidence registry. The checkpoint contains the exact returned
`relationship_persistence_state`, including the frozen reference and lifetime
reuse ledger. Resume returns only newly evaluated slots.

`not_quantifiable` means a slot's qualification status is not `sufficient`; the
top-level flag is true if any returned assessment is not quantifiable. A
sufficient comparison without six supporting windows is not a qualified
persistence detection, but is not automatically "not quantifiable." Limited
reference precision/variance remains an abstention, not a negative fault label.
Per-window evidence and deeper reference limitations remain in the registry/state.
The adapter reports no event verdict or fault probability.

When the existing engine produces no Pearson edge (for example a constant
signal), the slot is explicitly insufficient/not quantifiable. Prior state stays
unchanged and no vote is manufactured; subsequent qualification sees that planned
slot as missing/neutral. This is distinct from a failed engine module, which stops
the run. A wholly constant initial slot may therefore have an empty checkpoint
ledger, which remains bound to its source/profile and completed slot count.

Blindness requires an external process: use opaque names and broad,
event-independent source/plan selection. Keep truth labels with a separate
custodian until results are frozen. Unknown fields are rejected, but software
cannot detect event hints hidden in allowed names or free-text declarations.
Do not put such information there. Event-centered export selection cannot be
made noninformative by merely removing event labels.
