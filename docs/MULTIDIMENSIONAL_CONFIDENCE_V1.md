# Multidimensional Confidence v1

## Purpose and philosophy

Multidimensional Confidence v1 makes the Evidence Package explicit about which kind of evidence supports a claim. It does not increase confidence and it does not create an overall score. Evidence remains prior to conclusions, current evidence takes precedence, and `unknown` is a valid result whenever the persisted analysis does not support a dimension.

The five dimensions are independent. Data quality is not evidence of physical consistency; operating-context comparability is not evidence of cause; and a strong behavioral finding does not prove that semantic mapping was unique. The dimensions must not be averaged, weighted, or presented as an overall percentage.

## Implementation audit

Before this change, the canonical Evidence Package already contained a `confidence` object with the five dimension names introduced by Evidence Package v1. Every builder-produced dimension was hard-coded to `unknown`; `finding_confidence` only stated that generic legacy confidence was not reinterpreted, `operating_state_confidence` stated that Operating Context was descriptive, and the other dimensions used the generic not-calculated reason. The separate Operating Context `comparison_state.state_confidence` was also intentionally `unknown`.

The persisted analysis already provides defensible inputs for some dimensions: relationship results may contain an upstream confidence level and score; data quality contains documented reliability and signal-health assessments; Operating Context v1 contains deterministic transition and comparability evidence; and the telemetry catalog contains canonical semantic roles. No defensible operating-state match or physics-consistency calculation exists. Canonical roles support an availability and uniqueness check, but no numeric mapping score.

API routes already return the Evidence Package under analysis responses and through both package lookup routes. The response shape, package identity, exact-baseline eligibility gate, deterministic serialization, tenant scoping, and legacy finding projection are retained. The frontend does not read or display the package's five internal confidence dimensions, so no UI change or confidence gauge is added.

## Dimensions and supported calculations

The existing `confidence` object is retained and its five existing fields are populated as follows:

- `finding_confidence` preserves an existing relationship `confidence_level`/`confidence` and `confidence_score`/`relationship_confidence_score`. The package does not derive a new score from persistence, sample count, or relationship delta. Those facts remain separately referenced evidence.
- `data_quality_confidence` preserves the existing `data_quality.data_confidence` assessment. When available, its qualitative rating is normalized to the package's `high`, `medium`, and `low` vocabulary, and the already-calculated 0–100 `reliability_score` is preserved without rescaling.
- `operating_state_confidence` remains `unknown`. Operating Context v1 can deterministically describe transition direction and calculate range-overlap comparability, but it has no operating-state matching model. Its comparability score is not copied into state confidence.
- `mapping_confidence` uses only persisted canonical role availability and uniqueness. It is `medium` when both relationship signals have available, unambiguous canonical roles because uniqueness does not independently validate their physical correctness; it is `low` when another catalog signal competes for either role and `unknown` when role evidence is unavailable. It has no numeric score. V1 does not emit `high` without explicitly identified persisted validation evidence such as trusted connector semantics or engineer confirmation.
- `physical_consistency_confidence` remains `unknown` with the reason `Physics consistency engine not implemented.`

Each populated dimension records a method and evidence references where the corresponding package evidence exists. Numeric values are exposed only when an upstream calculation is already persisted.

## Unsupported and deferred work

No physics consistency layer, operating-state model, adaptive clustering, seasonal model, hypothesis or diagnosis engine, propagation or topology analysis, knowledge-conflict handling, engineer feedback, governance, lifecycle, or recurrence logic is introduced here. These remain deferred roadmap work. Their absence must be represented as `unknown`, not estimated from unrelated evidence.

## Compatibility

Routes, package identity, schema version, and legacy finding projection are unchanged. The Evidence Package schema already reserved the five confidence fields, so v1 populates those fields rather than duplicating them. Existing stored packages remain valid, and deterministic rebuilding produces stable serialization for the same persisted analysis.
