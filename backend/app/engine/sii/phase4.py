from __future__ import annotations

import json
from copy import deepcopy
from hashlib import sha256
from typing import Any

from app.engine.sii.baseline_evolution import evaluate_baseline_evolution
from app.engine.sii.bayesian_evidence import evaluate_bayesian_evidence
from app.engine.sii.behavioral_evolution import evaluate_behavioral_evolution
from app.engine.sii.behavioral_graph import compare_behavioral_graph
from app.engine.sii.behavioral_model import (
    active_operating_mode,
    behavioral_model_section,
    build_behavioral_snapshot,
    build_candidate_model,
    observation_bounds,
    resolve_infrastructure_identity,
    validate_model_compatibility,
)
from app.engine.sii.behavioral_model_contract import (
    BehavioralModelStorageError,
    BehavioralModelStorageUnavailable,
    BehavioralModelStore,
)
from app.engine.sii.behavioral_model_store import RuntimeBehavioralModelStore
from app.engine.sii.dynamical_stability import analyze_dynamical_stability
from app.engine.sii.event_memory import event_memory_section, prepare_event_memory
from app.engine.sii.expected_behavior import (
    evaluate_expected_behavior,
    train_expected_behavior_models,
)
from app.engine.sii.network_stability import analyze_network_stability
from app.engine.sii.propagation_analysis import analyze_propagation
from app.engine.sii.spectral_analysis import analyze_spectral_behavior


ADVANCED_MODULES = ("spectral_analysis", "dynamical_stability", "network_stability")


def evaluate_phase4(
    *,
    columns: list[str],
    rows: list[dict[str, Any]],
    numeric_columns: list[str],
    timestamp_column: str | None,
    telemetry_signal_catalog: dict[str, Any] | list[dict[str, Any]] | None,
    data_quality: dict[str, Any],
    sensor_health: dict[str, Any],
    operating_mode: dict[str, Any],
    signal_drift: dict[str, Any],
    relationship_analysis: dict[str, Any],
    relationship_graph: dict[str, Any],
    temporal_analysis: dict[str, Any],
    multiscale_analysis: dict[str, Any],
    physics_reasoning: dict[str, Any],
    covariance_analysis: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate and persist Phase 4 after all Phase 1–3 evidence is available."""

    cfg = config if isinstance(config, dict) else {}
    phase4_cfg = cfg.get("phase_4_config") if isinstance(cfg.get("phase_4_config"), dict) else {}
    source_run_id = _source_run_id(columns, rows, cfg)
    first_observed, observed_at, time_limitations = observation_bounds(rows, timestamp_column, source_run_id)
    identity = resolve_infrastructure_identity(
        columns=columns,
        telemetry_signal_catalog=telemetry_signal_catalog,
        config={**cfg, **phase4_cfg},
    )
    trace = _initial_trace(identity, source_run_id)
    storage_failures: list[str] = []
    storage_writes: list[dict[str, Any]] = []
    active_model: dict[str, Any] | None = None
    snapshots: list[dict[str, Any]] = []
    store: BehavioralModelStore | None = None

    if identity.get("memory_update_allowed"):
        configured_store = phase4_cfg.get("behavioral_model_store") or cfg.get("behavioral_model_store")
        try:
            store = configured_store if configured_store is not None else RuntimeBehavioralModelStore()
            active_model = store.load_model(str(identity["model_id"]))
            snapshots = store.list_snapshots(str(identity["model_id"]))
            trace["behavioral_model_loaded"] = active_model is not None
            trace["behavioral_model_created"] = active_model is None
        except Exception as exc:
            storage_failures.append(_storage_reason("load", exc))
            store = None
    compatibility = validate_model_compatibility(active_model, identity)
    previous_snapshot = snapshots[-1] if snapshots else None
    long_term_reference = snapshots[0] if snapshots else None
    mode_id = active_operating_mode(operating_mode)

    graph_comparison = compare_behavioral_graph(
        current_graph=relationship_graph,
        active_graph=active_model.get("behavioral_graph") if active_model else None,
        previous_snapshot_graph=previous_snapshot.get("behavioral_graph") if previous_snapshot else None,
        long_term_reference_graph=long_term_reference.get("behavioral_graph") if long_term_reference else None,
        operating_mode=mode_id,
        change_threshold=float(phase4_cfg.get("graph_change_threshold", 0.20)),
    )
    expected_behavior = evaluate_expected_behavior(
        active_model=active_model,
        rows=rows,
        operating_mode=mode_id,
        data_quality=data_quality,
        sensor_health=sensor_health,
        source_model_version=str(active_model.get("model_version")) if active_model else None,
        evaluation_time=observed_at,
        config=phase4_cfg.get("expected_behavior_config") if isinstance(phase4_cfg.get("expected_behavior_config"), dict) else None,
    )
    propagation = analyze_propagation(
        graph_comparison=graph_comparison,
        relationship_memory=(active_model or {}).get("relationship_memory", {}),
        signal_drift=signal_drift,
        expected_behavior=expected_behavior,
        operating_mode=operating_mode,
        sensor_health=sensor_health,
        data_quality=data_quality,
        multiscale_analysis=multiscale_analysis,
        signal_change_times=phase4_cfg.get("signal_change_times") if isinstance(phase4_cfg.get("signal_change_times"), dict) else None,
        config=phase4_cfg.get("propagation_config") if isinstance(phase4_cfg.get("propagation_config"), dict) else None,
    )
    evolution = evaluate_behavioral_evolution(
        active_model=active_model,
        snapshots=snapshots,
        rows=rows,
        numeric_columns=numeric_columns,
        relationship_graph_comparison=graph_comparison,
        operating_mode=operating_mode,
        expected_behavior=expected_behavior,
        learning_decision={"decision": "not_evaluated_yet"},
        current_confidence=None,
    )
    advanced = _advanced_modules(
        rows=rows,
        numeric_columns=numeric_columns,
        timestamp_column=timestamp_column,
        relationship_graph=relationship_graph,
        active_model=active_model,
        graph_comparison=graph_comparison,
        phase4_config=phase4_cfg,
    )
    bayesian = evaluate_bayesian_evidence(
        phase4_cfg.get("bayesian_evidence") if isinstance(phase4_cfg.get("bayesian_evidence"), dict) else None
    )

    active_observations = phase4_cfg.get("active_observations") if isinstance(phase4_cfg.get("active_observations"), list) else []
    learning = evaluate_baseline_evolution(
        active_model=active_model,
        rows_count=len(rows),
        numeric_columns=numeric_columns,
        operating_mode=operating_mode,
        data_quality=data_quality,
        sensor_health=sensor_health,
        temporal_analysis=temporal_analysis,
        multiscale_analysis=multiscale_analysis,
        physics_reasoning=physics_reasoning,
        expected_behavior=expected_behavior,
        graph_comparison=graph_comparison,
        active_observations=active_observations,
        source_run_id=source_run_id,
        effective_time=observed_at,
        model_version=str(active_model.get("model_version")) if active_model else "v1",
        config=phase4_cfg.get("baseline_evolution_config") if isinstance(phase4_cfg.get("baseline_evolution_config"), dict) else None,
    )
    if not identity.get("memory_update_allowed"):
        learning = _override_learning(learning, "insufficient_evidence", "infrastructure_identity_inadequate")
    elif store is None:
        learning = _override_learning(learning, "insufficient_evidence", "behavioral_model_storage_unavailable")
    elif not compatibility.get("compatible"):
        learning = _override_learning(learning, "rejected", "active_model_identity_conflict")
    elif active_model and not compatibility.get("schema_compatible"):
        learning = _override_learning(learning, "blocked_by_model_validation", "telemetry_schema_changed_requires_human_compatibility_review")

    projected_version = _projected_model_version(active_model, learning.get("learning_allowed", False))
    baseline_before = _baseline_version(active_model)
    candidate_baseline = learning.get("candidate_baseline") if isinstance(learning.get("candidate_baseline"), dict) else None
    baseline_after = (
        candidate_baseline.get("candidate_version")
        if candidate_baseline and learning.get("learning_allowed")
        else baseline_before
    )
    prepared_events = prepare_event_memory(
        external_events=phase4_cfg.get("external_events") if isinstance(phase4_cfg.get("external_events"), list) else None,
        expected_behavior=expected_behavior,
        graph_comparison=graph_comparison,
        operating_mode=operating_mode,
        learning_decision=learning,
        source_run_id=source_run_id,
        timestamp=observed_at,
        model_version_before=str(active_model.get("model_version")) if active_model else None,
        model_version_after=projected_version,
        baseline_version_before=baseline_before,
        baseline_version_after=baseline_after,
    )
    event_ids = [str(item["event_id"]) for item in prepared_events.get("events", [])]
    trained_models = {}
    if learning.get("learning_allowed"):
        # Expected models are fitted only after current evidence and learning gates finish.
        relationship_source = (active_model or {}).get("relationship_memory", {})
        if not relationship_source:
            relationship_source = _provisional_relationship_memory(relationship_graph, mode_id)
        trained_models = train_expected_behavior_models(
            rows=rows,
            relationship_memory=relationship_source,
            operating_mode=mode_id,
            timestamp_column=timestamp_column,
            source_run_id=source_run_id,
            training_time=observed_at,
            config=phase4_cfg.get("expected_behavior_config") if isinstance(phase4_cfg.get("expected_behavior_config"), dict) else None,
        )

    persisted_model = active_model
    current_snapshot: dict[str, Any] | None = None
    changes = {
        "model_version_before": str(active_model.get("model_version")) if active_model else None,
        "model_version_after": projected_version,
        "signals_added": 0,
        "signals_updated": 0,
        "relationships_added": 0,
        "relationships_updated": 0,
        "relationships_retired": 0,
        "learning_exclusions": [],
    }
    baseline_state: dict[str, Any] = {
        "previous_version": baseline_before,
        "candidate_version": candidate_baseline.get("candidate_version") if candidate_baseline else None,
        "active_version": baseline_before,
        "approval_status": candidate_baseline.get("approval_status") if candidate_baseline else None,
    }

    if store is not None and identity.get("model_id"):
        model_id = str(identity["model_id"])
        try:
            decision_record = store.record_learning_decision(model_id, learning, source_run_id=source_run_id)
            storage_writes.append(_write("record_learning_decision", decision_record.get("decision_id")))
        except Exception as exc:
            storage_failures.append(_storage_reason("record_learning_decision", exc))
        if candidate_baseline:
            try:
                stored_candidate = store.save_candidate_baseline(model_id, candidate_baseline, source_run_id=source_run_id)
                storage_writes.append(_write("save_candidate_baseline", stored_candidate.get("candidate_version")))
                baseline_state = {
                    "previous_version": stored_candidate.get("previous_version"),
                    "candidate_version": stored_candidate.get("candidate_version"),
                    "active_version": stored_candidate.get("active_version"),
                    "approval_status": stored_candidate.get("approval_status"),
                }
                if learning.get("learning_allowed"):
                    activated = store.activate_baseline(
                        model_id,
                        str(stored_candidate["candidate_version"]),
                        source_run_id=source_run_id,
                    )
                    storage_writes.append(_write("activate_baseline", activated.get("active_version")))
                    baseline_state["active_version"] = activated.get("active_version")
                    baseline_state["approval_status"] = activated.get("approval_status")
                    candidate_baseline = activated
            except Exception as exc:
                storage_failures.append(_storage_reason("baseline_write", exc))
                learning = _override_learning(learning, "rejected", "baseline_persistence_failed")
        if learning.get("learning_allowed") and not storage_failures:
            candidate_model, changes = build_candidate_model(
                active_model=active_model,
                identity=identity,
                rows=rows,
                numeric_columns=numeric_columns,
                timestamp_column=timestamp_column,
                telemetry_signal_catalog=telemetry_signal_catalog,
                signal_drift=signal_drift,
                relationship_graph=relationship_graph,
                operating_mode=operating_mode,
                sensor_health=sensor_health,
                data_quality=data_quality,
                temporal_analysis=temporal_analysis,
                multiscale_analysis=multiscale_analysis,
                physics_reasoning=physics_reasoning,
                expected_behavior=expected_behavior,
                trained_expected_models=trained_models,
                baseline_record=candidate_baseline,
                event_references=event_ids,
                source_run_id=source_run_id,
                observed_at=observed_at,
                allow_learning=True,
                config=phase4_cfg.get("behavioral_model_config") if isinstance(phase4_cfg.get("behavioral_model_config"), dict) else None,
            )
            candidate_model["learning_decisions"] = [
                *(active_model or {}).get("learning_decisions", []),
                deepcopy(learning),
            ][-100:]
            current_snapshot = build_behavioral_snapshot(
                model=candidate_model,
                source_run_id=source_run_id,
                created_at=observed_at,
                previous_snapshot_id=previous_snapshot.get("snapshot_id") if previous_snapshot else None,
                changes=changes,
            )
            candidate_model["snapshot_history"] = [
                *(active_model or {}).get("snapshot_history", []),
                current_snapshot["snapshot_id"],
            ][-100:]
            try:
                if active_model is None:
                    persisted_model = store.create_model(candidate_model, source_run_id=source_run_id)
                    storage_writes.append(_write("create_model", persisted_model.get("model_version")))
                    trace["behavioral_model_created"] = True
                else:
                    persisted_model = store.save_model(candidate_model, source_run_id=source_run_id)
                    storage_writes.append(_write("save_model", persisted_model.get("model_version")))
                stored_snapshot = store.create_snapshot(current_snapshot, source_run_id=source_run_id)
                storage_writes.append(_write("create_snapshot", stored_snapshot.get("snapshot_id")))
                current_snapshot = stored_snapshot
            except Exception as exc:
                storage_failures.append(_storage_reason("model_or_snapshot_write", exc))
                persisted_model = active_model
        elif active_model is not None and not storage_failures:
            current_snapshot = build_behavioral_snapshot(
                model=active_model,
                source_run_id=source_run_id,
                created_at=observed_at,
                previous_snapshot_id=previous_snapshot.get("snapshot_id") if previous_snapshot else None,
                changes={**changes, "learning_decision": learning.get("decision")},
            )
            try:
                current_snapshot = store.create_snapshot(current_snapshot, source_run_id=source_run_id)
                storage_writes.append(_write("create_snapshot", current_snapshot.get("snapshot_id")))
            except Exception as exc:
                storage_failures.append(_storage_reason("create_snapshot", exc))

        persisted_event_ids = []
        for event in prepared_events.get("events", []):
            try:
                stored_event = store.append_event(model_id, event, source_run_id=source_run_id)
                persisted_event_ids.append(str(stored_event["event_id"]))
                storage_writes.append(_write("append_event", stored_event.get("event_id")))
            except Exception as exc:
                storage_failures.append(_storage_reason("append_event", exc))
    else:
        persisted_event_ids = []

    if storage_failures:
        trace["storage_failures"] = list(storage_failures)
    trace.update(
        {
            "phase_4_active": True,
            "model_id": identity.get("model_id"),
            "model_version_before": str(active_model.get("model_version")) if active_model else None,
            "model_version_after": str(persisted_model.get("model_version")) if persisted_model else None,
            "snapshot_id": current_snapshot.get("snapshot_id") if current_snapshot else None,
            "previous_snapshot_id": previous_snapshot.get("snapshot_id") if previous_snapshot else None,
            "signals_evaluated": len(numeric_columns),
            "relationships_evaluated": len((active_model or {}).get("relationship_memory", {})),
            "expected_models_evaluated": int(expected_behavior.get("models_evaluated") or 0),
            "residuals_generated": len(expected_behavior.get("expected_values", [])),
            "candidate_paths_generated": len(propagation.get("candidate_paths", [])),
            "relationships_added": int(changes.get("relationships_added") or 0),
            "relationships_updated": int(changes.get("relationships_updated") or 0),
            "relationships_retired": int(changes.get("relationships_retired") or 0),
            "baselines_updated": 1 if learning.get("learning_allowed") and baseline_state.get("active_version") != baseline_before else 0,
            "baseline_updates_deferred": 1 if learning.get("pending_validation") or learning.get("decision") == "deferred" else 0,
            "events_recorded": len(persisted_event_ids),
            "learning_allowed": bool(learning.get("learning_allowed")),
            "learning_decision": learning.get("decision"),
            "learning_exclusions": deepcopy(changes.get("learning_exclusions", [])),
            "advanced_modules_attempted": list(ADVANCED_MODULES),
            "advanced_modules_completed": [name for name in ADVANCED_MODULES if advanced[name].get("status") == "complete"],
            "advanced_modules_limited": [name for name in ADVANCED_MODULES if advanced[name].get("status") == "limited"],
            "advanced_modules_failed": [name for name in ADVANCED_MODULES if advanced[name].get("status") == "failed"],
            "bayesian_evidence_active": False,
            "bayesian_evidence_deferred_reason": bayesian.get("reason"),
            "storage_writes": storage_writes,
            "storage_failures": storage_failures,
            "rollback_reference": current_snapshot.get("rollback_reference") if current_snapshot else None,
            "current_evidence_evaluated_before_model_update": True,
        }
    )
    model_limitations = [*time_limitations, *compatibility.get("limitations", [])]
    if storage_failures:
        model_limitations.extend(storage_failures)
    if not identity.get("memory_update_allowed"):
        model_limitations.extend(identity.get("identity_limitations", []))
    model_output = behavioral_model_section(
        model=persisted_model,
        identity=identity,
        snapshot_id=current_snapshot.get("snapshot_id") if current_snapshot else None,
        baseline_state=baseline_state,
        learning_decision=learning,
        processing_trace=trace,
        limitations=model_limitations,
    )
    graph_comparison["evidence_classification"] = "Supporting" if graph_comparison.get("changed_edges") else "Neutral"
    expected_behavior["evidence_classification"] = "Supporting" if expected_behavior.get("residual_evidence") else ("Limiting" if expected_behavior.get("status") == "limited" else "Neutral")
    propagation["evidence_classification"] = "Supporting" if propagation.get("candidate_paths") else "Limiting"
    evolution["evidence_classification"] = "Supporting" if evolution.get("unresolved_changes") or evolution.get("relationship_changes") else ("Limiting" if evolution.get("status") == "limited" else "Neutral")
    events_output = event_memory_section(prepared_events, persisted_event_ids)
    events_output["evidence_classification"] = "Neutral" if not persisted_event_ids else "Supporting"
    if storage_failures or (prepared_events.get("events") and not persisted_event_ids):
        events_output["status"] = "limited"
        events_output["limitations"] = list(dict.fromkeys([*events_output.get("limitations", []), *storage_failures, "Some prepared events were not persisted."]))

    snapshots_output = {
        "status": "complete" if current_snapshot else "limited",
        "current_snapshot_id": current_snapshot.get("snapshot_id") if current_snapshot else None,
        "previous_snapshot_id": previous_snapshot.get("snapshot_id") if previous_snapshot else None,
        "model_version": str(persisted_model.get("model_version")) if persisted_model else None,
        "changes": deepcopy(changes),
        "rollback_reference": current_snapshot.get("rollback_reference") if current_snapshot else None,
    }
    return {
        "behavioral_model": model_output,
        "expected_behavior": expected_behavior,
        "behavioral_evolution": evolution,
        "propagation_analysis": propagation,
        "behavioral_snapshots": snapshots_output,
        "event_memory": events_output,
        "spectral_analysis": advanced["spectral_analysis"],
        "dynamical_stability": advanced["dynamical_stability"],
        "network_stability": advanced["network_stability"],
        "bayesian_evidence": bayesian,
        "behavioral_graph_comparison": graph_comparison,
        "processing_trace": trace,
    }


def limited_phase4(reason: str) -> dict[str, Any]:
    empty_trace = {
        "phase_4_active": True,
        "behavioral_model_loaded": False,
        "behavioral_model_created": False,
        "storage_writes": [],
        "storage_failures": [reason],
        "bayesian_evidence_active": False,
        "bayesian_evidence_deferred_reason": "validated_likelihoods_and_calibration_unavailable",
    }
    return {
        "behavioral_model": {
            "status": "limited",
            "active": False,
            "model_id": None,
            "model_version": None,
            "snapshot_id": None,
            "identity": {},
            "behavioral_identity": {},
            "signal_memory_summary": {"signals_tracked": 0, "signals": []},
            "relationship_memory_summary": {"relationships_tracked": 0, "relationships": []},
            "behavioral_graph": {},
            "operating_mode_memory": {},
            "baseline_state": {},
            "confidence": {"not_probability": True, "factors": {}},
            "limitations": [reason],
            "learning_decision": {"decision": "insufficient_evidence", "reason": reason, "learning_allowed": False},
            "processing_trace": deepcopy(empty_trace),
        },
        "expected_behavior": _limited_section(reason, "models_evaluated", "signals_evaluated", "expected_values", "residual_evidence"),
        "behavioral_evolution": _limited_section(reason, "signal_changes", "relationship_changes", "graph_changes", "operating_mode_changes", "recovery_evidence", "adaptation_evidence", "unresolved_changes"),
        "propagation_analysis": _limited_section(reason, "activated_nodes", "activated_edges", "candidate_paths", "competing_paths", "unsupported_segments"),
        "behavioral_snapshots": {"status": "limited", "current_snapshot_id": None, "previous_snapshot_id": None, "model_version": None, "changes": {}, "rollback_reference": None},
        "event_memory": {"status": "limited", "events_recorded": 0, "events_referenced": [], "externally_supplied_events": [], "telemetry_derived_events": [], "limitations": [reason]},
        "spectral_analysis": {"status": "limited", "reason": reason, "limitations": [reason]},
        "dynamical_stability": {"status": "limited", "reason": reason, "limitations": [reason]},
        "network_stability": {"status": "limited", "reason": reason, "limitations": [reason]},
        "bayesian_evidence": evaluate_bayesian_evidence(),
        "behavioral_graph_comparison": {"status": "limited", "reason": reason, "changed_edges": []},
        "processing_trace": empty_trace,
    }


def _advanced_modules(
    *,
    rows: list[dict[str, Any]],
    numeric_columns: list[str],
    timestamp_column: str | None,
    relationship_graph: dict[str, Any],
    active_model: dict[str, Any] | None,
    graph_comparison: dict[str, Any],
    phase4_config: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    outputs: dict[str, dict[str, Any]] = {}
    calls = {
        "spectral_analysis": lambda: analyze_spectral_behavior(
            rows=rows,
            numeric_columns=numeric_columns,
            timestamp_column=timestamp_column,
            reference=(active_model or {}).get("spectral_reference"),
            config=phase4_config.get("spectral_config") if isinstance(phase4_config.get("spectral_config"), dict) else None,
        ),
        "dynamical_stability": lambda: analyze_dynamical_stability(
            rows=rows,
            numeric_columns=numeric_columns,
            timestamp_column=timestamp_column,
            config=phase4_config.get("dynamical_stability_config") if isinstance(phase4_config.get("dynamical_stability_config"), dict) else None,
        ),
        "network_stability": lambda: analyze_network_stability(
            current_graph=relationship_graph,
            active_graph=(active_model or {}).get("behavioral_graph"),
            graph_comparison=graph_comparison,
            config=phase4_config.get("network_stability_config") if isinstance(phase4_config.get("network_stability_config"), dict) else None,
        ),
    }
    for name, call in calls.items():
        try:
            outputs[name] = call()
        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"
            outputs[name] = {"status": "failed", "reason": reason, "limitations": [reason]}
    return outputs


def _source_run_id(columns: list[str], rows: list[dict[str, Any]], config: dict[str, Any]) -> str:
    configured = config.get("source_run_id") or config.get("run_id") or config.get("job_id")
    if configured:
        return str(configured)
    payload = {"columns": columns, "rows": rows}
    digest = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()[:24]
    return f"deterministic-run:{digest}"


def _initial_trace(identity: dict[str, Any], source_run_id: str) -> dict[str, Any]:
    return {
        "phase_4_active": True,
        "source_run_id": source_run_id,
        "behavioral_model_loaded": False,
        "behavioral_model_created": False,
        "model_id": identity.get("model_id"),
        "model_version_before": None,
        "model_version_after": None,
        "snapshot_id": None,
        "previous_snapshot_id": None,
        "signals_evaluated": 0,
        "relationships_evaluated": 0,
        "expected_models_evaluated": 0,
        "residuals_generated": 0,
        "candidate_paths_generated": 0,
        "relationships_added": 0,
        "relationships_updated": 0,
        "relationships_retired": 0,
        "baselines_updated": 0,
        "baseline_updates_deferred": 0,
        "events_recorded": 0,
        "learning_allowed": False,
        "learning_decision": "not_evaluated",
        "learning_exclusions": [],
        "advanced_modules_attempted": [],
        "advanced_modules_completed": [],
        "advanced_modules_limited": [],
        "advanced_modules_failed": [],
        "bayesian_evidence_active": False,
        "bayesian_evidence_deferred_reason": None,
        "storage_writes": [],
        "storage_failures": [],
        "rollback_reference": None,
    }


def _storage_reason(operation: str, exc: Exception) -> str:
    return f"{operation}:{type(exc).__name__}:{exc}"


def _write(operation: str, reference: Any) -> dict[str, Any]:
    return {"operation": operation, "reference": str(reference) if reference is not None else None}


def _projected_model_version(active_model: dict[str, Any] | None, learning_allowed: bool) -> str | None:
    if not learning_allowed:
        return str(active_model.get("model_version")) if active_model else None
    if not active_model:
        return "v1"
    digits = "".join(character for character in str(active_model.get("model_version") or "v0") if character.isdigit())
    return f"v{int(digits or 0) + 1}"


def _baseline_version(active_model: dict[str, Any] | None) -> str | None:
    if not active_model:
        return None
    history = active_model.get("baseline_history") or []
    for item in reversed(history):
        if isinstance(item, dict) and item.get("active_version"):
            return str(item["active_version"])
    versions = active_model.get("baseline_versions") or []
    return str(versions[-1]) if versions else None


def _override_learning(result: dict[str, Any], decision: str, reason: str) -> dict[str, Any]:
    return {
        **deepcopy(result),
        "decision": decision,
        "status": decision,
        "reason": reason,
        "learning_allowed": False,
        "pending_validation": False,
        "processing_trace": {
            **deepcopy(result.get("processing_trace") or {}),
            "override_reason": reason,
        },
    }


def _provisional_relationship_memory(graph: dict[str, Any], operating_mode: str) -> dict[str, Any]:
    from app.engine.sii.behavioral_graph import relationship_memory_id
    from app.engine.sii.common import relationship_columns

    candidates = graph.get("eligible_edges") if isinstance(graph, dict) else None
    if not isinstance(candidates, list) or not candidates:
        candidates = graph.get("edges", []) if isinstance(graph, dict) else []
    output = {}
    for edge in candidates:
        if not isinstance(edge, dict):
            continue
        columns = relationship_columns(edge)
        if len(columns) != 2:
            continue
        relationship_type = str(edge.get("relationship_type") or "linear_correlation")
        relationship_id = relationship_memory_id(columns[0], columns[1], relationship_type, operating_mode)
        output[relationship_id] = {
            "relationship_id": relationship_id,
            "source_signal": columns[0],
            "target_signal": columns[1],
            "relationship_type": relationship_type,
            "operating_modes_observed": [operating_mode],
            "current_strength": abs(float(edge.get("current_strength") or edge.get("current_correlation") or edge.get("recent_correlation") or 0.0)),
            "status": "active",
        }
    return output


def _limited_section(reason: str, *fields: str) -> dict[str, Any]:
    result: dict[str, Any] = {"status": "limited", "reason": reason, "limitations": [reason], "processing_trace": {}}
    for field in fields:
        result[field] = 0 if field.endswith("evaluated") else [] if field not in {"graph_changes"} else {}
    return result
