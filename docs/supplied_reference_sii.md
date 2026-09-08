# Supplied-reference historical SII

The Python authority boundary is `app.engine.sii_engine.evaluate_sii`. Existing
calls with `rows=...` retain their single-dataset behavior. Paired callers use:

```python
result = evaluate_sii(
    columns=["timestamp", "flow", "pressure"],
    reference_rows=reference_rows,
    comparison_rows=comparison_rows,
    numeric_profiles=[{"column": "flow"}, {"column": "pressure"}],
    timestamp_column="timestamp",
    signal_units={"flow": "L/s", "pressure": "kPa"},
)
```

Both datasets contain dictionaries with exactly those columns. Signal names,
order, and declared units form one shared schema: the caller must confirm that
both datasets conform. `None` is an explicit unknown unit, not an inferred unit.
Dataset identities are deterministic content hashes including columns and units;
roles, row bounds, original timestamp bounds, signal identity, engine/version,
and limitations are returned in `supplied_reference` and the governed evidence.
No customer operating-state labels are assigned to either dataset.

The supplied reference replaces internal baseline selection for signal drift,
relationship comparison, operating context, exact like-mode selection, empirical
threshold fitting, temporal math, and covariance. Existing math, thresholds,
quality checks, sensor-health gates, graph analysis, evidence fusion, finding
classification, and condition corroboration remain authoritative. The evaluated
period is the comparison dataset. No App comparison implementation is needed.

Use `analysis_result` for the normal governed findings (`insights`), structural
conditions, evidence index, and bounded `sii_evidence` projection. `findings` is
an alias of those governed insights. Detailed analytical sections remain in the
engine result. Stable and limited outcomes do not require a finding. Existing
engineering priors may be provided with `config.engineering_priors` or
`config.physics_reasoning_config`; no consequence or causal claim is inferred
from the mere presence of two datasets.

## Timing and operating envelope

Each dataset supports 16–12,000 rows and 1–32 numeric signals. Two 8,640-row
periods fit explicitly: paired mode uses the existing `TemporalMathConfig` with
`max_rows=12000` and relationship window limits of 12,000. Smaller explicit
`temporal_config.max_rows` values reject oversized input. The single-dataset
5,000-row temporal default is unchanged. Paired covariance processes every
comparison vector against the reference; its existing recent rolling window
remains bounded. Other module signal/horizon limits remain visible in outputs.

Reference rows never enter comparison history or its persistence clock.
Temporal active rows cover the whole comparison; temporal timestamp indexes
start at comparison row zero. Fixed and adaptive persistence use all comparison
rows. Adaptive persistence retains its existing convention of crediting the
terminal sample one median interval. Timestamps must be strictly increasing,
timezone-aware ISO strings within each dataset; reference and comparison may
have independent or overlapping date ranges. They are never joined into a
synthetic timeline. Uneven intervals retain existing elapsed-time handling.
Without a timestamp column, elapsed evidence is explicitly limited to row
support. Temporal onset/lead-time output remains heuristic evidence, not a
verified physical event or a failure-time prediction.

## Safe failure and read-only behavior

Malformed inputs raise `ValueError` before orchestration: mixed `rows`/paired
arguments, incompatible row schemas, missing/nonfinite/non-numeric signal
values, malformed/unordered timestamps, missing unit declarations, out-of-bound
sizes, unsupported configuration, and cumulative-counter inputs are rejected.
No resampling, signal renaming, unit conversion, or missing-value imputation is
performed at this boundary. Counter support is deliberately excluded because
its existing derived-delta path assumes one dataset.

Paired mode computes fresh data-quality, sensor-health, and operating-context
evidence. It rejects supplied overrides, a telemetry catalog, and authenticated
persistent-memory scope. It neither writes latest runner state nor loads or
updates persistent behavioral memory. Phase 4 memory-dependent sections remain
explicitly limited; multiscale/regime evidence describes the comparison period
itself. This interface does not establish or activate a saved behavioral
baseline. It adds no HTTP endpoint.

Validation covers strict input failure, reference substitution, stable/change
outcomes, comparison-only timing, read-only covariance, governed finding/evidence
construction, and the 8,640-row contract envelope. The real integration fixture
uses 64 rows per period; the envelope check does not run a large replay.
