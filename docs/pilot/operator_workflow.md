# Hydronic Finding Workflow

## Canonical flow

`System Status -> Findings -> Evidence -> Outcome`

### 1. System status

Confirm the selected site/system, current data coverage, active operating mode, baseline identity, and whether analysis is complete or limited. Resolve signal mappings and unit problems before interpreting system behavior.

### 2. Findings

Review only persistent, corroborated findings. Each finding should state what changed, affected signals/system boundary, first observed time, confidence tier, and why it may matter. A candidate suppressed by mode-aware evidence is counted in metrics but is not shown as an active finding.

Set the case state independently of technical judgment:

- `open`
- `acknowledged`
- `investigating`
- `monitoring`
- `resolved`
- `dismissed`

### 3. Evidence

Verify the baseline/comparison windows, source signals and rows, relationship changes, persistence, mode comparability, data limitations, engine/configuration versions, and hashes. Review “possible explanations” only as hypotheses. Follow the evidence-linked verification checks in the facility.

### 4. Outcome

Record owner/assignee, work-order reference, action taken, and one operator judgment such as `confirmed_issue`, `known_operational_change`, `sensor_or_data_problem`, `useful_warning`, or `false_positive`. Resolution closes workflow state but does not overwrite the finding or historical evidence.

## Weekly review

- Examine all newly surfaced and suppressed candidates.
- Review unresolved findings and missing operator outcomes.
- Compare findings with alarms, inspections, and work orders.
- Investigate every irrelevant finding and every documented event Neraium missed.
- Export the evidence package and observability pilot metrics for the weekly record.
