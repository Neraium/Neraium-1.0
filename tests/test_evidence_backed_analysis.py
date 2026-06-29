from app.services.upload_jobs import process_csv_content


def evidence_fixture_csv() -> bytes:
    baseline_rows = [
        f"2026-05-01T08:{index:02d}:00Z,{100 + index},{200 + 2 * index},{50 + (index % 3) * 0.1:.1f}"
        for index in range(21)
    ]
    recent_rows = [
        f"2026-05-01T09:{index:02d}:00Z,{140 + index},{170 - 3 * index},{51 + (index % 2) * 0.1:.1f}"
        for index in range(9)
    ]
    content = "timestamp,pump_power,flow_rate,differential_pressure\n" + "\n".join(baseline_rows + recent_rows)
    return content.encode("utf-8")


def test_uploaded_csv_analysis_returns_evidence_backed_outputs() -> None:
    result = process_csv_content(
        filename="evidence-backed-analysis.csv",
        content=evidence_fixture_csv(),
        job_id="evidencebackedanalysis001",
    )

    analysis = result["analysis_explanation"]
    insights = analysis["insights"]
    assert insights

    for insight in insights:
        assert insight["title"]
        assert insight["severity"]
        assert 0 < insight["confidence_score"] <= 1
        assert insight["affected_systems"]
        assert insight["what_changed"]
        assert insight["why_neraium_thinks_it_happened"]
        assert insight["possible_operational_consequence"]
        assert insight["recommended_operator_check"]
        assert insight["evidence_summary"]
        assert insight["evidence_items"]
        assert insight["source_time_ranges"]
        assert insight["upload_id"] == result["upload_id"]
        assert insight["analysis_id"] == result["run_id"]

    placeholder_titles = {
        "structural drift observed",
        "persistent structural drift observed",
        "placeholder",
    }
    assert all(insight["title"].lower() not in placeholder_titles for insight in insights)

    first = insights[0]
    assert first["contributing_relationships"]
    assert first["contributing_metrics"]
    evidence_item = first["evidence_items"][0]
    assert {"pump_power", "flow_rate"}.issubset(set(evidence_item["source_columns"]))
    assert evidence_item["calculated_delta"] is not None
    assert evidence_item["source_upload_id"] == result["upload_id"]

    relationship = analysis["relationships"][0]
    assert relationship["strength"] is not None
    assert relationship["baseline_strength"] is not None
    assert relationship["current_strength"] is not None
    assert relationship["change_percentage"] is not None
    assert relationship["confidence_score"] > 0
    assert relationship["time_window"]

    graph = analysis["relationship_graph"]
    assert graph["nodes"]
    assert graph["edges"]
    assert graph["changed_edges"]
    edge = graph["changed_edges"][0]
    assert edge["relationship_type"]
    assert edge["strength"] is not None
    assert edge["baseline_strength"] is not None
    assert edge["current_strength"] is not None
    assert edge["confidence"] > 0
    assert edge["supporting_metric_pairs"]
    assert edge["time_window"]

    fingerprint = analysis["fingerprint"]
    assert fingerprint["baseline_summary"]
    assert fingerprint["current_behavior_summary"]
    assert fingerprint["drift_status"] in {"changed", "stable"}
    assert fingerprint["largest_deviations"]
    assert fingerprint["confidence_score"] > 0
    assert fingerprint["confidence_rationale"]
    assert fingerprint["evidence"]
