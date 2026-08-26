# Intelligence Contract (Frozen v1)

This document freezes the minimum intelligence payload contract for Neraium uploads and facility views.

See [SII authority boundaries](SII_AUTHORITY_BOUNDARIES.md) for the distinction between this production contract and repository research/reference packages.

Scope:
- `GET /api/facility/systems` -> `intelligence`
- `GET /api/data/latest-upload` -> `latest_result.sii_intelligence`
- `POST /api/data/upload` processing output -> `sii_intelligence`

## Required top-level fields

These fields are required for v1 consumers:

- `facility_state`
- `room_state`
- `urgency`
- `intervention_window`
- `neraium_score`
- `primary_room`
- `primary_driver`
- `driver_category`
- `attribution_confidence`
- `supporting_evidence` (list)
- `relationship_evidence` (list)
- `structural_explanation` (list)
- `confidence_basis`
- `confidence_components` (object)
- `recommended_operator_review`
- `next_operator_move`
- `what_to_check` (list)
- `why_flagged`
- `baseline_comparison`
- `observed_persistence`
- `last_updated`
- `rooms` (list)

## Required per-room fields (`rooms[]`)

Each room/system record must include:

- `room`
- `room_state`
- `urgency`
- `intervention_window`
- `primary_driver`
- `driver_category`
- `attribution_confidence`
- `supporting_evidence` (list)
- `relationship_evidence` (list)
- `structural_explanation` (list)
- `confidence_basis`
- `confidence_components` (object)
- `recommended_operator_review`
- `next_operator_move`
- `what_to_check` (list)
- `why_flagged`
- `review_window`
- `review_window_hours`
- `confidence`

## Confidence Components

`confidence_components` must include:

- `data_sufficiency`
- `signal_strength`
- `relationship_support`
- `persistence`

Current values are qualitative (`low`, `medium`, `high`) and are intended for operator-facing explainability, not prediction.

## Non-goals / guardrails

- No deterministic failure prediction claims.
- Review windows are operational scheduling aids, not predicted failure timing or remaining useful life.
- No autonomous control actions.
- Sparse telemetry should be surfaced explicitly (for example, `room_state = "Insufficient telemetry"`), not hidden.

## Compatibility policy

- New fields may be added.
- Existing required fields above must not be removed or renamed in v1.
- Semantic changes to existing required fields require a versioned contract update.
- Prediction-named aliases may remain inside internal canonical compatibility objects for older server-side consumers, but they are not part of the customer-facing intelligence contract. New consumers must use `review_window*`.
- `evidence_lineage` remains a preserved compatibility field. It does not replace formal traceability, source-window, method/version, or bounded SII evidence contracts.
