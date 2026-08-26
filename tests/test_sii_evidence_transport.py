from __future__ import annotations

from app.engine.sii_engine import evaluate_sii
from app.models.api_models import EvidenceRunResponse
from app.services.analysis_result_contract import build_analysis_result
from app.services.upload_evidence import build_evidence_record_from_result
from app.services.upload_persistence import project_result_for_transport


def _engine_profiles(columns: list[str]) -> list[dict[str, object]]:
    return [
        {
            "column": column,
            "constant_or_stuck": False,
            "missing_count": 0,
            "non_numeric_count": 0,
        }
        for column in columns
        if column != "timestamp"
    ]


def test_real_engine_relationship_evidence_reaches_transport_projection() -> None:
    columns = ["timestamp", "flow", "pressure", "power"]
    rows = []
    for index in range(120):
        flow = 80.0 + index * 0.25
        pressure = 10.0 + flow * 0.5 if index < 84 else 35.0 + ((index * 17) % 11)
        timestamp = f"2026-01-02T{index // 60:02d}:{index % 60:02d}:00Z"
        rows.append(
            {
                "timestamp": timestamp,
                "flow": f"{flow:.6f}",
                "pressure": f"{pressure:.6f}",
                "power": f"{15.0 + flow * 0.2:.6f}",
            }
        )
    sii_result = evaluate_sii(
        columns=columns,
        rows=rows,
        numeric_profiles=_engine_profiles(columns),
        timestamp_column="timestamp",
        config={"numeric_columns": columns[1:]},
    )
    result = {
        "job_id": "engine-transport",
        "filename": "engine-transport.csv",
        "columns": columns,
        "row_count": len(rows),
        "data_quality": {"readiness": "ready", "warnings": []},
        "sii_result": sii_result,
    }
    projected = project_result_for_transport(result)
    relationships = projected["analysis_result"]["sii_evidence"]["relationship_changes"]

    assert "sii_result" not in projected
    assert any(
        set(item.get("columns", [])) == {"flow", "pressure"}
        and item.get("change_type") in {"weakened", "missing"}
        for item in relationships
    )


def _canonical_result() -> dict:
    return {
        "job_id": "transport-1",
        "run_id": "transport-1",
        "upload_id": "transport-1",
        "filename": "transport.csv",
        "row_count": 120,
        "column_count": 3,
        "columns": ["timestamp", "flow", "pressure"],
        "completed_at": "2026-08-15T12:00:00Z",
        "data_quality": {"readiness": "ready", "warnings": []},
        "timestamp_profile": {
            "first_timestamp": "2026-08-15T10:00:00Z",
            "last_timestamp": "2026-08-15T12:00:00Z",
        },
        "baseline_analysis": {},
        "relationship_model": {},
        "operator_report": {},
        "traceability": {
            "provenance": {
                "schema_version": "analysis-provenance.v1",
                "analysis_run_id": "transport-1",
                "upload_id": "transport-1",
                "dataset_id": "dataset-1",
                "input_hash": "input-hash",
                "baseline_id": "baseline-1",
                "baseline_dataset_id": "baseline-dataset-1",
                "baseline_version": 3,
                "baseline_hash": "baseline-hash",
                "engine_name": "neraium_sii",
                "engine_version": "v2",
                "configuration_hash": "config-hash",
                "result_hash": "result-hash",
            }
        },
        "sii_result": {
            "engine": {"name": "neraium_sii", "version": "v2"},
            "status": "limited",
            "relationship_graph": {
                "status": "complete",
                "changed_edges": [
                    {
                        "id": "relationship:flow:pressure",
                        "source": "metric:flow",
                        "target": "metric:pressure",
                        "columns": ["flow", "pressure"],
                        "change_type": "weakened",
                        "baseline_correlation": 0.91,
                        "current_correlation": 0.42,
                        "correlation_delta": 0.49,
                        "confidence": 0.88,
                        "evidence_refs": [
                            {
                                "evidence_id": "relationship-window-1",
                                "source_reference": "relationship_graph.changed_edges",
                            }
                        ],
                    }
                ],
            },
            "operating_modes": {
                "status": "complete",
                "baseline_mode": "running",
                "recent_mode": "running",
                "match": "strong",
                "confidence": "high",
                "mode_conditioned_baseline": {
                    "status": "complete",
                    "used_global_fallback": False,
                    "selection_confidence": 0.86,
                    "selection_confidence_level": "high",
                    "selected_operating_mode": {
                        "mode_id": "running",
                        "features": {"stage": "loaded"},
                    },
                    "selection": {
                        "selected_baseline_rows": 52,
                        "recent_rows": 36,
                        "selected_historical_indices": list(range(52)),
                    },
                },
            },
            "persistence_analysis": {
                "status": "complete",
                "method": "phase_1_views_with_phase_2_elapsed_time_persistence",
                "fixed_row_support": {
                    "status": "persistent",
                    "persistent_columns": ["pressure"],
                    "details": [
                        {
                            "column": "pressure",
                            "support_percent": 82.0,
                            "persistent": True,
                        }
                    ],
                },
                "adaptive_persistence": {
                    "status": "complete",
                    "persistence_basis": "elapsed_time",
                    "elapsed_time_available": True,
                    "persistent_columns": ["pressure"],
                    "actual_persistence": {
                        "persistent_columns": ["pressure"],
                        "source": "elapsed_time_support",
                    },
                },
            },
            "data_conditions": {
                "data_quality": {
                    "status": "limited",
                    "readiness": "degraded_ready",
                    "analysis_gate_state": "DEGRADED_READY",
                    "data_confidence": {"rating": "limited"},
                    "warnings": ["Missing samples reduce confidence."],
                },
                "sensor_health": {
                    "status": "limited",
                    "signals": [
                        {
                            "signal": "pressure",
                            "health": "suspect",
                            "conditions": ["stuck_value_review"],
                        }
                    ],
                },
            },
            "uncertainty": {
                "status": "limited",
                "data_confidence": {"rating": "limited"},
                "module_failures": [],
                "limitations": ["Missing samples reduce confidence."],
                "components": {
                    "relationship_uncertainty": {
                        "status": "limited",
                        "not_probability": True,
                        "source_references": ["relationship_graph.edges"],
                        "traceable_metrics": {"direction_ambiguous_edge_count": 1},
                        "limitations": ["relationship_direction_not_established"],
                    }
                },
            },
            "evidence_fusion": {
                "observations": [
                    {
                        "observation_id": "engineering_observation:pump-prior",
                        "observation": "Configured prose is intentionally not transported.",
                        "behavioral_status": "not_consistent_with_configured_expectation",
                        "contributing_analytical_modules": [
                            "physics_reasoning",
                            "relationship_graph",
                        ],
                        "evaluated_engineering_priors": ["pump-prior"],
                        "human_review_required": True,
                        "causal_interpretation_provided": False,
                        "maintenance_recommendation_provided": False,
                        "processing_trace": {
                            "prior_id": "pump-prior",
                            "prior_status": "contradicted",
                            "supporting_evidence_ids": ["physics:pump-prior:1"],
                            "limiting_evidence_ids": ["module:uncertainty"],
                            "contradictory_evidence_ids": [],
                        },
                    }
                ]
            },
            "behavioral_model": {
                "status": "complete",
                "model_id": "tenant-derived-model-id",
                "identity": {"organization_id": "do-not-transport"},
                "behavioral_identity": {"workspace_id": "do-not-transport"},
                "model_store": {"backend": "do-not-transport"},
                "limitations": [],
            },
            "behavioral_evolution": {
                "status": "complete",
                "relationship_changes": [
                    {
                        "relationship_id": "relationship:flow:pressure",
                        "change_type": "weakened",
                        "classification": "persistent_behavioral_change",
                        "persistent_across_references": True,
                        "source_evidence": {"model_id": "do-not-transport"},
                    }
                ],
                "limitations": [
                    "Evolution evidence does not establish future failure."
                ],
            },
            "propagation_analysis": {
                "status": "complete",
                "activated_nodes": ["flow", "pressure"],
                "candidate_paths": [
                    {
                        "path_id": "candidate_path:flow->pressure",
                        "nodes": ["flow", "pressure"],
                        "edges": ["relationship:flow:pressure"],
                        "compatibility": 0.81,
                        "not_probability": True,
                        "causal_claim": False,
                        "path_evidence": [{"model_id": "do-not-transport"}],
                    }
                ],
                "uncertainty": {
                    "not_probability": True,
                    "cause_selected": False,
                },
                "limitations": [],
                "reasoning_trace": {
                    "causal_proof_claimed": False,
                    "root_cause_selected": False,
                },
            },
        },
    }


def test_canonical_sii_evidence_survives_analysis_and_transport_projection() -> None:
    result = _canonical_result()
    result["analysis_result"] = build_analysis_result(result)

    projected = project_result_for_transport(result)

    assert projected is not None
    assert "sii_result" not in projected
    evidence = projected["analysis_result"]["sii_evidence"]
    assert evidence["source"] == "sii_result"
    assert evidence["source_path"] == "sii_result"
    assert evidence["authority"] == {
        "scope": "canonical_engine_evidence",
        "finding_classification": False,
    }
    assert evidence["relationship_changes"][0] == {
        "id": "relationship:flow:pressure",
        "source": "metric:flow",
        "target": "metric:pressure",
        "columns": ["flow", "pressure"],
        "change_type": "weakened",
        "baseline_correlation": 0.91,
        "current_correlation": 0.42,
        "correlation_delta": 0.49,
        "confidence": 0.88,
        "evidence_refs": [
            {
                "evidence_id": "relationship-window-1",
                "source_reference": "relationship_graph.changed_edges",
            }
        ],
    }
    assert evidence["operating_context"]["recent_mode"] == "running"
    assert evidence["operating_context"]["mode_conditioned_baseline"]["selection"] == {
        "selected_baseline_rows": 52,
        "recent_rows": 36,
    }
    assert evidence["persistence"]["adaptive_persistence"]["actual_persistence"] == {
        "persistent_columns": ["pressure"],
        "source": "elapsed_time_support",
    }
    assert evidence["uncertainty"]["limitations"] == [
        "Missing samples reduce confidence."
    ]
    assert evidence["data_quality"]["analysis_gate_state"] == "DEGRADED_READY"
    assert evidence["sensor_health"]["signals"][0]["health"] == "suspect"
    observation = evidence["configured_prior_observations"][0]
    assert observation["prior_id"] == "pump-prior"
    assert observation["prior_status"] == "contradicted"
    assert "observation" not in observation
    assert evidence["phase_4"]["available"] is True
    assert evidence["phase_4"]["propagation"]["candidate_paths"][0]["causal_claim"] is False
    assert evidence["provenance"]["configuration_hash"] == "config-hash"
    assert evidence["provenance"]["result_hash"] == "result-hash"
    serialized = repr(evidence)
    assert "tenant-derived-model-id" not in serialized
    assert "do-not-transport" not in serialized
    assert "model_store" not in serialized
    assert "behavioral_identity" not in serialized


def test_transport_upgrades_an_existing_analysis_contract_before_stripping_sii() -> None:
    result = _canonical_result()
    existing = build_analysis_result({key: value for key, value in result.items() if key != "sii_result"})
    assert existing["sii_evidence"]["status"] == "unavailable"
    existing.pop("sii_evidence")
    result["analysis_result"] = existing

    projected = project_result_for_transport(result)

    assert "sii_result" not in projected
    assert projected["analysis_result"]["sii_evidence"]["relationship_changes"]
    assert projected["analysis_result"]["sii_evidence"]["provenance"]["input_hash"] == "input-hash"


def test_unavailable_phase4_and_missing_sii_remain_explicit() -> None:
    limited = _canonical_result()
    sii = limited["sii_result"]
    sii["behavioral_model"] = {
        "status": "limited",
        "reason": "authenticated_workspace_identity_unavailable",
        "identity": {"workspace_id": "hidden"},
    }
    sii["behavioral_evolution"] = {
        "status": "limited",
        "reason": "active_behavioral_model_unavailable",
        "relationship_changes": [],
    }
    sii["propagation_analysis"] = {
        "status": "limited",
        "reason": "no_fully_supported_candidate_propagation_path",
        "candidate_paths": [],
    }

    limited_evidence = build_analysis_result(limited)["sii_evidence"]
    missing = build_analysis_result({"job_id": "missing-sii"})["sii_evidence"]

    assert limited_evidence["phase_4"]["available"] is False
    assert limited_evidence["phase_4"]["status"] == "limited"
    assert "active_behavioral_model_unavailable" in limited_evidence["phase_4"]["limitations"]
    assert "hidden" not in repr(limited_evidence)
    assert missing["status"] == "unavailable"
    assert missing["relationship_changes"] == []
    assert missing["phase_4"] == {
        "status": "unavailable",
        "available": False,
        "limitations": [],
        "behavioral_evolution": {},
        "propagation": {},
    }


def test_durable_evidence_record_and_api_model_preserve_bounded_projection() -> None:
    result = _canonical_result()
    result["analysis_result"] = build_analysis_result(result)
    record = build_evidence_record_from_result(
        run_id="transport-1",
        filename="transport.csv",
        source_type="csv_upload",
        result=result,
        created_at="2026-08-15T10:00:00Z",
        completed_at="2026-08-15T12:00:00Z",
        status="completed",
        initiated_by="operator",
    )

    assert record["sii_evidence"] == result["analysis_result"]["sii_evidence"]
    assert record["phase_2_supporting_evidence"]["relationship_graph"]
    response = EvidenceRunResponse.model_validate(record).model_dump()
    assert response["sii_evidence"] == record["sii_evidence"]
    assert response["phase_2_supporting_evidence"] == record["phase_2_supporting_evidence"]
    assert response["sii_evidence"]["provenance"]["input_hash"] == "input-hash"
