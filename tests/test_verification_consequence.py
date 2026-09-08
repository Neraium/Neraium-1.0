"""Scoped production smoke fixture and real replay/API persistence proof."""
from __future__ import annotations

import json
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest

from app.models.api_models import EvidenceRunResponse
from app.services import runtime_db, upload_state_repository as repository
from app.services.analysis_provenance import canonical_digest, result_digest
from app.services.dataset_scope import dataset_scope_context
from app.services.upload_pipeline import _empty_optional_replay, _inline_replay_generation_enabled
from datasets.verification_consequence import (
    MARKERS, RUN_ID, SCOPE, WORKSPACE_ID, build_fixture, fixture_paths, seed_fixture, verify_responses,
)
from test_upload_queue_scope_routing import _FakeS3Client, _configure_shared_runtime


def forbid(*args, **kwargs):
    raise AssertionError("Reading a persisted fixture must not recalculate or rewrite artifacts")


@pytest.fixture
def smoke_headers(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.neraium.com")
    monkeypatch.setenv("NERAIUM_API_TOKEN", "synthetic-test-token")
    return {"Authorization": "Bearer synthetic-test-token", "X-Neraium-Workspace-Id": WORKSPACE_ID}


@pytest.mark.parametrize("storage", ["local", "shared"])
def test_fixture_replay_persistence_apis_and_frontend_projection(client, monkeypatch, smoke_headers, storage, tmp_path):
    shared = _FakeS3Client()
    if storage == "shared":
        _configure_shared_runtime(monkeypatch, shared)
    manifest = seed_fixture()
    with dataset_scope_context(SCOPE):
        stored = repository.read_upload_result_by_job_id(RUN_ID)
        evidence = runtime_db.read_evidence_run_db(RUN_ID)
    artifact_hash = canonical_digest(stored)
    evidence_hash = canonical_digest(evidence)
    shared_before = deepcopy(shared.objects)
    if storage == "shared":
        key = ("shared-upload-state", f"upload-state/scopes/{SCOPE.storage_id}/upload_result_{RUN_ID}.json")
        assert json.loads(shared.objects[key]) == stored
        repository.configure_runtime_dir(tmp_path / "fresh-api-upload-state")
    assert artifact_hash == manifest["artifact_hash"]
    assert stored["verification"] == MARKERS
    assert stored["source_type"] == "verification_fixture"
    assert stored["replay_timeline"]["timeline"][0]["timestamp"] == "2026-09-01T00:00:00+00:00"
    assert stored["replay_timeline"]["timeline"][-1]["timestamp"] == "2026-09-01T06:00:00+00:00"
    # Drop in-process upload state. Reads must recover persisted data.
    repository.runtime_state().latest_upload_cache.clear()
    repository.runtime_state().jobs.clear()
    for target in (
        "app.services.measurable_consequence.quantify_consequence",
        "app.engine.sii.expected_behavior.evaluate_expected_behavior",
        "datasets.verification_consequence.evaluate_expected_behavior",
        "app.services.upload_jobs.process_csv_file",
        "app.services.upload_replay.build_replay",
        "app.services.upload_state_repository.write_upload_result",
        "app.services.evidence_store.upsert_evidence_run",
        "app.services.runtime_db.upsert_evidence_run_db",
    ):
        monkeypatch.setattr(target, forbid)
    # Reseeding is a read-only no-op, including with analytical calls forbidden.
    assert seed_fixture() == manifest
    for _ in range(2):
        proof = verify_responses(lambda path: client.get(path, headers=smoke_headers))
    assert proof["consequence"]["support_level"] == "high"
    assert proof["consequence"]["direction"] == "above_expected"
    assert proof["consequence"]["observation_count"] == 7
    assert proof["consequence"]["contributing_interval_count"] == 6
    assert proof["consequence"]["skipped_interval_count"] == 0
    with dataset_scope_context(SCOPE):
        assert canonical_digest(repository.read_upload_result_by_job_id(RUN_ID)) == artifact_hash
        assert canonical_digest(runtime_db.read_evidence_run_db(RUN_ID)) == evidence_hash
    # Execute the shipped frontend selector against the actual HTTP consequence.
    script = Path(__file__).parents[1] / "scripts/verify-consequence-projection.mjs"
    completed = subprocess.run(["node", str(script)], input=json.dumps(proof), text=True, capture_output=True)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["frontend_projection_matches"] is True
    assert shared.objects == shared_before


def test_fixture_is_hidden_from_normal_scopes_and_latest_views(client, smoke_headers):
    seed_fixture()
    for headers in (
        {"Authorization": smoke_headers["Authorization"]},
        {"X-Neraium-Workspace-Id": WORKSPACE_ID},
    ):
        for path in fixture_paths().values():
            assert client.get(path, headers=headers).status_code in (401, 404)
    # Normal authenticated service lists and latest remain empty.
    headers = {"Authorization": smoke_headers["Authorization"]}
    for path in ("/api/findings", "/api/evidence/runs", "/api/data/latest-upload"):
        response = client.get(path, headers=headers)
        assert response.status_code == 200
        assert RUN_ID not in response.text
    for path in ("/api/data/latest-upload", "/api/replay/timeline"):
        response = client.get(path, headers=smoke_headers)
        assert response.status_code == 200
        assert RUN_ID not in response.text


def test_fixture_is_deterministic_and_does_not_seed_on_build():
    first = build_fixture()
    assert first == build_fixture()
    with dataset_scope_context(SCOPE):
        assert repository.read_upload_result_by_job_id(RUN_ID) is None
        assert runtime_db.read_evidence_run_db(RUN_ID) is None
    assert first["analysis_result"]["conditions"][0]["measurable_consequence"]["cumulative_amount"] == 3600


def test_seed_refuses_existing_unrelated_payload():
    with dataset_scope_context(SCOPE):
        repository.write_upload_result(RUN_ID, {"run_id": RUN_ID, "keep": "untouched"})
        before = repository.read_upload_result_by_job_id(RUN_ID)
    with pytest.raises(ValueError, match="refusing to overwrite"):
        seed_fixture()
    with dataset_scope_context(SCOPE):
        assert repository.read_upload_result_by_job_id(RUN_ID) == before


def test_customer_cannot_select_service_fixture_scope(client, monkeypatch, smoke_headers):
    seed_fixture()
    monkeypatch.setattr("app.core.security.get_user_by_session", lambda _: {
        "email": "customer@example.test", "role": "operator",
    })
    for path in fixture_paths().values():
        assert client.get(path, headers=smoke_headers).status_code == 404


def test_historical_driver_field_parses_but_is_never_serialized():
    parsed = EvidenceRunResponse.model_validate({
        "run_id": "historical-driver-schema", "source_type": "csv_upload",
        "created_at": "2026-09-01T00:00:00Z", "status": "completed",
        "primary_drivers": ["HISTORICAL_ONLY"],
    })
    assert parsed.primary_drivers == ["HISTORICAL_ONLY"]
    assert "primary_drivers" not in parsed.model_dump()
    assert "HISTORICAL_ONLY" not in parsed.model_dump_json()


@pytest.mark.parametrize("path", ["/api/data/replay/", "/api/replay/"])
def test_production_disabled_replay_is_genuinely_missing(client, monkeypatch, path):
    # Exact persisted replay shape in both post-deployment historical probes.
    monkeypatch.delenv("PYTEST_CURRENT_TEST")
    monkeypatch.delenv("NERAIUM_INLINE_REPLAY_GENERATION", raising=False)
    monkeypatch.setenv("NERAIUM_DISABLE_RUNTIME_DB_LATEST", "1")
    assert _inline_replay_generation_enabled() is False
    job_id = "historical-inline-disabled"
    historical = {"job_id": job_id, "replay_timeline": _empty_optional_replay(job_id, "inline_replay_disabled")}
    repository.write_upload_result(job_id, historical)
    before = repository.read_upload_result_by_job_id(job_id)
    assert client.get(path + job_id).status_code == 404
    assert client.get(path + "truly-missing").status_code == 404
    assert client.get(f"/api/data/intake/{job_id}/result").status_code == 200
    assert repository.read_upload_result_by_job_id(job_id) == before


@pytest.mark.parametrize("nested", [False, True])
@pytest.mark.parametrize("route", ["data", "alias", "timeline", "frame", "range"])
def test_valid_historical_replay_projects_boundary_without_rewriting(client, nested, route):
    job_id = "historical-valid-replay"
    frame = {
        "timestamp": "2026-09-01T00:00:00Z", "measurement": 110,
        "cause": "RETIRED", "driver_attribution": {"primary_driver": "RETIRED"},
        "diagnosis": "RETIRED", "attribution_confidence": "RETIRED",
    }
    replay = {"timeline": [frame], "meta": {"frame_count": 1}}
    source = {"job_id": job_id}
    source["sii_intelligence" if nested else "replay_timeline"] = {"replay_timeline": replay} if nested else replay
    repository.write_latest_upload_result(job_id, source)
    before = deepcopy(repository.read_upload_result_by_job_id(job_id))
    paths = {
        "data": f"/api/data/replay/{job_id}", "alias": f"/api/replay/{job_id}",
        "timeline": "/api/replay/timeline",
        "frame": "/api/replay/frame/2026-09-01T00:00:00Z",
        "range": "/api/replay/range?start_timestamp=2026-09-01T00:00:00Z&end_timestamp=2026-09-01T00:00:00Z",
    }
    response = client.get(paths[route])
    assert response.status_code == 200
    assert "RETIRED" not in response.text
    assert "measurement" in response.text
    after = repository.read_upload_result_by_job_id(job_id)
    assert after == before
    assert result_digest(after) == result_digest(before)
