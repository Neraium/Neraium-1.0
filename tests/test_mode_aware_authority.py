from app.services.mode_aware_authority import apply_mode_aware_suppression


def _inputs() -> dict:
    return {
        "engine_result": {
            "overall_result": "needs_review",
            "signals": [{"column": "flow"}],
            "evidence": [{"column": "flow", "window": "recent"}],
        },
        "relationship_model": {
            "top_relationship_changes": [{"source": "flow", "target": "pump_speed"}],
        },
        "mode_conditioned": {
            "status": "complete",
            "used_global_fallback": False,
            "selection_confidence": 0.91,
        },
        "relationship_graph": {
            "status": "complete",
            "edge_basis": "mode_conditioned_relationships",
            "changed_edges": [],
        },
        "adaptive_persistence": {"status": "complete", "persistent_columns": []},
        "multiscale_analysis": {
            "cross_scale_interpretation": {
                "status": "complete",
                "classification": "stable_across_scales",
            }
        },
        "enabled": True,
    }


def test_corroborated_same_mode_stability_can_only_suppress() -> None:
    result = apply_mode_aware_suppression(**_inputs())

    assert result["decision"]["applied"] is True
    assert result["decision"]["authority"] == "suppression_only"
    assert result["engine_result"]["overall_result"] == "complete"
    assert result["engine_result"]["signals"] == []
    assert result["relationship_model"]["top_relationship_changes"] == []
    assert result["relationship_model"]["suppressed_top_relationship_changes"]


def test_changed_mode_conditioned_relationship_retains_candidate() -> None:
    inputs = _inputs()
    inputs["relationship_graph"]["changed_edges"] = [{"source": "flow", "target": "pump_speed"}]

    result = apply_mode_aware_suppression(**inputs)

    assert result["decision"]["applied"] is False
    assert result["engine_result"]["overall_result"] == "needs_review"
    assert result["engine_result"]["signals"]


def test_policy_never_creates_a_finding() -> None:
    inputs = _inputs()
    inputs["engine_result"] = {"overall_result": "complete", "signals": [], "evidence": []}

    result = apply_mode_aware_suppression(**inputs)

    assert result["decision"]["applied"] is False
    assert result["engine_result"]["overall_result"] == "complete"
    assert result["engine_result"]["signals"] == []


def test_incomplete_corroboration_retains_candidate() -> None:
    inputs = _inputs()
    inputs["multiscale_analysis"] = {"cross_scale_interpretation": {"status": "limited"}}

    result = apply_mode_aware_suppression(**inputs)

    assert result["decision"]["applied"] is False
    assert "multiscale_stability_not_established" in result["decision"]["blockers"]
