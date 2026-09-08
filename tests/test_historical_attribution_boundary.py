from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from app.models.api_models import EvidenceRunResponse
from app.routers import data as data_router
from app.services import evidence_store, runtime_db, upload_state_repository
from app.services.analysis_provenance import result_digest
from app.services.finding_workflow import evidence_finding_id
from app.services.product_evidence_contract import product_evidence


def historical_result():
    consequence = json.loads(
        (Path(__file__).parents[1] / "frontend/tests/fixtures/measurable-consequence.json").read_text()
    )
    return {
        "job_id": "historical-attribution",
        "sii_intelligence": {
            "attribution_confidence": "LEGACY_ATTRIBUTION",
            "rooms": [{"attribution_confidence": "LEGACY_ROOM_ATTRIBUTION"}],
            "instability_index": {
                "score": 0.4,
                "components": {"causal_evidence": 0.5, "relationship_degradation": 0.3},
            },
        },
        "relationships": [{"id": "water:load", "correlation_delta": 0.7}],
        "measurable_consequence": consequence,
        "provenance": {"result_hash": "historical-result-hash", "model_version": "v1"},
    }


def assert_projected(projected, original):
    intelligence = projected["sii_intelligence"]
    assert "attribution_confidence" not in intelligence
    assert "attribution_confidence" not in intelligence["rooms"][0]
    assert intelligence["instability_index"] == {
        "score": 0.4, "components": {"relationship_degradation": 0.3},
    }
    for field in ("relationships", "measurable_consequence", "provenance"):
        assert projected[field] == original[field]


@pytest.mark.parametrize("key", [
    "attribution_confidence", "attributionConfidence", "causal_evidence", "causalEvidence",
    "driver_attribution", "driverAttribution", "cause_attribution", "causeAttribution",
    "projected_time_to_failure", "projected_time_to_failure_hours", "failure_probability",
    "probability_of_failure", "remaining_useful_life", "RUL",
])
def test_product_boundary_omits_legacy_and_renamed_attribution_objects(key):
    original = {"nested": [{key: {"conclusion": "LEGACY_ATTRIBUTION"}, "correlation_delta": 0.7}]}
    saved = deepcopy(original)
    assert product_evidence(original) == {"nested": [{"correlation_delta": 0.7}]}
    assert original == saved


@pytest.mark.parametrize("route", ["intake", "latest", "replay"])
def test_historical_result_routes_project_without_rewriting_storage(client, monkeypatch, route):
    original = historical_result()
    job_id = original["job_id"]
    upload_state_repository.write_upload_result(job_id, original)
    stored = upload_state_repository.read_upload_result_by_job_id(job_id)
    stored_hash = result_digest(stored)
    assert stored["sii_intelligence"] == original["sii_intelligence"]

    if route == "latest":
        monkeypatch.setattr(data_router, "resolve_latest_upload_payload", lambda **_: {"latest_result": stored})
        monkeypatch.setattr(data_router, "read_latest_candidate", lambda: None)
        monkeypatch.setattr(data_router, "read_active_behavioral_model", lambda: None)
        path, field = "/api/data/latest-upload", "latest_result"
    elif route == "replay":
        monkeypatch.setattr(data_router, "resolve_upload_artifacts", lambda _: {"replay": {"timeline": [stored]}})
        path, field = f"/api/data/replay/{job_id}", "timeline"
    else:
        path, field = f"/api/data/intake/{job_id}/result", "result"

    for _ in range(2):
        response = client.get(path)
        assert response.status_code == 200
        projected = response.json()[field]
        assert_projected(projected[0] if route == "replay" else projected, original)
    reloaded = upload_state_repository.read_upload_result_by_job_id(job_id)
    assert reloaded == stored
    assert result_digest(reloaded) == stored_hash


def test_historical_evidence_findings_and_exports_preserve_storage_and_consequence(client):
    finding = {**historical_result(), "condition_id": "finding", "headline": "Relationship changed"}
    record = {
        "run_id": "historical-attribution", "source_type": "csv_upload", "status": "completed",
        "created_at": "2026-09-05T00:00:00Z", "result_hash": "historical-result-hash",
        "condition": finding,
        "finding_identity_snapshot": [{"source_finding_id": "finding", "finding": finding}],
        "drift_metrics": finding["sii_intelligence"]["instability_index"]["components"],
    }
    evidence_store.upsert_evidence_run(record)
    stored = runtime_db.read_evidence_run_db(record["run_id"])
    stored_hash = result_digest(stored)
    parsed = EvidenceRunResponse.model_validate(stored)
    assert parsed.condition["sii_intelligence"] == finding["sii_intelligence"]

    for path in (
        f"/api/evidence/runs/{record['run_id']}",
        f"/api/evidence/export/{record['run_id']}?format=json",
    ):
        response = client.get(path)
        assert response.status_code == 200
        assert_projected(response.json()["condition"], finding)
        assert response.json()["result_hash"] == record["result_hash"]
    response = client.get(f"/api/findings/{evidence_finding_id(record['run_id'], 'finding')}")
    assert response.status_code == 200
    assert_projected(response.json()["evidence"]["finding"], finding)

    for formatter in (
        evidence_store.build_evidence_export_payload,
        evidence_store.build_evidence_export,
        evidence_store.build_evidence_export_csv,
        evidence_store.build_evidence_package_payload,
    ):
        exported = formatter(stored)
        assert "attribution_confidence" not in str(exported)
        assert "causal_evidence" not in str(exported)
        assert "LEGACY_" not in str(exported)
    package = evidence_store.build_evidence_package_payload(stored)
    assert package["relationship_changes"] == {"relationship_degradation": 0.3}
    reloaded = runtime_db.read_evidence_run_db(record["run_id"])
    assert reloaded == stored
    assert result_digest(reloaded) == stored_hash


def test_facility_intelligence_omits_legacy_predictions_without_mutating_evidence(monkeypatch):
    from app.routers import facility
    original = {
        "sii_intelligence": {
            "source": "uploaded", "rooms": [{"projected_time_to_failure_hours": 8}],
            "failure_probability": 0.9,
            "measurable_consequence": {"status": "not_quantifiable"},
            "provenance": {"result_hash": "original"},
        },
    }
    before = deepcopy(original)
    monkeypatch.setattr(facility, "has_active_session_artifact", lambda _: True)
    projected = facility.resolve_uploaded_intelligence(original, include_persisted=True)
    assert projected == {
        "source": "uploaded", "rooms": [{}],
        "measurable_consequence": {"status": "not_quantifiable"},
        "provenance": {"result_hash": "original"},
    }
    assert original == before
