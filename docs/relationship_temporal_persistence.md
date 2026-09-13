# Temporal relationship evidence

The existing Pearson detector and abrupt classification rules are unchanged.
`app.engine.relationship_change` centralizes classification and strength/promotion
rules used by the baseline service, mode-conditioned analysis and dynamic graph.
Temporal evaluation happens in the graph after sensor-health, confidence, sample
eligibility and data-quality enrichment. Baseline service edges continue to
represent single-window evidence; graph edges retain `single_window_change_type`
and can become `strengthened` or `weakened` through temporal evidence.

For a fixed baseline and compatible relationship/mode, the reducer retains at
most eight chronological observations within 30 days of the latest observation.
A window supports a direction only when its signed correlation displacement from
baseline is at least 0.15 in magnitude, it is eligible, and adjusted confidence
and quality meet the graph floors (defaults 0.45 and 0.35). Six supporting windows
and at least 75% agreement across all retained windows are required. The current
window must also support that direction. Neutral, reversed and poor-quality
windows occupy the horizon without voting for the dominant direction. There is
no delta summation or monotonicity requirement. These are deterministic evidence
criteria, not a statistical independence or probability claim; rolling windows
may overlap.

Promotion accepts the existing abrupt route (default 0.25) or temporal support,
with the existing relationship-strength, eligibility, confidence and quality
gates retained. Returning to baseline stops current promotion immediately.

```python
state = None
for comparison_rows in chronological_windows:
    result = evaluate_sii(
        **fixed_reference_arguments,
        comparison_rows=comparison_rows,
        relationship_persistence_state=state,
    )
    state = result["relationship_graph"]["relationship_persistence_state"]
```

State is detached JSON-compatible evidence, never automatically loaded or saved.
Callers must carry it between evaluations of the same dataset/facility. Without
state, only one temporal observation is available; sample count cannot create
history. Baseline correlation/window, supplied reference identity/units, mode or
edge-basis changes reset support. Missing pairs lose their retained history.
Identical retries do not add observations; conflicting retries, backwards times,
missing times and invalid windows cannot confirm temporal persistence. Supporting
windows retain timestamps, source row anchors, signed displacement, quality and
confidence; supplied-reference evaluations also retain source dataset IDs. The
bounded supporting-window evidence survives the governed transport projection.

No database migration is required. `minimum_persistence_observations` remains a
legacy configuration alias for `minimum_sample_observations` only. Edge
`persistence_factor` now describes cross-window evidence; its former sample-based
value is `sample_sufficiency_factor`. Component coherence uses the same numerical
sample-sufficiency term as before, now named explicitly. Relationship importance
likewise renames `ranking_factors.persistence` to `sample_sufficiency` without
changing score weights. Consumers of those old factor names must update. Existing
single-window callers retain abrupt promotion behavior and receive unconfirmed
or limited temporal evidence. No causal, diagnostic or prescriptive output is
introduced.
