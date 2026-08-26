# Neraium product language

Neraium is the platform. Systemic Infrastructure Intelligence (SII) is the intelligence Neraium uses to analyze infrastructure behavior. Do not use SII as the product name, and do not describe Neraium as maintenance forecasting.

The production, experimental, static-reference, and future capability boundaries are defined in [SII authority boundaries](SII_AUTHORITY_BOUNDARIES.md).

## Core terms

- **System**: Operational equipment or processes grouped by shared telemetry behavior. Systems are discovered from analyzed telemetry.
- **Dataset**: A bounded collection of timestamped telemetry imported for analysis. A dataset is not a connector.
- **Connector**: A configured read-only integration that can test access to a telemetry source and prepare records. Connector health does not describe facility health.
- **Analysis**: One execution of SII against a dataset. Analyses can be queued, analyzing, saving results, complete, failed, cancelled, or timed out.
- **Insight**: An operator-facing change identified by SII that may warrant investigation. Use insight, not issue or finding, in product copy.
- **Evidence**: Observed telemetry relationships, measurements, and time windows that support an insight. Evidence supports an interpretation but does not prove root cause.
- **Behavior baseline**: The learned reference for how system relationships normally move together.
- **Operational review window**: A non-predictive scheduling aid for when evidence should be reviewed if the observed trajectory persists. It is not a failure horizon, remaining useful life, or predicted time to failure.

## Status language

Insight severity describes investigation priority:

- **Critical**: Immediate operator review is required.
- **High**: Prompt operator review is recommended.
- **Moderate**: Review during the current operating cycle.
- **Low**: Monitor and review when practical.

Connector health describes access to a configured telemetry source:

- **Healthy**: The connector completed its latest check.
- **Degraded**: The connector is reachable but returned warnings or partial data.
- **Offline**: The latest connection attempt failed.
- **Not configured**: No usable connector settings are available.

Facility state uses **Stable**, **Investigation recommended**, **Urgent investigation**, **Baseline needed**, and **Analyzing**. These states do not predict equipment failure.

## Copy rules

Use direct operator actions, explain the next step in empty and error states, keep technical identifiers inside Analysis Details, and never expose stack traces, credentials, database errors, filesystem paths, or internal service tokens in user-facing messages. Use hyphens, colons, or full stops instead of em dashes.

Customer copy may describe observed relationships and structural paths, but must not turn them into causal chains or root-cause claims. Do not present repository research packages as production federation, cross-site learning, persistent cognition memory, validated digital twins, counterfactual truth, or failure prediction.
