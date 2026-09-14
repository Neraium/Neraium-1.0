# Governed relationship recurrence evidence

Recurrence is an independent, retrospective association-evidence channel. The
continuous reducer in `app.engine.relationship_change`, its thresholds, promotion
rules, changed-edge metrics and persistence fields are unchanged. Recurrence
does not set `persistent_relationship_change`, change an edge's classification,
or enter `changed_edges`. A sustained displacement is one episode regardless of
its duration or sample count. One transient and alternating-direction behavior
cannot establish same-direction recurrence.

The versioned `relationship_recurrence_v1` policy is deterministic:

| Criterion | Policy |
| --- | --- |
| Episode count | At least 3 completed episodes |
| Episode support | At least 2 consecutive acceptable, non-overlapping windows |
| Displacement | Absolute signed displacement from the fixed baseline >= 0.15 |
| Direction | All counted episodes share the same sign of displacement |
| Return / separation | An acceptable window with absolute displacement < 0.15 closes an episode and separates it from the next |
| Horizon | All retained windows must start within 30 days of the evaluation end |
| Opposite support | Any opposite run with at least 2 consecutive acceptable windows vetoes the entire candidate, including an open opposite episode |
| Resource bound | At most 256 retained windows per relationship |
| Gates | Existing graph eligibility, adjusted confidence and data quality; default floors 0.45 and 0.35 |

The 0.15 boundary reuses the existing material-displacement definition; a neutral
return means below that boundary, not proof of exact baseline equality. Three
episodes distinguish a recurrent pattern from one event or a single repeat;
two windows prevent one-window events from qualifying. These are explicit
evidence requirements, not calibrated probabilities. The 30-day horizon matches
the existing temporal horizon. There is no campaign-specific episode-duration
cutoff, delta-spread tuning, correlation-delta summation or inferred diagnosis.

Support is emitted only when the third episode has closed on observed neutral
evidence. It may remain supported on later acceptable windows within the horizon;
it describes completed history, not an assertion that the current window is
displaced. A current gated window suppresses support. Missing or gated windows
break consecutive support and cannot establish a return. Direction changes
without a neutral return do not split an episode. An episode containing both
material directions cannot count. Historical gates are rechecked on evaluation.

Windows require valid start/end times and positive duration. Identical retries
are idempotent; conflicting retries, backward times and overlaps return limited
evidence without updating retained history. Timestamp offsets are normalized to
UTC; naive timestamps are interpreted as UTC. Horizon truncation requires a new
retained neutral return before counting a potentially clipped initial episode.
Capacity overflow returns limited evidence until discarded observations have
expired from the horizon, so eviction cannot silently remove an opposite veto.

State uses the same canonical identity as continuous evidence: signal pair,
graph basis, baseline correlation/time range, reference dataset, units and mode
context. Identity changes reset recurrence; missing pairs lose their state.
State is detached JSON data, scoped by the caller to its facility/dataset. It is
never automatically loaded, saved, or used to take an operational action.

```python
persistence_state = recurrence_state = None
for comparison_rows in chronological_windows:
    result = evaluate_sii(
        **fixed_reference_arguments,
        comparison_rows=comparison_rows,
        relationship_persistence_state=persistence_state,
        relationship_recurrence_state=recurrence_state,
    )
    graph = result["relationship_graph"]
    persistence_state = graph["relationship_persistence_state"]
    recurrence_state = graph["relationship_recurrence_state"]
```

Every graph edge includes `recurrence_evidence`: model/version, status
(`supported`, `unconfirmed`, `limited`), support flag, direction, episode count,
opposite veto, evaluation timestamp, reason, policy, gates, identity and episodes.
Episodes include support windows and opening/closing return evidence, with source
dataset IDs, source-row anchors, timestamps, signed displacement, gate values and
sensor-health context. The first observed episode may have no opening return;
every counted episode requires a closing return.

`relationship_graph.recurring_edges` contains supported recurrence edges.
The governed result exposes them independently at
`analysis_result.sii_evidence.relationship_recurrences`, bounded to the existing
12-relationship transport limit. Its allowlisted episode evidence retains the
reducer's window bounds and mode features. Continuation state is not projected.
Empty evidence is a valid result and does not claim recurrence is impossible.
The frontend exposes this collection as its own run-scoped Evidence channel.
It does not turn it into a finding, cause, diagnosis, prescription or continuous
persistence assertion. No database migration or automatic persistence is added.

Validation includes independent deterministic sequences and an extracted fixed
CHW campaign fixture (`tests/fixtures/chw_recurrence_evidence.json`). The fixture
records its source CSV SHA-256 and per-window checkpoint hashes, identities,
source anchors and existing continuous decisions. All 290 scenario windows are
checked against those saved continuous decisions. Only scenario B supports
recurrence; the fixture is validation input and does not configure thresholds.
