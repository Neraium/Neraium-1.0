from __future__ import annotations

import time
from typing import Any

from app.engine.analysis import assess_persistence
from app.engine.sii_contract import (
    ENGINE_NAME,
    ENGINE_VERSION,
    canonical_status,
    covariance_section,
    failed_result,
    limited_result,
    persistence_section,
    planned_section,
    status_copy,
    uncertainty_section,
)
from app.engine.sii import (
    analyze_mode_conditioned_baseline,
    analyze_multiscale,
    analyze_relationship_graph,
    estimate_empirical_thresholds,
    evaluate_adaptive_persistence,
    evaluate_phase4,
    evaluate_physics_reasoning,
    fuse_evidence,
    limited_phase4,
)
from app.engine.sii_inputs import build_data_conditions, normalize_rows, numeric_columns
from app.engine.temporal_math import TemporalMathConfig, evaluate_temporal_math
from app.services.baseline_analysis import build_baseline_analysis
from app.services.operating_modes import apply_operating_mode_context, assess_operating_modes
from app.services.relationship_baselines import build_relationship_baseline
from app.services.sensor_health import (
    apply_sensor_health_context,
    assess_sensor_health,
    build_data_confidence,
)
from app.services.sii_runner import run_sii_runner
from app.services.telemetry_classification import (
    build_telemetry_signal_catalog,
    update_catalog_from_baseline,
)


def evaluate_sii(
    *,
    columns,
    rows,
    numeric_profiles,
    timestamp_column,
    telemetry_signal_catalog=None,
    data_quality=None,
    sensor_health=None,
    operating_mode=None,
    config=None,
    progress_callback=None,
) -> dict:
    """Run the authoritative, read-only SII evidence orchestration path.

    Phase 1 calculations remain unchanged. Phase 2 adds isolated graph-level,
    like-mode, elapsed-time persistence, multi-scale, and empirical-threshold
    evidence. Phase 3 evaluates externally configured engineering priors and
    organizes independent evidence without scoring it. No module diagnoses
    root cause, prescribes work, or treats confidence as probability.
    """

    started = time.perf_counter()
    cfg = dict(config) if isinstance(config, dict) else {}
    column_names = [str(column) for column in columns]
    profile_list = [dict(item) for item in numeric_profiles if isinstance(item, dict)]
    dict_rows, matrix_rows = normalize_rows(column_names, rows)
    numeric_columns_used = numeric_columns(
        columns=column_names,
        numeric_profiles=profile_list,
        configured_columns=cfg.get("numeric_columns"),
    )
    attempted: list[str] = []
    completed: list[str] = []
    limited: list[str] = []
    failed: list[str] = []
    failures: list[dict[str, str]] = []
    module_statuses: dict[str, dict[str, str]] = {}

    def notify(step: str, progress: float) -> None:
        if not progress_callback:
            return
        try:
            progress_callback(
                step,
                float(progress),
                {
                    "modules_attempted": list(attempted),
                    "modules_completed": list(completed),
                    "modules_limited": list(limited),
                    "modules_failed": list(failed),
                },
            )
        except Exception:
            pass

    def record(module: str, status: str, reason: str | None = None) -> None:
        normalized_status = status if status in {"complete", "limited", "failed"} else "failed"
        if module not in attempted:
            attempted.append(module)
        target = completed if normalized_status == "complete" else limited if normalized_status == "limited" else failed
        if module not in target:
            target.append(module)
        module_statuses[module] = {"status": normalized_status}
        if reason:
            module_statuses[module]["reason"] = str(reason)
        if normalized_status == "failed":
            failure = {"module": module, "reason": str(reason or f"invalid_module_status:{status}")}
            failures.append(failure)
            module_statuses[module]["reason"] = failure["reason"]

    notify("prepare_inputs", 0.02)

    try:
        attempted.append("telemetry_catalog")
        catalog = telemetry_signal_catalog
        if catalog is None:
            catalog = build_telemetry_signal_catalog(
                column_names,
                numeric_profiles=profile_list,
                timestamp_column=timestamp_column,
                header_present=bool(cfg.get("header_present", True)),
            )
        record("telemetry_catalog", "complete")
    except Exception as exc:
        catalog = telemetry_signal_catalog or {}
        record("telemetry_catalog", "failed", f"{type(exc).__name__}: {exc}")

    notify("signal_drift", 0.10)
    try:
        attempted.append("signal_drift")
        baseline_analysis = build_baseline_analysis(
            column_names,
            matrix_rows,
            profile_list,
            telemetry_signal_catalog=catalog,
        )
        drift_status = "complete" if int(baseline_analysis.get("baseline_window_rows") or 0) > 0 else "limited"
        record("signal_drift", drift_status, (baseline_analysis.get("warnings") or [None])[0])
    except Exception as exc:
        baseline_analysis = failed_result(exc)
        record("signal_drift", "failed", baseline_analysis["reason"])

    try:
        attempted.append("telemetry_catalog_enrichment")
        catalog = update_catalog_from_baseline(catalog, baseline_analysis)
        record("telemetry_catalog_enrichment", "complete")
    except Exception as exc:
        record(
            "telemetry_catalog_enrichment",
            "failed",
            f"{type(exc).__name__}: {exc}",
        )

    notify("relationship_analysis", 0.22)
    try:
        attempted.append("relationship_analysis")
        relationship_model = build_relationship_baseline(
            dict_rows,
            numeric_columns_used,
            total_row_count=int(cfg.get("row_count_total") or len(dict_rows)),
            baseline_analysis=baseline_analysis,
            telemetry_signal_catalog=catalog,
        )
        relationship_status = "complete"
        if len(dict_rows) < 12 or int(relationship_model.get("relationship_columns_analyzed") or 0) < 2:
            relationship_status = "limited"
        record(
            "relationship_analysis",
            relationship_status,
            "insufficient_relationship_history"
            if relationship_status == "limited"
            else None,
        )
    except Exception as exc:
        relationship_model = failed_result(exc)
        record("relationship_analysis", "failed", relationship_model["reason"])

    notify("operating_modes", 0.30)
    try:
        attempted.append("operating_modes")
        operating_mode_result = (
            dict(operating_mode)
            if isinstance(operating_mode, dict)
            else assess_operating_modes(
                dict_rows,
                timestamp_column=timestamp_column,
                telemetry_signal_catalog=catalog,
            )
        )
        mode_status = "complete" if operating_mode_result.get("match") != "unavailable" else "limited"
        relationship_model = apply_operating_mode_context(relationship_model, operating_mode_result)
        record("operating_modes", mode_status, (operating_mode_result.get("reasons") or [None])[0])
    except Exception as exc:
        operating_mode_result = failed_result(exc)
        record("operating_modes", "failed", operating_mode_result["reason"])

    notify("data_conditions", 0.38)
    try:
        attempted.append("data_conditions")
        data_quality_result, timestamp_profile = build_data_conditions(
            columns=column_names,
            matrix_rows=matrix_rows,
            numeric_columns_used=numeric_columns_used,
            numeric_profiles=profile_list,
            timestamp_column=timestamp_column,
            baseline_analysis=baseline_analysis,
            provided_data_quality=data_quality if isinstance(data_quality, dict) else None,
            config=cfg,
        )
        data_quality_result["operating_mode"] = operating_mode_result
        record("data_conditions", "complete")
    except Exception as exc:
        data_quality_result = {
            "readiness": "not_ready",
            "warnings": [f"Data-condition assembly failed: {type(exc).__name__}: {exc}"],
        }
        timestamp_profile = cfg.get("timestamp_profile") if isinstance(cfg.get("timestamp_profile"), dict) else {}
        record("data_conditions", "failed", data_quality_result["warnings"][0])

    notify("sensor_health", 0.46)
    try:
        attempted.append("sensor_health")
        sensor_health_result = (
            dict(sensor_health)
            if isinstance(sensor_health, dict)
            else assess_sensor_health(
                dict_rows,
                numeric_columns_used,
                timestamp_column=timestamp_column,
                numeric_profiles=profile_list,
                normalization_report=(
                    cfg.get("normalization_report")
                    if isinstance(cfg.get("normalization_report"), dict)
                    else {}
                ),
                ingestion_report=cfg.get("ingestion_report") if isinstance(cfg.get("ingestion_report"), dict) else {},
                timestamp_profile=timestamp_profile,
                relationship_model=relationship_model,
                telemetry_signal_catalog=catalog,
            )
        )
        data_quality_result["sensor_health"] = list(sensor_health_result.get("signals") or [])
        data_quality_result["sensor_health_summary"] = {
            key: sensor_health_result.get(key)
            for key in (
                "source_conditions",
                "population_rows",
                "assessed_rows",
                "sampled_for_signal_health",
                "assessment_method",
            )
        }
        data_quality_result["data_confidence"] = build_data_confidence(data_quality_result, sensor_health_result)
        relationship_model = apply_sensor_health_context(
            relationship_model,
            sensor_health=sensor_health_result,
            data_quality=data_quality_result,
        )
        record("sensor_health", "complete")
    except Exception as exc:
        sensor_health_result = failed_result(exc)
        data_quality_result["data_confidence"] = {
            "rating": "low",
            "summary": "Signal-health evidence was unavailable.",
            "reasons": [sensor_health_result["reason"]],
            "affected_signals": [],
        }
        record("sensor_health", "failed", sensor_health_result["reason"])

    notify("empirical_thresholds", 0.50)
    try:
        attempted.append("empirical_thresholds")
        relationship_source_graph = relationship_model.get("relationship_graph") if isinstance(relationship_model, dict) else None
        relationship_fit_columns = [
            str(node.get("source_column"))
            for node in (relationship_source_graph.get("nodes", []) if isinstance(relationship_source_graph, dict) else [])
            if isinstance(node, dict) and node.get("type") == "metric" and node.get("source_column")
        ]
        empirical_thresholds = estimate_empirical_thresholds(
            rows=dict_rows,
            numeric_columns=numeric_columns_used,
            relationship_columns=list(dict.fromkeys(relationship_fit_columns)),
            config=cfg.get("empirical_threshold_config") if isinstance(cfg.get("empirical_threshold_config"), dict) else None,
        )
        record(
            "empirical_thresholds",
            str(empirical_thresholds.get("status") or "limited"),
            empirical_thresholds.get("reason"),
        )
    except Exception as exc:
        empirical_thresholds = failed_result(exc)
        record("empirical_thresholds", "failed", empirical_thresholds["reason"])

    notify("mode_conditioned_baseline", 0.54)
    try:
        attempted.append("mode_conditioned_baseline")
        mode_conditioned = analyze_mode_conditioned_baseline(
            rows=dict_rows,
            numeric_columns=numeric_columns_used,
            timestamp_column=timestamp_column,
            telemetry_signal_catalog=catalog,
            relationship_model=relationship_model,
            operating_mode=operating_mode_result,
            config=cfg.get("mode_conditioned_config") if isinstance(cfg.get("mode_conditioned_config"), dict) else None,
        )
        record(
            "mode_conditioned_baseline",
            str(mode_conditioned.get("status") or "limited"),
            mode_conditioned.get("reason"),
        )
    except Exception as exc:
        mode_conditioned = failed_result(exc)
        mode_conditioned["used_global_fallback"] = True
        mode_conditioned["fallback_reason"] = mode_conditioned["reason"]
        record("mode_conditioned_baseline", "failed", mode_conditioned["reason"])

    notify("relationship_graph_analysis", 0.58)
    try:
        attempted.append("relationship_graph_analysis")
        learned_relationship = empirical_thresholds.get("relationship_change") if isinstance(empirical_thresholds, dict) else None
        learned_change_threshold = (
            learned_relationship.get("threshold")
            if isinstance(learned_relationship, dict)
            else None
        )
        graph_config = dict(cfg.get("relationship_graph_config") or {}) if isinstance(cfg.get("relationship_graph_config"), dict) else {}
        if learned_change_threshold is not None:
            graph_config.setdefault("change_inclusion_threshold", float(learned_change_threshold))
        dynamic_relationship_graph = analyze_relationship_graph(
            relationship_model=relationship_model,
            telemetry_signal_catalog=catalog,
            sensor_health=sensor_health_result,
            data_quality=data_quality_result,
            operating_mode=operating_mode_result,
            mode_conditioned_analysis=mode_conditioned,
            config=graph_config,
        )
        record(
            "relationship_graph_analysis",
            str(dynamic_relationship_graph.get("status") or "limited"),
            dynamic_relationship_graph.get("reason"),
        )
    except Exception as exc:
        dynamic_relationship_graph = failed_result(exc)
        record("relationship_graph_analysis", "failed", dynamic_relationship_graph["reason"])

    notify("fixed_persistence", 0.62)
    try:
        attempted.append("fixed_persistence")
        fixed_persistence = assess_persistence(column_names, matrix_rows, baseline_analysis)
        fixed_status = "limited" if fixed_persistence.get("status") == "limited" else "complete"
        record("fixed_persistence", fixed_status, (fixed_persistence.get("limitations") or [None])[0])
    except Exception as exc:
        fixed_persistence = failed_result(exc)
        record("fixed_persistence", "failed", fixed_persistence["reason"])

    notify("adaptive_persistence", 0.66)
    try:
        attempted.append("adaptive_persistence")
        adaptive_config = (
            dict(cfg.get("adaptive_persistence_config"))
            if isinstance(cfg.get("adaptive_persistence_config"), dict)
            else {}
        )
        adaptive_config.setdefault("align_to_phase2_active_window", True)
        adaptive_persistence = evaluate_adaptive_persistence(
            rows=dict_rows,
            timestamp_column=timestamp_column,
            baseline_analysis=baseline_analysis,
            fixed_persistence=fixed_persistence,
            empirical_thresholds=empirical_thresholds,
            data_quality=data_quality_result,
            sensor_health=sensor_health_result,
            operating_mode=operating_mode_result,
            config=adaptive_config,
        )
        record(
            "adaptive_persistence",
            str(adaptive_persistence.get("status") or "limited"),
            adaptive_persistence.get("reason"),
        )
    except Exception as exc:
        adaptive_persistence = failed_result(exc)
        record("adaptive_persistence", "failed", adaptive_persistence["reason"])

    notify("temporal_analysis", 0.70)
    try:
        attempted.append("temporal_analysis")
        temporal_config = cfg.get("temporal_config")
        if isinstance(temporal_config, dict):
            temporal_config = TemporalMathConfig(**temporal_config)
        if not isinstance(temporal_config, TemporalMathConfig):
            temporal_config = None
        temporal_analysis = evaluate_temporal_math(
            columns=column_names,
            rows=matrix_rows,
            numeric_profiles=profile_list,
            timestamp_column=timestamp_column,
            config=temporal_config,
            progress_callback=None,
        )
        temporal_status = str(temporal_analysis.get("status") or "complete")
        record("temporal_analysis", temporal_status, temporal_analysis.get("reason"))
    except Exception as exc:
        temporal_analysis = failed_result(exc)
        record("temporal_analysis", "failed", temporal_analysis["reason"])

    notify("multiscale_analysis", 0.76)
    try:
        attempted.append("multiscale_analysis")
        multiscale_config = dict(cfg.get("multiscale_config") or {}) if isinstance(cfg.get("multiscale_config"), dict) else {}
        multiscale_analysis = analyze_multiscale(
            rows=dict_rows,
            numeric_columns=numeric_columns_used,
            timestamp_column=timestamp_column,
            empirical_thresholds=empirical_thresholds,
            config=multiscale_config,
        )
        record(
            "multiscale_analysis",
            str(multiscale_analysis.get("status") or "limited"),
            multiscale_analysis.get("reason"),
        )
    except Exception as exc:
        multiscale_analysis = failed_result(exc)
        multiscale_analysis["scales_used"] = []
        record("multiscale_analysis", "failed", multiscale_analysis["reason"])

    legacy_baseline_analysis = {
        **baseline_analysis,
        "top_relationship_changes": relationship_model.get("top_relationship_changes", []),
        "baseline_relationships": relationship_model.get("baseline_relationships", []),
        "relationship_graph": relationship_model.get("relationship_graph", {}),
        "sampled_for_baseline": bool(relationship_model.get("sampled_for_baseline")),
    }
    compatibility_payload = {
        "engine_result": cfg.get("engine_result") if isinstance(cfg.get("engine_result"), dict) else {},
        "driver_attribution": cfg.get("driver_attribution") if isinstance(cfg.get("driver_attribution"), dict) else {},
        "primary_room": str(cfg.get("primary_room") or "Uploaded telemetry"),
        "processing_trace": cfg.get("processing_trace") if isinstance(cfg.get("processing_trace"), dict) else {},
    }
    context_factory = cfg.get("compatibility_context_factory")
    if callable(context_factory):
        try:
            attempted.append("compatibility_context")
            built_context = context_factory(
                {
                    "baseline_analysis": legacy_baseline_analysis,
                    "relationship_model": relationship_model,
                    "operating_mode": operating_mode_result,
                    "data_quality": data_quality_result,
                    "sensor_health": sensor_health_result,
                    "timestamp_profile": timestamp_profile,
                    "telemetry_signal_catalog": catalog,
                }
            )
            if isinstance(built_context, dict):
                compatibility_payload.update(built_context)
            record("compatibility_context", "complete")
        except Exception as exc:
            record(
                "compatibility_context",
                "failed",
                f"{type(exc).__name__}: {exc}",
            )

    notify("covariance_analysis", 0.84)
    try:
        attempted.append("covariance_analysis")
        runner_result = run_sii_runner(
            columns=column_names,
            rows=matrix_rows,
            numeric_profiles=profile_list,
            timestamp_column=timestamp_column,
            primary_room=str(compatibility_payload.get("primary_room") or "Uploaded telemetry"),
            driver_attribution=(
                compatibility_payload.get("driver_attribution")
                if isinstance(compatibility_payload.get("driver_attribution"), dict)
                else {}
            ),
            engine_result=(
                compatibility_payload.get("engine_result")
                if isinstance(compatibility_payload.get("engine_result"), dict)
                else {}
            ),
            processing_trace=(
                compatibility_payload.get("processing_trace")
                if isinstance(compatibility_payload.get("processing_trace"), dict)
                else {}
            ),
            telemetry_signal_catalog=catalog,
        )
        covariance = covariance_section(runner_result)
        record("covariance_analysis", str(covariance.get("status") or "complete"), covariance.get("reason"))
    except Exception as exc:
        runner_result = {
            "runner_used": False,
            "rows_received": len(matrix_rows),
            "rows_processed": 0,
            "columns_used": [],
            "errors": [f"{type(exc).__name__}: {exc}"],
        }
        covariance = failed_result(exc)
        record("covariance_analysis", "failed", covariance["reason"])

    relationship_graph = relationship_model.get("relationship_graph")
    if isinstance(dynamic_relationship_graph, dict) and dynamic_relationship_graph.get("status") != "failed":
        canonical_graph = dynamic_relationship_graph
    elif isinstance(relationship_graph, dict):
        graph_status = "complete" if relationship_graph.get("edges") else "limited"
        canonical_graph = {
            **status_copy(
                relationship_graph,
                status=graph_status,
                reason="no_comparable_relationship_edges" if graph_status == "limited" else None,
            ),
            "phase_2_status": dynamic_relationship_graph,
            "edge_basis": "global_relationship_model_failure_fallback",
        }
    else:
        canonical_graph = limited_result("relationship_graph_unavailable", nodes=[], edges=[], changed_edges=[])

    signal_status = (
        "limited"
        if baseline_analysis.get("status") == "failed"
        or int(baseline_analysis.get("baseline_window_rows") or 0) <= 0
        else "complete"
    )
    mode_status = "complete" if operating_mode_result.get("match") not in {None, "unavailable"} else "limited"
    relationship_status = "failed" if relationship_model.get("status") == "failed" else (
        "limited"
        if len(dict_rows) < 12
        or int(relationship_model.get("relationship_columns_analyzed") or 0) < 2
        else "complete"
    )
    temporal_status = str(temporal_analysis.get("status") or "complete")
    persistence = persistence_section(
        fixed_persistence=fixed_persistence,
        adaptive_persistence=adaptive_persistence,
        baseline_analysis=baseline_analysis,
        runner_result=runner_result,
        temporal_analysis=temporal_analysis,
    )
    operating_modes_used = [
        str(value)
        for value in (
            operating_mode_result.get("baseline_mode"),
            operating_mode_result.get("recent_mode"),
        )
        if value and value != "unavailable"
    ]
    rows_received = int(cfg.get("row_count_total") or len(matrix_rows))
    phase_2_uncertainty = uncertainty_section(
        data_quality=data_quality_result,
        sensor_health=sensor_health_result,
        temporal_analysis=temporal_analysis,
        module_failures=list(failures),
    )
    phase_2_evidence = {
        "signal_drift": status_copy(baseline_analysis, status=signal_status),
        "relationship_analysis": {
            **status_copy(relationship_model, status=relationship_status),
            "mode_conditioned_baseline": mode_conditioned,
        },
        "operating_modes": {
            **status_copy(operating_mode_result, status=mode_status),
            "mode_conditioned_baseline": mode_conditioned,
        },
        "adaptive_persistence": adaptive_persistence,
        "temporal_analysis": status_copy(temporal_analysis, status=temporal_status),
        "multiscale_analysis": multiscale_analysis,
        "relationship_graph": canonical_graph,
        "covariance_analysis": covariance,
        "data_quality": data_quality_result,
        "sensor_health": sensor_health_result,
        "uncertainty": phase_2_uncertainty,
    }

    notify("physics_reasoning", 0.90)
    try:
        attempted.append("physics_reasoning")
        physics_config = (
            dict(cfg.get("physics_reasoning_config"))
            if isinstance(cfg.get("physics_reasoning_config"), dict)
            else {}
        )
        configured_priors = physics_config.get("priors")
        if not isinstance(configured_priors, list):
            configured_priors = (
                cfg.get("engineering_priors")
                if isinstance(cfg.get("engineering_priors"), list)
                else []
            )
        equipment_context = physics_config.get("equipment_context")
        if not isinstance(equipment_context, dict):
            equipment_context = (
                cfg.get("equipment_context")
                if isinstance(cfg.get("equipment_context"), dict)
                else {}
            )
        physics_reasoning = evaluate_physics_reasoning(
            priors=configured_priors,
            analytical_evidence=phase_2_evidence,
            equipment_context=equipment_context,
        )
        record(
            "physics_reasoning",
            str(physics_reasoning.get("status") or "limited"),
            physics_reasoning.get("reason"),
        )
    except Exception as exc:
        physics_reasoning = {
            **failed_result(exc),
            "active": True,
            "evaluated_priors": [],
            "applicable_priors": [],
            "supporting_priors": [],
            "contradictory_priors": [],
            "ignored_priors": [],
            "limitations": [f"{type(exc).__name__}: {exc}"],
            "reasoning_trace": [],
        }
        record("physics_reasoning", "failed", physics_reasoning["reason"])

    notify("behavioral_model", 0.94)
    try:
        attempted.append("phase_4")
        phase_4 = evaluate_phase4(
            columns=column_names,
            rows=dict_rows,
            numeric_columns=numeric_columns_used,
            timestamp_column=timestamp_column,
            telemetry_signal_catalog=catalog,
            data_quality=data_quality_result,
            sensor_health=sensor_health_result,
            operating_mode=operating_mode_result,
            signal_drift=baseline_analysis,
            relationship_analysis=relationship_model,
            relationship_graph=canonical_graph,
            temporal_analysis=temporal_analysis,
            multiscale_analysis=multiscale_analysis,
            physics_reasoning=physics_reasoning,
            covariance_analysis=covariance,
            config=cfg,
        )
        phase_4_status = str((phase_4.get("behavioral_model") or {}).get("status") or "limited")
        record(
            "phase_4",
            phase_4_status,
            ((phase_4.get("behavioral_model") or {}).get("limitations") or [None])[0],
        )
    except Exception as exc:
        phase_4 = limited_phase4(f"{type(exc).__name__}: {exc}")
        record("phase_4", "failed", f"{type(exc).__name__}: {exc}")

    preliminary_uncertainty = uncertainty_section(
        data_quality=data_quality_result,
        sensor_health=sensor_health_result,
        temporal_analysis=temporal_analysis,
        module_failures=list(failures),
    )
    fusion_inputs = {
        **phase_2_evidence,
        "behavioral_model": phase_4["behavioral_model"],
        "expected_behavior": phase_4["expected_behavior"],
        "behavioral_evolution": phase_4["behavioral_evolution"],
        "propagation_analysis": phase_4["propagation_analysis"],
        "event_memory": phase_4["event_memory"],
        "spectral_analysis": phase_4["spectral_analysis"],
        "dynamical_stability": phase_4["dynamical_stability"],
        "network_stability": phase_4["network_stability"],
        "bayesian_evidence": phase_4["bayesian_evidence"],
        "uncertainty": preliminary_uncertainty,
    }
    preliminary_statuses = {
        **module_statuses,
        "relationship_graph": dict(
            module_statuses.get("relationship_graph_analysis", {"status": "limited"})
        ),
        "data_quality": dict(
            module_statuses.get("data_conditions", {"status": "limited"})
        ),
        "uncertainty": {"status": str(preliminary_uncertainty.get("status") or "limited")},
        **{
            module: {"status": str((phase_4.get(module) or {}).get("status") or "limited")}
            for module in (
                "behavioral_model",
                "expected_behavior",
                "behavioral_evolution",
                "propagation_analysis",
                "event_memory",
                "spectral_analysis",
                "dynamical_stability",
                "network_stability",
                "bayesian_evidence",
            )
        },
    }
    preliminary_trace = {
        "sii_engine_called": True,
        "sii_engine_version": ENGINE_VERSION,
        "modules_attempted": list(attempted),
        "modules_completed": list(completed),
        "modules_limited": list(limited),
        "modules_failed": list(failed),
        "module_statuses": preliminary_statuses,
        "module_failures": list(failures),
        "phase_2_authoritative": False,
        "phase_2_effect": "supporting_evidence_only",
        "phase_3_active": True,
        "phase_3_effect": "transparent_evidence_enrichment_only",
        "phase_4_effect": "persistent_behavioral_memory_and_evidence_only",
        **dict(phase_4.get("processing_trace") or {}),
        "rows_received": rows_received,
        "rows_used": len(matrix_rows),
        "columns_used": list(numeric_columns_used),
        "operating_modes_used": list(dict.fromkeys(operating_modes_used)),
        "scales_used": list(multiscale_analysis.get("scales_used") or []) if isinstance(multiscale_analysis, dict) else [],
    }

    notify("evidence_fusion", 0.98)
    try:
        attempted.append("evidence_fusion")
        evidence_fusion = fuse_evidence(
            analytical_evidence=fusion_inputs,
            physics_reasoning=physics_reasoning,
            processing_trace=preliminary_trace,
        )
        record(
            "evidence_fusion",
            str(evidence_fusion.get("status") or "limited"),
            evidence_fusion.get("reason"),
        )
    except Exception as exc:
        evidence_fusion = {
            **failed_result(exc),
            "active": True,
            "observations": [],
            "supporting_evidence": [],
            "limiting_evidence": [],
            "contradictory_evidence": [],
            "neutral_evidence": [],
            "evidence_inventory": [],
            "uncertainty": preliminary_uncertainty,
            "processing_trace": {
                "weighted_scoring_performed": False,
                "diagnosis_performed": False,
                "recommendations_generated": False,
            },
        }
        record("evidence_fusion", "failed", evidence_fusion["reason"])

    uncertainty = uncertainty_section(
        data_quality=data_quality_result,
        sensor_health=sensor_health_result,
        temporal_analysis=temporal_analysis,
        module_failures=list(failures),
    )
    runtime = round(max(0.0, time.perf_counter() - started), 6)
    final_statuses = {
        **module_statuses,
        "relationship_graph": dict(
            module_statuses.get("relationship_graph_analysis", {"status": "limited"})
        ),
        "data_quality": dict(
            module_statuses.get("data_conditions", {"status": "limited"})
        ),
        "uncertainty": {"status": str(uncertainty.get("status") or "limited")},
        **{
            module: {"status": str((phase_4.get(module) or {}).get("status") or "limited")}
            for module in (
                "behavioral_model",
                "expected_behavior",
                "behavioral_evolution",
                "propagation_analysis",
                "event_memory",
                "spectral_analysis",
                "dynamical_stability",
                "network_stability",
                "bayesian_evidence",
            )
        },
    }
    processing_trace = {
        **preliminary_trace,
        "modules_attempted": list(attempted),
        "modules_completed": list(completed),
        "modules_limited": list(limited),
        "modules_failed": list(failed),
        "module_statuses": final_statuses,
        "module_failures": list(failures),
        "engineering_priors_evaluated": len(physics_reasoning.get("evaluated_priors") or []),
        "engineering_priors_applicable": len(physics_reasoning.get("applicable_priors") or []),
        "engineering_observations_generated": len(evidence_fusion.get("observations") or []),
        "total_runtime_seconds": runtime,
    }
    runner_trace = runner_result.get("processing_trace") if isinstance(runner_result, dict) else None
    if isinstance(runner_trace, dict):
        processing_trace = {**runner_trace, **processing_trace}

    notify("complete", 1.0)
    result = {
        "engine": {"name": ENGINE_NAME, "version": ENGINE_VERSION},
        "status": canonical_status(
            rows_used=len(matrix_rows),
            core_statuses=[
                signal_status,
                relationship_status,
                temporal_status,
                str(covariance.get("status") or "limited"),
            ],
            failed_modules=failed,
        ),
        "data_conditions": {
            "status": "complete" if data_quality_result.get("readiness") != "not_ready" else "limited",
            "empirical_thresholds": empirical_thresholds,
            "data_quality": data_quality_result,
            "sensor_health": sensor_health_result,
            "timestamp_profile": timestamp_profile,
            "rows_received": rows_received,
            "rows_used": len(matrix_rows),
            "numeric_columns": numeric_columns_used,
        },
        "operating_modes": {
            **status_copy(operating_mode_result, status=mode_status),
            "mode_conditioned_baseline": mode_conditioned,
        },
        "signal_drift": status_copy(baseline_analysis, status=signal_status),
        "relationship_analysis": {
            **status_copy(relationship_model, status=relationship_status),
            "mode_conditioned_baseline": mode_conditioned,
        },
        "relationship_graph": canonical_graph,
        "covariance_analysis": covariance,
        "temporal_analysis": status_copy(temporal_analysis, status=temporal_status),
        "multiscale_analysis": multiscale_analysis,
        "physics_reasoning": physics_reasoning,
        "physics_evidence": physics_reasoning,
        "propagation_analysis": phase_4["propagation_analysis"],
        "persistence_analysis": persistence,
        "evidence_fusion": evidence_fusion,
        "behavioral_model": phase_4["behavioral_model"],
        "expected_behavior": phase_4["expected_behavior"],
        "behavioral_evolution": phase_4["behavioral_evolution"],
        "behavioral_snapshots": phase_4["behavioral_snapshots"],
        "event_memory": phase_4["event_memory"],
        "spectral_analysis": phase_4["spectral_analysis"],
        "dynamical_stability": phase_4["dynamical_stability"],
        "network_stability": phase_4["network_stability"],
        "bayesian_evidence": phase_4["bayesian_evidence"],
        "findings": [],
        "uncertainty": uncertainty,
        "processing_trace": processing_trace,
        "compatibility": {
            "baseline_analysis": legacy_baseline_analysis,
            "relationship_model": relationship_model,
            "engine_result": (
                compatibility_payload.get("engine_result")
                if isinstance(compatibility_payload.get("engine_result"), dict)
                else {}
            ),
            "driver_attribution": (
                compatibility_payload.get("driver_attribution")
                if isinstance(compatibility_payload.get("driver_attribution"), dict)
                else {}
            ),
            "sii_runner_result": runner_result,
            "telemetry_signal_catalog": catalog,
            "data_quality": data_quality_result,
            "sensor_health": sensor_health_result,
            "operating_mode": operating_mode_result,
            "timestamp_profile": timestamp_profile,
            "temporal_analysis": temporal_analysis,
        },
    }
    return result
