from __future__ import annotations

import json
import math
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from statistics import median
from typing import Any

from app.engine.sii.behavioral_graph import relationship_memory_id, update_behavioral_graph
from app.engine.sii.common import (
    EPSILON,
    clamp,
    finite_number,
    median_absolute_deviation,
    numeric_values,
    quantile,
    relationship_columns,
)
from app.services.data_quality import parse_timestamp
from app.services.telemetry_classification import telemetry_catalog_by_column


MODEL_CONTRACT_VERSION = "behavioral-digital-model-v1"
DEFAULT_CONFIG = {
    "maximum_history_entries": 100,
    "relationship_inactive_after_runs": 2,
    "relationship_retire_after_runs": 3,
    "minimum_signal_observations": 5,
}
IDENTITY_FIELDS = (
    "organization_id",
    "facility_id",
    "system_id",
    "subsystem_id",
    "equipment_group_id",
)


def resolve_infrastructure_identity(
    *,
    columns: list[str],
    telemetry_signal_catalog: dict[str, Any] | list[dict[str, Any]] | None,
    config: dict[str, Any] | None,
) -> dict[str, Any]:
    """Resolve a deterministic system scope without inventing missing identity."""

    cfg = config if isinstance(config, dict) else {}
    nested = cfg.get("infrastructure_identity") if isinstance(cfg.get("infrastructure_identity"), dict) else {}
    conflicts: list[str] = []
    values: dict[str, str | None] = {}
    for field in IDENTITY_FIELDS:
        nested_value = _clean(nested.get(field))
        direct_value = _clean(cfg.get(field))
        if nested_value and direct_value and nested_value != direct_value:
            conflicts.append(f"conflicting_{field}")
        values[field] = nested_value or direct_value
    configured_model_id = _clean(nested.get("configured_model_id")) or _clean(cfg.get("configured_model_id"))
    computed_schema = telemetry_schema_fingerprint(columns, telemetry_signal_catalog)
    declared_schema = _clean(nested.get("schema_fingerprint")) or _clean(cfg.get("schema_fingerprint"))
    if declared_schema and declared_schema != computed_schema:
        conflicts.append("configured_schema_fingerprint_conflicts_with_observed_schema")

    stable_scope = configured_model_id or values["system_id"] or (
        f"{values['facility_id']}::{values['subsystem_id'] or values['equipment_group_id']}"
        if values["facility_id"] and (values["subsystem_id"] or values["equipment_group_id"])
        else None
    )
    limitations = []
    if conflicts:
        status = "conflicting"
        limitations.extend(conflicts)
    elif not stable_scope:
        status = "limited"
        limitations.append(
            "A configured model id, system id, or facility-plus-subsystem/equipment-group scope is required before behavioral memory can be attached."
        )
    else:
        status = "adequate"
    seed_fields = {
        "configured_model_id": configured_model_id,
        **values,
    }
    identity_seed = json.dumps(seed_fields, sort_keys=True, separators=(",", ":"))
    model_id = (
        f"behavioral-model:{sha256(identity_seed.encode('utf-8')).hexdigest()[:24]}"
        if status == "adequate"
        else None
    )
    factors = {
        "configured_model_id": 1.0 if configured_model_id else 0.0,
        "organization_scope": 1.0 if values["organization_id"] else 0.0,
        "facility_scope": 1.0 if values["facility_id"] else 0.0,
        "system_scope": 1.0 if values["system_id"] else 0.0,
        "subsystem_or_group_scope": 1.0 if values["subsystem_id"] or values["equipment_group_id"] else 0.0,
        "schema_observed": 1.0 if computed_schema else 0.0,
        "conflict_free": 0.0 if conflicts else 1.0,
    }
    compatibility = sum(factors.values()) / len(factors)
    if status != "adequate":
        compatibility = min(compatibility, 0.35)
    return {
        "model_id": model_id,
        **values,
        "schema_fingerprint": computed_schema,
        "configured_model_id": configured_model_id,
        "identity_confidence": {
            "compatibility": round(compatibility, 6),
            "not_probability": True,
            "factors": factors,
            "method": "unweighted_identity_evidence_factor_mean",
        },
        "identity_status": status,
        "identity_limitations": limitations,
        "conflicts": conflicts,
        "memory_update_allowed": status == "adequate",
    }


def telemetry_schema_fingerprint(
    columns: list[str],
    telemetry_signal_catalog: dict[str, Any] | list[dict[str, Any]] | None,
) -> str:
    catalog = telemetry_catalog_by_column(telemetry_signal_catalog)
    schema = []
    for index, column in enumerate(columns):
        metadata = catalog.get(str(column), {})
        schema.append(
            {
                "position": index,
                "source_column": str(column),
                "semantic_category": metadata.get("telemetry_category")
                or (metadata.get("telemetry_classification") or {}).get("category"),
                "units": metadata.get("engineering_units"),
            }
        )
    encoded = json.dumps(schema, sort_keys=True, separators=(",", ":"), default=str)
    return f"schema:{sha256(encoded.encode('utf-8')).hexdigest()}"


def validate_model_compatibility(
    active_model: dict[str, Any] | None,
    identity: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(active_model, dict):
        return {
            "status": "new_model",
            "compatible": True,
            "limitations": ["No active model existed; this run can initialize memory only if all learning safeguards pass."],
        }
    limitations = []
    if str(active_model.get("model_id")) != str(identity.get("model_id")):
        limitations.append("model_identity_mismatch")
    active_identity = active_model.get("infrastructure_identity") if isinstance(active_model.get("infrastructure_identity"), dict) else {}
    for field in IDENTITY_FIELDS:
        before = _clean(active_identity.get(field))
        after = _clean(identity.get(field))
        if before and after and before != after:
            limitations.append(f"identity_field_mismatch:{field}")
    schema_matches = str(active_identity.get("schema_fingerprint")) == str(identity.get("schema_fingerprint"))
    if not schema_matches:
        limitations.append("telemetry_schema_fingerprint_changed")
    hard_conflicts = [item for item in limitations if item.startswith("model_identity") or item.startswith("identity_field")]
    return {
        "status": "compatible" if not limitations else "limited" if not hard_conflicts else "conflicting",
        "compatible": not hard_conflicts,
        "schema_compatible": schema_matches,
        "limitations": limitations,
    }


def create_empty_behavioral_model(
    *,
    identity: dict[str, Any],
    source_run_id: str,
    observed_at: str,
) -> dict[str, Any]:
    return {
        "contract_version": MODEL_CONTRACT_VERSION,
        "model_id": identity.get("model_id"),
        "model_version": "v1",
        "model_status": "initializing",
        "infrastructure_identity": deepcopy(identity),
        "behavioral_identity": {},
        "signal_memory": {},
        "relationship_memory": {},
        "operating_mode_memory": {},
        "behavioral_graph": {"method": "persistent_behavioral_graph_v1", "nodes": {}, "edges": {}, "evolution_history": []},
        "expected_behavior_models": {},
        "baseline_history": [],
        "baseline_versions": [],
        "model_confidence_history": [],
        "event_memory": [],
        "snapshot_history": [],
        "learning_decisions": [],
        "learning_exclusions": [],
        "limitations": [],
        "processing_trace": {
            "created_from_source_run_id": source_run_id,
            "created_at_observation_time": observed_at,
        },
        "source_run_id": source_run_id,
    }


def build_candidate_model(
    *,
    active_model: dict[str, Any] | None,
    identity: dict[str, Any],
    rows: list[dict[str, Any]],
    numeric_columns: list[str],
    timestamp_column: str | None,
    telemetry_signal_catalog: dict[str, Any] | list[dict[str, Any]] | None,
    signal_drift: dict[str, Any],
    relationship_graph: dict[str, Any],
    operating_mode: dict[str, Any],
    sensor_health: dict[str, Any],
    data_quality: dict[str, Any],
    temporal_analysis: dict[str, Any],
    multiscale_analysis: dict[str, Any],
    physics_reasoning: dict[str, Any],
    expected_behavior: dict[str, Any],
    trained_expected_models: dict[str, Any],
    baseline_record: dict[str, Any] | None,
    event_references: list[str],
    source_run_id: str,
    observed_at: str,
    allow_learning: bool,
    config: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build a new version from current evidence after learning has been decided."""

    cfg = {**DEFAULT_CONFIG, **(config or {})}
    base = deepcopy(active_model) if isinstance(active_model, dict) else create_empty_behavioral_model(
        identity=identity, source_run_id=source_run_id, observed_at=observed_at
    )
    version_before = str(base.get("model_version") or "v0") if active_model else None
    version_after = _next_version(version_before) if active_model and allow_learning else str(base.get("model_version") or "v1")
    exclusions: list[dict[str, Any]] = []
    update_counts = {
        "signals_added": 0,
        "signals_updated": 0,
        "relationships_added": 0,
        "relationships_updated": 0,
        "relationships_retired": 0,
    }
    mode_id = active_operating_mode(operating_mode)
    signal_memory = deepcopy(base.get("signal_memory") or {})
    relationship_memory = deepcopy(base.get("relationship_memory") or {})
    if allow_learning:
        signal_memory, signal_exclusions, signal_counts = _update_signal_memory(
            prior=signal_memory,
            rows=rows,
            numeric_columns=numeric_columns,
            timestamp_column=timestamp_column,
            catalog=telemetry_catalog_by_column(telemetry_signal_catalog),
            drift=signal_drift,
            operating_mode=mode_id,
            sensor_health=sensor_health,
            data_quality=data_quality,
            temporal_analysis=temporal_analysis,
            multiscale_analysis=multiscale_analysis,
            expected_behavior=expected_behavior,
            source_run_id=source_run_id,
            observed_at=observed_at,
            config=cfg,
        )
        exclusions.extend(signal_exclusions)
        update_counts.update(signal_counts)
        relationship_memory, relationship_exclusions, relationship_counts = _update_relationship_memory(
            prior=relationship_memory,
            graph=relationship_graph,
            operating_mode=mode_id,
            sensor_health=sensor_health,
            temporal_analysis=temporal_analysis,
            physics_reasoning=physics_reasoning,
            source_run_id=source_run_id,
            observed_at=observed_at,
            config=cfg,
        )
        exclusions.extend(relationship_exclusions)
        update_counts.update(relationship_counts)
    else:
        exclusions.append(
            {
                "type": "model_update",
                "reason": "learning_not_allowed_for_this_run",
                "source_run_id": source_run_id,
            }
        )

    mode_memory = _update_mode_memory(
        deepcopy(base.get("operating_mode_memory") or {}),
        operating_mode,
        observed_at,
        source_run_id,
        allow_learning,
    )
    expected_models = deepcopy(base.get("expected_behavior_models") or {})
    if allow_learning:
        expected_models.update(deepcopy(trained_expected_models))
    graph = update_behavioral_graph(
        active_graph=base.get("behavioral_graph"),
        current_graph=relationship_graph,
        signal_memory=signal_memory,
        relationship_memory=relationship_memory,
        event_references=event_references,
        source_run_id=source_run_id,
        model_version=version_after,
        allow_learning=allow_learning,
    )
    baseline_history = list(base.get("baseline_history") or [])
    baseline_versions = list(base.get("baseline_versions") or [])
    if baseline_record:
        baseline_history.append(deepcopy(baseline_record))
        candidate_version = baseline_record.get("candidate_version")
        if candidate_version and candidate_version not in baseline_versions:
            baseline_versions.append(candidate_version)
    behavioral_identity = _build_behavioral_identity(
        signal_memory=signal_memory,
        relationship_memory=relationship_memory,
        operating_mode_memory=mode_memory,
        graph=graph,
    )
    confidence = behavioral_confidence(
        signal_memory=signal_memory,
        relationship_memory=relationship_memory,
        graph=graph,
        data_quality=data_quality,
        sensor_health=sensor_health,
        expected_behavior=expected_behavior,
        multiscale_analysis=multiscale_analysis,
        snapshot_count=len(base.get("snapshot_history") or []),
    )
    confidence_history = list(base.get("model_confidence_history") or [])
    confidence_history.append(
        {"observed_at": observed_at, "source_run_id": source_run_id, "model_version": version_after, **confidence}
    )
    max_history = int(cfg["maximum_history_entries"])
    updated = {
        **base,
        "contract_version": MODEL_CONTRACT_VERSION,
        "model_id": identity.get("model_id"),
        "model_version": version_after,
        "model_status": "active" if allow_learning else str(base.get("model_status") or "limited"),
        "infrastructure_identity": deepcopy(identity),
        "behavioral_identity": behavioral_identity,
        "signal_memory": dict(sorted(signal_memory.items())),
        "relationship_memory": dict(sorted(relationship_memory.items())),
        "operating_mode_memory": mode_memory,
        "behavioral_graph": graph,
        "expected_behavior_models": dict(sorted(expected_models.items())),
        "baseline_history": baseline_history[-max_history:],
        "baseline_versions": baseline_versions,
        "model_confidence_history": confidence_history[-max_history:],
        "event_memory": list(dict.fromkeys([*base.get("event_memory", []), *event_references])),
        "learning_exclusions": [*base.get("learning_exclusions", []), *exclusions][-max_history:],
        "limitations": list(
            dict.fromkeys(
                [
                    *base.get("limitations", []),
                    "Behavioral memory represents empirical system behavior and does not simulate the physical system.",
                    "Behavioral associations and residuals do not establish cause, failure, or future outcome.",
                ]
            )
        ),
        "processing_trace": {
            **deepcopy(base.get("processing_trace") or {}),
            "last_source_run_id": source_run_id,
            "last_observed_at": observed_at,
            "last_update_allowed": allow_learning,
            "last_update_counts": update_counts,
        },
        "source_run_id": source_run_id,
    }
    return updated, {
        "model_version_before": version_before,
        "model_version_after": version_after,
        **update_counts,
        "learning_exclusions": exclusions,
    }


def build_behavioral_snapshot(
    *,
    model: dict[str, Any],
    source_run_id: str,
    created_at: str,
    previous_snapshot_id: str | None,
    changes: dict[str, Any],
) -> dict[str, Any]:
    identity = {
        "model_id": model.get("model_id"),
        "model_version": model.get("model_version"),
        "source_run_id": source_run_id,
        "previous_snapshot_id": previous_snapshot_id,
    }
    digest = sha256(json.dumps(identity, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()[:24]
    snapshot_id = f"behavioral-snapshot:{digest}"
    confidence_history = model.get("model_confidence_history") or []
    return {
        "snapshot_id": snapshot_id,
        "model_id": model.get("model_id"),
        "model_version": model.get("model_version"),
        "created_at": created_at,
        "source_run_id": source_run_id,
        "behavioral_identity": deepcopy(model.get("behavioral_identity", {})),
        "signal_memory": deepcopy(model.get("signal_memory", {})),
        "relationship_memory": deepcopy(model.get("relationship_memory", {})),
        "behavioral_graph": deepcopy(model.get("behavioral_graph", {})),
        "operating_mode_memory": deepcopy(model.get("operating_mode_memory", {})),
        "expected_behavior_models": deepcopy(model.get("expected_behavior_models", {})),
        "baseline_versions": deepcopy(model.get("baseline_versions", [])),
        "event_references": deepcopy(model.get("event_memory", [])),
        "confidence_summary": deepcopy(confidence_history[-1] if confidence_history else {}),
        "limitations": deepcopy(model.get("limitations", [])),
        "processing_trace": {
            "immutable": True,
            "source_run_id": source_run_id,
            "changes": deepcopy(changes),
        },
        "previous_snapshot_id": previous_snapshot_id,
        "rollback_reference": previous_snapshot_id,
    }


def behavioral_model_section(
    *,
    model: dict[str, Any] | None,
    identity: dict[str, Any],
    snapshot_id: str | None,
    baseline_state: dict[str, Any],
    learning_decision: dict[str, Any],
    processing_trace: dict[str, Any],
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(model, dict):
        return {
            "status": "limited",
            "active": False,
            "model_id": identity.get("model_id"),
            "model_version": None,
            "snapshot_id": snapshot_id,
            "identity": deepcopy(identity),
            "behavioral_identity": {},
            "signal_memory_summary": {"signals_tracked": 0, "signals": []},
            "relationship_memory_summary": {"relationships_tracked": 0, "relationships": []},
            "behavioral_graph": {},
            "operating_mode_memory": {},
            "baseline_state": deepcopy(baseline_state),
            "confidence": {"not_probability": True, "factors": {}},
            "limitations": list(limitations or identity.get("identity_limitations") or []),
            "learning_decision": deepcopy(learning_decision),
            "processing_trace": deepcopy(processing_trace),
        }
    signal_memory = model.get("signal_memory") if isinstance(model.get("signal_memory"), dict) else {}
    relationship_memory = model.get("relationship_memory") if isinstance(model.get("relationship_memory"), dict) else {}
    confidence_history = model.get("model_confidence_history") or []
    combined_limitations = list(
        dict.fromkeys([*model.get("limitations", []), *(limitations or [])])
    )
    return {
        "status": "complete" if model.get("model_status") == "active" else "limited",
        "active": model.get("model_status") == "active",
        "model_id": model.get("model_id"),
        "model_version": model.get("model_version"),
        "snapshot_id": snapshot_id,
        "identity": deepcopy(identity),
        "behavioral_identity": deepcopy(model.get("behavioral_identity", {})),
        "signal_memory_summary": {
            "signals_tracked": len(signal_memory),
            "signals": [
                {
                    "signal_id": signal_id,
                    "status": item.get("status"),
                    "observation_count": item.get("observation_count"),
                    "historical_center": item.get("historical_center"),
                    "historical_scale": item.get("historical_scale"),
                    "confidence": deepcopy(item.get("confidence", {})),
                    "limitations": deepcopy(item.get("limitations", [])),
                }
                for signal_id, item in sorted(signal_memory.items())
            ],
        },
        "relationship_memory_summary": {
            "relationships_tracked": len(relationship_memory),
            "active": sum(1 for item in relationship_memory.values() if item.get("status") not in {"inactive", "retired"}),
            "inactive": sum(1 for item in relationship_memory.values() if item.get("status") == "inactive"),
            "retired": sum(1 for item in relationship_memory.values() if item.get("status") == "retired"),
            "relationships": [
                {
                    "relationship_id": relationship_id,
                    "source_signal": item.get("source_signal"),
                    "target_signal": item.get("target_signal"),
                    "operating_modes_observed": deepcopy(item.get("operating_modes_observed", [])),
                    "current_strength": item.get("current_strength"),
                    "stability": item.get("stability"),
                    "volatility": item.get("volatility"),
                    "status": item.get("status"),
                    "confidence": deepcopy(item.get("confidence", {})),
                }
                for relationship_id, item in sorted(relationship_memory.items())
            ],
        },
        "behavioral_graph": deepcopy(model.get("behavioral_graph", {})),
        "operating_mode_memory": deepcopy(model.get("operating_mode_memory", {})),
        "baseline_state": deepcopy(baseline_state),
        "confidence": deepcopy(confidence_history[-1] if confidence_history else {"not_probability": True, "factors": {}}),
        "limitations": combined_limitations,
        "learning_decision": deepcopy(learning_decision),
        "processing_trace": deepcopy(processing_trace),
    }


def behavioral_confidence(
    *,
    signal_memory: dict[str, Any],
    relationship_memory: dict[str, Any],
    graph: dict[str, Any],
    data_quality: dict[str, Any],
    sensor_health: dict[str, Any],
    expected_behavior: dict[str, Any],
    multiscale_analysis: dict[str, Any],
    snapshot_count: int,
) -> dict[str, Any]:
    signal_counts = [int(item.get("observation_count") or 0) for item in signal_memory.values()]
    relationship_stability = [
        1.0 - clamp(float(item.get("volatility") or 0.0))
        for item in relationship_memory.values()
        if item.get("status") not in {"inactive", "retired"}
    ]
    health_items = [
        str(item.get("health") or "").lower()
        for item in sensor_health.get("signals", [])
        if isinstance(item, dict)
    ]
    quality_rating = str((data_quality.get("data_confidence") or {}).get("rating") or "").lower()
    expected_values = expected_behavior.get("expected_values", []) if isinstance(expected_behavior, dict) else []
    residual_stability = [
        clamp(1.0 - min(abs(float(item.get("normalized_residual") or 0.0)) / 6.0, 1.0))
        for item in expected_values
        if isinstance(item, dict)
    ]
    graph_history = graph.get("evolution_history", []) if isinstance(graph, dict) else []
    factors = {
        "historical_support": round(clamp((sum(signal_counts) / max(1, len(signal_counts))) / 120.0), 6) if signal_counts else 0.0,
        "sample_sufficiency": round(clamp(len(signal_memory) / 3.0), 6),
        "relationship_stability": round(sum(relationship_stability) / len(relationship_stability), 6) if relationship_stability else 0.0,
        "cross_scale_agreement": _multiscale_factor(multiscale_analysis),
        "operating_mode_consistency": 1.0,
        "data_quality": {"high": 1.0, "moderate": 0.8, "limited": 0.5, "low": 0.0}.get(quality_rating, 0.5),
        "sensor_health": round(sum(1.0 if item in {"healthy", "good"} else 0.0 for item in health_items) / len(health_items), 6) if health_items else 0.0,
        "expected_model_validation": round(clamp(len(expected_values) / max(1, len(signal_memory))), 6),
        "residual_stability": round(sum(residual_stability) / len(residual_stability), 6) if residual_stability else 0.0,
        "physics_prior_support": 0.0,
        "snapshot_consistency": round(clamp(snapshot_count / 3.0), 6),
        "graph_stability": round(clamp(len(graph_history) / 3.0), 6),
    }
    compatibility = sum(float(value) for value in factors.values()) / len(factors)
    return {
        "compatibility": round(compatibility, 6),
        "not_probability": True,
        "factors": factors,
        "method": "unweighted_deterministic_evidence_factor_mean",
        "interpretation": "Compatibility summarizes inspectable evidence sufficiency and consistency; it is not a probability.",
    }


def active_operating_mode(operating_mode: dict[str, Any]) -> str:
    mode = operating_mode.get("recent_mode") if isinstance(operating_mode, dict) else None
    return str(mode) if mode and mode != "unavailable" else "unavailable"


def observation_bounds(
    rows: list[dict[str, Any]], timestamp_column: str | None, source_run_id: str
) -> tuple[str, str, list[str]]:
    limitations = []
    parsed = []
    if timestamp_column:
        for row in rows:
            value = row.get(timestamp_column)
            timestamp = parse_timestamp(str(value)) if value is not None else None
            if timestamp is not None:
                parsed.append(timestamp)
    if parsed:
        return parsed[0].isoformat(), parsed[-1].isoformat(), limitations
    limitations.append("Source timestamps were unavailable; deterministic run identity time was used for behavioral version attribution.")
    digest = int(sha256(source_run_id.encode("utf-8")).hexdigest()[:8], 16)
    synthetic = datetime.fromtimestamp(digest % 2147483647).astimezone().isoformat()
    return synthetic, synthetic, limitations


def _update_signal_memory(
    *,
    prior: dict[str, Any],
    rows: list[dict[str, Any]],
    numeric_columns: list[str],
    timestamp_column: str | None,
    catalog: dict[str, dict[str, Any]],
    drift: dict[str, Any],
    operating_mode: str,
    sensor_health: dict[str, Any],
    data_quality: dict[str, Any],
    temporal_analysis: dict[str, Any],
    multiscale_analysis: dict[str, Any],
    expected_behavior: dict[str, Any],
    source_run_id: str,
    observed_at: str,
    config: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, int]]:
    output = deepcopy(prior)
    exclusions = []
    health = _health_profiles(sensor_health)
    drift_by_signal = {
        str(item.get("column")): item
        for item in drift.get("column_drift", [])
        if isinstance(item, dict) and item.get("column")
    }
    first_observed, last_observed, _ = observation_bounds(rows, timestamp_column, source_run_id)
    added = 0
    updated = 0
    for column in numeric_columns:
        values = numeric_values(rows, column)
        if len(values) < int(config["minimum_signal_observations"]):
            exclusions.append({"type": "signal", "signal_id": column, "reason": "insufficient_signal_observations"})
            continue
        health_status = str(health.get(column, {}).get("health") or "unavailable").lower()
        if health_status not in {"healthy", "good"}:
            exclusions.append({"type": "signal", "signal_id": column, "reason": f"sensor_health_not_acceptable:{health_status}"})
            continue
        existing = deepcopy(output.get(column) or {})
        current_center = float(median(values))
        current_mad = median_absolute_deviation(values)
        current_scale = max(1.4826 * current_mad, EPSILON)
        previous_count = int(existing.get("observation_count") or 0)
        combined_count = previous_count + len(values)
        historical_center = (
            (float(existing.get("historical_center") or current_center) * previous_count + current_center * len(values))
            / max(1, combined_count)
        )
        historical_scale = (
            (float(existing.get("historical_scale") or current_scale) * previous_count + current_scale * len(values))
            / max(1, combined_count)
        )
        differences = [right - left for left, right in zip(values, values[1:])]
        accelerations = [right - left for left, right in zip(differences, differences[1:])]
        metadata = catalog.get(column, {})
        signal_drift = deepcopy(drift_by_signal.get(column, {}))
        trend = {
            "observed_at": observed_at,
            "source_run_id": source_run_id,
            "center": round(current_center, 6),
            "robust_scale": round(current_scale, 6),
            "direction": signal_drift.get("direction"),
        }
        sensor_history = _append_history(existing.get("sensor_health_history"), {"observed_at": observed_at, "source_run_id": source_run_id, **deepcopy(health.get(column, {}))}, config)
        quality_history = _append_history(existing.get("data_quality_history"), {"observed_at": observed_at, "source_run_id": source_run_id, "readiness": data_quality.get("readiness"), "data_confidence": deepcopy(data_quality.get("data_confidence", {}))}, config)
        residual_history = list(existing.get("historical_residual_behavior") or [])
        for item in expected_behavior.get("expected_values", []) if isinstance(expected_behavior, dict) else []:
            if isinstance(item, dict) and item.get("target_signal") == column:
                residual_history.append(
                    {
                        "observed_at": observed_at,
                        "source_run_id": source_run_id,
                        "residual": item.get("residual"),
                        "normalized_residual": item.get("normalized_residual"),
                        "source_model_version": item.get("source_model_version"),
                    }
                )
        modes = list(existing.get("operating_modes_observed") or [])
        if operating_mode not in modes:
            modes.append(operating_mode)
        confidence_factors = {
            "sample_sufficiency": round(clamp(combined_count / 120.0), 6),
            "data_quality": 1.0 if str((data_quality.get("data_confidence") or {}).get("rating") or "").lower() in {"high", "moderate"} else 0.5,
            "sensor_health": 1.0,
            "mode_support": round(clamp(len(modes) / 2.0), 6),
        }
        confidence = {
            "compatibility": round(sum(confidence_factors.values()) / len(confidence_factors), 6),
            "not_probability": True,
            "factors": confidence_factors,
        }
        output[column] = {
            **existing,
            "signal_id": column,
            "source_column": column,
            "semantic_category": metadata.get("telemetry_category") or (metadata.get("telemetry_classification") or {}).get("category"),
            "units": metadata.get("engineering_units"),
            "first_observed": existing.get("first_observed") or first_observed,
            "last_observed": last_observed,
            "observation_count": combined_count,
            "historical_support_duration": _duration(existing.get("first_observed") or first_observed, last_observed),
            "operating_modes_observed": modes,
            "historical_center": round(historical_center, 6),
            "historical_scale": round(historical_scale, 6),
            "historical_quantiles": {
                "method": "empirical_linear_interpolation",
                "values": {str(item): round(quantile(values, item), 6) for item in (0.05, 0.25, 0.5, 0.75, 0.95)},
            },
            "historical_variability": {
                "method": "median_absolute_deviation",
                "mad": round(current_mad, 6),
                "robust_scale": round(current_scale, 6),
            },
            "trend_history": _append_history(existing.get("trend_history"), trend, config),
            "drift_history": _append_history(existing.get("drift_history"), {"observed_at": observed_at, "source_run_id": source_run_id, **signal_drift}, config),
            "velocity_history": _append_history(existing.get("velocity_history"), {"observed_at": observed_at, "source_run_id": source_run_id, "median_velocity_per_sample": round(float(median(differences)), 6) if differences else None}, config),
            "acceleration_history": _append_history(existing.get("acceleration_history"), {"observed_at": observed_at, "source_run_id": source_run_id, "median_acceleration_per_sample": round(float(median(accelerations)), 6) if accelerations else None}, config),
            "temporal_characteristics": {
                "method": "per_sample_robust_difference_summary",
                "temporal_engine_rate_of_change": deepcopy(temporal_analysis.get("rate_of_change", {})),
            },
            "multiscale_characteristics": {
                "source_status": multiscale_analysis.get("status"),
                "cross_scale_classification": multiscale_analysis.get("cross_scale_classification"),
                "scales_used": deepcopy(multiscale_analysis.get("scales_used", [])),
            },
            "expected_response_contexts": _expected_contexts(column, expected_behavior),
            "sensor_health_history": sensor_history,
            "data_quality_history": quality_history,
            "historical_residual_behavior": residual_history[-int(config["maximum_history_entries"]):],
            "confidence": confidence,
            "limitations": ["Historical center and scale evolve through transparent observation-count-weighted robust summaries."],
            "status": "active",
            "method_metadata": {
                "center": "median_per_run_then_observation_count_weighted_history",
                "scale": "1.4826_times_median_absolute_deviation",
                "distribution_assumption": "non_parametric",
            },
        }
        if existing:
            updated += 1
        else:
            added += 1
    return output, exclusions, {"signals_added": added, "signals_updated": updated}


def _update_relationship_memory(
    *,
    prior: dict[str, Any],
    graph: dict[str, Any],
    operating_mode: str,
    sensor_health: dict[str, Any],
    temporal_analysis: dict[str, Any],
    physics_reasoning: dict[str, Any],
    source_run_id: str,
    observed_at: str,
    config: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, int]]:
    output = deepcopy(prior)
    exclusions = []
    health = _health_profiles(sensor_health)
    candidates = graph.get("eligible_edges") if isinstance(graph, dict) else None
    if not isinstance(candidates, list) or not candidates:
        candidates = graph.get("edges", []) if isinstance(graph, dict) else []
    observed_ids: set[str] = set()
    added = 0
    updated = 0
    retired = 0
    applicable_priors = list(physics_reasoning.get("applicable_priors") or []) if isinstance(physics_reasoning, dict) else []
    for edge in candidates:
        if not isinstance(edge, dict):
            continue
        columns = relationship_columns(edge)
        if len(columns) != 2:
            continue
        unhealthy = [column for column in columns if str(health.get(column, {}).get("health") or "unavailable").lower() not in {"healthy", "good"}]
        if unhealthy:
            exclusions.append({"type": "relationship", "signals": columns, "reason": f"sensor_health_not_acceptable:{','.join(unhealthy)}"})
            continue
        relationship_type = str(edge.get("relationship_type") or "linear_correlation")
        relationship_id = relationship_memory_id(columns[0], columns[1], relationship_type, operating_mode)
        observed_ids.add(relationship_id)
        existing = deepcopy(output.get(relationship_id) or {})
        current_strength = _edge_strength(edge)
        strength_history = list(existing.get("strength_history") or [])
        strength_history.append({"observed_at": observed_at, "source_run_id": source_run_id, "strength": current_strength})
        strengths = [float(item.get("strength") or 0.0) for item in strength_history]
        volatility = 1.4826 * median_absolute_deviation(strengths)
        prior_strength = float(existing.get("current_strength") or current_strength)
        delta = current_strength - prior_strength
        if not existing:
            status = "emerged"
        elif volatility >= 0.20:
            status = "volatile"
        elif delta >= 0.20:
            status = "strengthened"
        elif delta <= -0.20:
            status = "weakened"
        else:
            status = "active"
        sample_count = _edge_sample_count(edge)
        modes = list(existing.get("operating_modes_observed") or [])
        if operating_mode not in modes:
            modes.append(operating_mode)
        stability = "volatile" if volatility >= 0.20 else "stable" if volatility <= 0.08 and len(strengths) >= 2 else "developing"
        confidence_factors = {
            "sample_sufficiency": round(clamp((int(existing.get("sample_support") or 0) + sample_count) / 120.0), 6),
            "strength_stability": round(clamp(1.0 - volatility), 6),
            "sensor_health": 1.0,
            "mode_consistency": 1.0,
        }
        output[relationship_id] = {
            **existing,
            "relationship_id": relationship_id,
            "source_signal": columns[0],
            "target_signal": columns[1],
            "relationship_type": relationship_type,
            "directionality_status": "association_only_direction_not_established",
            "first_observed": existing.get("first_observed") or observed_at,
            "last_observed": observed_at,
            "historical_support_duration": _duration(existing.get("first_observed") or observed_at, observed_at),
            "sample_support": int(existing.get("sample_support") or 0) + sample_count,
            "operating_modes_observed": modes,
            "baseline_strength": existing.get("baseline_strength", _edge_baseline_strength(edge)),
            "current_strength": current_strength,
            "strength_history": strength_history[-int(config["maximum_history_entries"]):],
            "mutual_information_history": _append_history(existing.get("mutual_information_history"), {"observed_at": observed_at, "source_run_id": source_run_id, "global_temporal_evidence": deepcopy(temporal_analysis.get("mutual_information_drift", {}))}, config),
            "covariance_history": _append_history(existing.get("covariance_history"), {"observed_at": observed_at, "source_run_id": source_run_id, "edge_correlation": edge.get("current_correlation") or edge.get("recent_correlation")}, config),
            "lag_history": _append_history(existing.get("lag_history"), {"observed_at": observed_at, "source_run_id": source_run_id, "global_temporal_lag_evidence": deepcopy(temporal_analysis.get("lagged_relationships", {}))}, config),
            "stability": stability,
            "volatility": round(volatility, 6),
            "persistence": len(strength_history),
            "confidence": {
                "compatibility": round(sum(confidence_factors.values()) / len(confidence_factors), 6),
                "not_probability": True,
                "factors": confidence_factors,
            },
            "age": int(existing.get("age") or 0) + 1,
            "change_history": _append_history(existing.get("change_history"), {"observed_at": observed_at, "source_run_id": source_run_id, "status": status, "strength_delta": round(delta, 6)}, config),
            "physics_prior_references": list(dict.fromkeys([*existing.get("physics_prior_references", []), *applicable_priors])),
            "graph_neighborhood": sorted(set(columns)),
            "limitations": ["Relationship memory stores association evidence and does not establish causality."],
            "status": status,
            "missed_observations": 0,
            "method_metadata": {
                "strength": "absolute_current_correlation_or_reported_strength",
                "volatility": "1.4826_times_mad_of_strength_history",
                "mode_conditioned": True,
            },
        }
        if existing:
            updated += 1
        else:
            added += 1

    for relationship_id, existing in list(output.items()):
        if relationship_id in observed_ids or operating_mode not in list(existing.get("operating_modes_observed") or []):
            continue
        missed = int(existing.get("missed_observations") or 0) + 1
        changed = deepcopy(existing)
        changed["missed_observations"] = missed
        if missed >= int(config["relationship_retire_after_runs"]):
            changed["status"] = "retired"
            retired += 1
        elif missed >= int(config["relationship_inactive_after_runs"]):
            changed["status"] = "inactive"
        changed["change_history"] = _append_history(changed.get("change_history"), {"observed_at": observed_at, "source_run_id": source_run_id, "status": changed.get("status"), "reason": "relationship_not_observed_in_compatible_mode"}, config)
        output[relationship_id] = changed
    return output, exclusions, {"relationships_added": added, "relationships_updated": updated, "relationships_retired": retired}


def _update_mode_memory(
    prior: dict[str, Any],
    operating_mode: dict[str, Any],
    observed_at: str,
    source_run_id: str,
    allow_learning: bool,
) -> dict[str, Any]:
    if not allow_learning:
        return prior
    mode_id = active_operating_mode(operating_mode)
    existing = deepcopy(prior.get(mode_id) or {})
    transitions = list(existing.get("transition_history") or [])
    baseline_mode = operating_mode.get("baseline_mode")
    if baseline_mode and baseline_mode != mode_id:
        transitions.append({"from": baseline_mode, "to": mode_id, "observed_at": observed_at, "source_run_id": source_run_id})
    prior[mode_id] = {
        **existing,
        "mode_id": mode_id,
        "first_observed": existing.get("first_observed") or observed_at,
        "last_observed": observed_at,
        "observation_count": int(existing.get("observation_count") or 0) + 1,
        "features": deepcopy((operating_mode.get("features") or {}).get("recent", {})),
        "confidence": operating_mode.get("confidence"),
        "transition_history": transitions[-100:],
        "recurring_schedule": {"status": "insufficient_evidence", "method": "not_learned_without_repeated_timestamped_cycles"},
    }
    return dict(sorted(prior.items()))


def _build_behavioral_identity(
    *,
    signal_memory: dict[str, Any],
    relationship_memory: dict[str, Any],
    operating_mode_memory: dict[str, Any],
    graph: dict[str, Any],
) -> dict[str, Any]:
    active_relationships = [item for item in relationship_memory.values() if item.get("status") not in {"inactive", "retired"}]
    stable_relationships = [item for item in active_relationships if item.get("stability") == "stable"]
    modes = sorted(
        operating_mode_memory.values(),
        key=lambda item: (-int(item.get("observation_count") or 0), str(item.get("mode_id"))),
    )
    return {
        "typical_signal_distributions": {
            signal_id: {
                "center": item.get("historical_center"),
                "scale": item.get("historical_scale"),
                "quantiles": deepcopy(item.get("historical_quantiles")),
                "method_metadata": deepcopy(item.get("method_metadata")),
            }
            for signal_id, item in sorted(signal_memory.items())
        },
        "expected_variability": {
            signal_id: deepcopy(item.get("historical_variability"))
            for signal_id, item in sorted(signal_memory.items())
        },
        "stable_operating_ranges": {
            signal_id: deepcopy(item.get("historical_quantiles"))
            for signal_id, item in sorted(signal_memory.items())
        },
        "dominant_operating_modes": [item.get("mode_id") for item in modes],
        "recurring_operating_schedules": {
            str(item.get("mode_id")): deepcopy(item.get("recurring_schedule")) for item in modes
        },
        "stable_relationships": [item.get("relationship_id") for item in stable_relationships],
        "relationship_volatility": {
            str(item.get("relationship_id")): item.get("volatility") for item in active_relationships
        },
        "normal_transition_behavior": [
            transition for item in modes for transition in item.get("transition_history", [])
        ][-100:],
        "typical_response_delays": {
            str(item.get("relationship_id")): deepcopy(item.get("lag_history", []))[-5:]
            for item in active_relationships
        },
        "multiscale_behavior": {
            signal_id: deepcopy(item.get("multiscale_characteristics"))
            for signal_id, item in sorted(signal_memory.items())
        },
        "seasonal_or_recurring_behavior": {
            "status": "insufficient_evidence",
            "limitations": ["Seasonal behavior is not learned until repeated timestamped cycles are available."],
        },
        "historical_residual_behavior": {
            signal_id: deepcopy(item.get("historical_residual_behavior", []))
            for signal_id, item in sorted(signal_memory.items())
        },
        "historical_graph_structure": deepcopy(graph.get("evolution_history", [])),
        "inspectable": True,
        "opaque_vector_used": False,
    }


def _health_profiles(sensor_health: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("signal")): deepcopy(item)
        for item in sensor_health.get("signals", [])
        if isinstance(item, dict) and item.get("signal")
    }


def _edge_strength(edge: dict[str, Any]) -> float:
    for field in ("current_strength", "current_correlation", "recent_correlation", "strength"):
        value = finite_number(edge.get(field))
        if value is not None:
            return round(abs(value), 6)
    return 0.0


def _edge_baseline_strength(edge: dict[str, Any]) -> float:
    value = finite_number(edge.get("baseline_strength"))
    if value is not None:
        return round(abs(value), 6)
    value = finite_number(edge.get("baseline_correlation"))
    return round(abs(value), 6) if value is not None else 0.0


def _edge_sample_count(edge: dict[str, Any]) -> int:
    return max(
        int(edge.get("current_sample_count") or edge.get("recent_sample_size") or 0),
        int(edge.get("baseline_sample_count") or edge.get("baseline_sample_size") or 0),
    )


def _expected_contexts(column: str, expected_behavior: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "predictor_signals": deepcopy(item.get("predictor_signals", [])),
            "operating_mode": item.get("operating_mode"),
            "source_model_version": item.get("source_model_version"),
        }
        for item in expected_behavior.get("expected_values", []) if isinstance(expected_behavior, dict)
        if isinstance(item, dict) and item.get("target_signal") == column
    ]


def _append_history(history: Any, item: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    output = [deepcopy(value) for value in history if isinstance(value, dict)] if isinstance(history, list) else []
    output.append(deepcopy(item))
    return output[-int(config["maximum_history_entries"]):]


def _duration(start: Any, end: Any) -> str | None:
    try:
        start_time = parse_timestamp(str(start))
        end_time = parse_timestamp(str(end))
        if start_time is None or end_time is None:
            return None
        return f"PT{round(max(0.0, (end_time - start_time).total_seconds()), 6)}S"
    except (TypeError, ValueError):
        return None


def _multiscale_factor(multiscale: dict[str, Any]) -> float:
    classification = str(multiscale.get("cross_scale_classification") or "").lower()
    if classification in {"agreement", "consistent", "stable"}:
        return 1.0
    if classification in {"mixed", "conflicting"}:
        return 0.5
    return 0.0 if multiscale.get("status") == "limited" else 0.5


def _next_version(version: str | None) -> str:
    if not version:
        return "v1"
    digits = "".join(character for character in str(version) if character.isdigit())
    return f"v{int(digits or 0) + 1}"


def _clean(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
