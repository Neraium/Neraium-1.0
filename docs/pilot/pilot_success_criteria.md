# Pre-Registered Hydronic Pilot Success Criteria

Freeze this page, the input-file hashes, system scope, and backtest configuration before inspecting results.

## Primary measures

### 1. Earlier detection

- Measure: hours between the first compatible Neraium finding and the existing alarm, work order, inspection, or visible failure.
- Success: at least one facility-verified meaningful event has positive lead time, and no reported lead time uses telemetry later than the event.
- Report: every matched and unmatched event, median lead time, and the matching policy. Do not report only favorable examples.

### 2. Evidence usefulness

- Measure: share of reviewed findings marked `confirmed_issue`, `useful_warning`, or `maintenance_event` by the facility team, with a note describing the evidence or check used.
- Initial success threshold: at least 70% of reviewed surfaced findings are useful after a minimum of 10 reviews.
- Report: useful, explained, irrelevant, unresolved, and unreviewed findings separately.

### 3. Low irrelevant-finding burden

- Measure: findings marked `false_positive`, `nothing_meaningful`, or `ignore` divided by all reviewed findings.
- Initial success threshold: no more than 20%, and no more than two surfaced findings per site-week unless the facility team confirms an active incident period.
- Report: candidate findings, conservative suppressions, surfaced findings, and irrelevant outcomes so suppression is not hidden.

## Guardrails

- A mode-aware rule may only suppress an existing candidate; it may not create a finding or increase severity/confidence.
- A finding needs persistent or corroborated evidence. A single noisy threshold crossing is insufficient.
- Possible explanations are hypotheses, not confirmed causes.
- Feedback and case-state events are append-only. They do not alter the original result or evidence hash.
- Missed events, unavailable data, mapping changes, exclusions, and engine/configuration changes remain in the final report.

## Secondary diagnostics

Track data coverage, open finding count, time to acknowledgment, time to resolution, findings per site-week, event match rate, and unmatched-finding rate. These explain primary results but do not replace them.
