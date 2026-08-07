from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.services import historical_ingestion, upload_state_repository
from app.services.dataset_scope import build_dataset_scope, set_current_dataset_scope
from app.services.historical_ingestion import (
    apply_review,
    build_historical_ingestion,
    canonical_rows_page,
    read_ingestion_record,
)
from app.services.upload_state_repository import runtime_state
from app.services.upload_jobs import process_csv_content


FIXTURES = Path(__file__).resolve().parents[1] / "test-fixtures" / "historical-ingestion"


def _signal(record: dict, source_column: str) -> dict:
    return next(item for item in record["signal_profiles"] if item["source_column"] == source_column)


def test_clean_historian_is_deterministic_and_preserves_immutable_raw_source(tmp_path: Path) -> None:
    source = tmp_path / "historian.csv"
    original = (FIXTURES / "clean_historian.csv").read_bytes()
    source.write_bytes(original)

    first, first_handoff = build_historical_ingestion(
        source,
        dataset_id="clean-a",
        filename="historian.csv",
    )
    second, second_handoff = build_historical_ingestion(
        source,
        dataset_id="clean-b",
        filename="historian.csv",
    )

    assert first["dataset_identity"] == second["dataset_identity"]
    assert first_handoff["rows"] == second_handoff["rows"]
    assert first["raw_source"]["sha256"] == hashlib.sha256(original).hexdigest()
    assert first["raw_source"]["immutable"] is True
    assert first["canonical_dataset"]["original_values_preserved"] is True
    assert first["canonical_dataset"]["major_gaps_interpolated"] is False
    assert first["readiness"]["outcome"] == "ready"
    assert first["configuration_profile"]["status"] == "no_configuration_concern_detected"
    assert "trust_score" not in first
    assert len(first["trust_dimensions"]) == 8

    artifact_id = first["raw_source"]["storage"]["artifact_id"]
    raw_artifact = (
        runtime_state().runtime_dir
        / "historical_ingestion"
        / "scopes"
        / build_dataset_scope(user_id="anonymous").storage_id
        / "raw"
        / f"{artifact_id}.source"
    )
    source.write_text("changed after processing", encoding="utf-8")
    assert raw_artifact.read_bytes() == original


def test_shared_raw_artifact_uses_atomic_create_without_overwrite(monkeypatch, tmp_path: Path) -> None:
    class AlreadyExists(Exception):
        response = {
            "Error": {"Code": "PreconditionFailed"},
            "ResponseMetadata": {"HTTPStatusCode": 412},
        }

    class ConditionalObjectStore:
        def __init__(self):
            self.objects: dict[str, bytes] = {}

        def put_object(self, *, Key, Body, IfNoneMatch, **_kwargs):
            assert IfNoneMatch == "*"
            if Key in self.objects:
                raise AlreadyExists()
            self.objects[Key] = Body.read()

    store = ConditionalObjectStore()
    monkeypatch.setattr(upload_state_repository, "_get_s3_client", lambda: store)
    monkeypatch.setattr(upload_state_repository, "_upload_state_bucket", lambda: "trust-artifacts")
    monkeypatch.setattr(upload_state_repository, "_upload_state_prefix", lambda: "neraium")
    source = tmp_path / "raw.bin"
    source.write_bytes(b"immutable source bytes")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()

    first = upload_state_repository.persist_immutable_derived_artifact(
        "dataset-1", source, artifact_id=digest, artifact_kind="raw"
    )
    upload_state_repository.persist_immutable_derived_artifact(
        "dataset-1", source, artifact_id=digest, artifact_kind="raw"
    )
    source.write_bytes(b"attempted overwrite")
    with pytest.raises(ValueError, match="derived_artifact_digest_mismatch"):
        upload_state_repository.persist_immutable_derived_artifact(
            "dataset-1", source, artifact_id=digest, artifact_kind="raw"
        )

    assert first["backend"] == "s3_immutable"
    assert store.objects[first["object_key"]] == b"immutable source bytes"


def test_json_source_bytes_are_preserved_and_tabularization_is_provenanced(tmp_path: Path) -> None:
    source = tmp_path / "historian.json"
    original = (
        b'{\n  "rows": ['
        + b",".join(
            json.dumps(
                {
                    "Timestamp": f"2026-01-01T00:{index:02d}:00Z",
                    "Supply Temp F": 44 + index,
                    "Flow gpm": 100 + index,
                },
                separators=(",", ":"),
            ).encode("utf-8")
            for index in range(8)
        )
        + b"]\n}\n"
    )
    source.write_bytes(original)

    record, _ = build_historical_ingestion(
        source,
        dataset_id="json-source",
        filename="historian.json",
    )

    assert record["raw_source"]["sha256"] == hashlib.sha256(original).hexdigest()
    preparation = record["source_schema"]["source_preparation"]
    assert preparation["type"] == "json_to_tabular_csv"
    assert preparation["input_sha256"] == record["raw_source"]["sha256"]
    assert any(item["type"] == "json_to_tabular_csv" for item in record["provenance"]["transformations"])
    page = canonical_rows_page("json-source", limit=1)
    assert page["rows"][0]["source_values"]["Supply Temp F"] == "44"

    artifact_id = record["raw_source"]["storage"]["artifact_id"]
    raw_artifact = (
        runtime_state().runtime_dir
        / "historical_ingestion"
        / "scopes"
        / build_dataset_scope(user_id="anonymous").storage_id
        / "raw"
        / f"{artifact_id}.source"
    )
    assert raw_artifact.read_bytes() == original


def test_upload_pipeline_persists_complete_review_summary() -> None:
    result = process_csv_content(
        content=(FIXTURES / "clean_historian.csv").read_bytes(),
        filename="clean_historian.csv",
        job_id="trusted-upload-summary",
    )

    persisted = read_ingestion_record("trusted-upload-summary")
    assert persisted is not None
    assert persisted["summary"]["signal_counts"] == result["ingestion_trust"]["signal_counts"]
    assert persisted["summary"]["readiness"]["outcome"] == "ready"


def test_equipment_identifiers_with_digits_remain_source_headers(tmp_path: Path) -> None:
    source = tmp_path / "numeric-tags.csv"
    source.write_text(
        "Timestamp,AHU-001 Supply Temp F,Pump-002 Pressure psi\n"
        + "\n".join(
            f"2026-01-01T00:{index:02d}:00Z,{44 + index / 10},{72 + index / 10}"
            for index in range(8)
        )
        + "\n",
        encoding="utf-8",
    )

    record, _ = build_historical_ingestion(source, dataset_id="numeric-tags", filename=source.name)

    assert record["source_schema"]["header_present"] is True
    assert record["source_schema"]["candidate_row_count"] == 8
    assert [item["source_column"] for item in record["signal_profiles"]] == [
        "AHU-001 Supply Temp F",
        "Pump-002 Pressure psi",
    ]


def test_trusted_handoff_preserves_existing_operating_context_roles(tmp_path: Path) -> None:
    source = tmp_path / "context.csv"
    source.write_text(
        "Timestamp,Cooling Demand Tons,Valve Position %\n"
        + "\n".join(
            f"2026-01-01T00:{index:02d}:00Z,{200 + index},{40 + index}"
            for index in range(12)
        )
        + "\n",
        encoding="utf-8",
    )

    _, handoff = build_historical_ingestion(source, dataset_id="context-roles", filename=source.name)

    demand = handoff["telemetry_signal_catalog"]["Cooling Demand Tons"]
    valve = handoff["telemetry_signal_catalog"]["Valve Position %"]
    assert demand["canonical_role"] == "process_demand"
    assert demand["ingestion_semantic_role"] == "demand"
    assert valve["canonical_role"] == "control_command"
    assert valve["ingestion_semantic_role"] == "valve_position"


def test_correlation_is_advisory_and_never_invents_signal_identity(tmp_path: Path) -> None:
    source = tmp_path / "correlation-advisory.csv"
    source.write_text(
        "Timestamp,Supply Pressure psi,ZX_4007\n"
        + "\n".join(
            f"2026-01-01T00:{index:02d}:00Z,{30 + index},{60 + index * 2}"
            for index in range(20)
        )
        + "\n",
        encoding="utf-8",
    )

    record, _ = build_historical_ingestion(source, dataset_id="correlation-advisory", filename=source.name)
    unknown = _signal(record, "ZX_4007")

    assert unknown["proposed_canonical_role"] == "process_variable"
    assert unknown["mapping_state"] == "provisionally_mapped"
    pressure_alternative = next(item for item in unknown["alternatives"] if item.get("role") == "pressure")
    assert pressure_alternative["confidence"] == "advisory_only"
    assert "does not establish physical identity" in pressure_alternative["reason"]


def test_analysis_handoff_applies_deterministic_wide_dataset_cell_bound(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(historical_ingestion, "MAX_ANALYSIS_CELLS", 40)
    source = tmp_path / "wide-bound.csv"
    source.write_text(
        "Timestamp,Pressure psi,Flow gpm,Power kW\n"
        + "\n".join(
            f"2026-01-01T00:{index:02d}:00Z,{30 + index},{100 + index},{20 + index}"
            for index in range(20)
        )
        + "\n",
        encoding="utf-8",
    )

    record, handoff = build_historical_ingestion(source, dataset_id="wide-bound", filename=source.name, max_analysis_rows=20)

    assert record["canonical_dataset"]["analysis_cell_limit"] == 40
    assert record["canonical_dataset"]["analysis_population_rows"] == 20
    assert record["canonical_dataset"]["analysis_sample_rows"] == 10
    assert record["canonical_dataset"]["analysis_sample_stride"] == 2
    assert [row["__source_row_number"] for row in handoff["rows"]] == list(range(1, 21, 2))


def test_messy_export_profiles_timestamp_units_quality_duplicates_and_configuration() -> None:
    record, handoff = build_historical_ingestion(
        FIXTURES / "messy_industrial.csv",
        dataset_id="messy",
        filename="messy_industrial.csv",
    )

    timestamp = record["timestamp_profile"]
    assert timestamp["integrity"] == "medium"
    assert timestamp["duplicate_timestamp_count"] >= 1
    assert timestamp["out_of_order_count"] >= 1
    assert timestamp["large_gap_count"] >= 1
    assert timestamp["missing_count"] >= 1
    assert timestamp["irregular_sampling"] is True
    assert timestamp["effective_usable_coverage_seconds"] < timestamp["gross_coverage_seconds"]

    fahrenheit = _signal(record, "Supply Temp F")
    assert fahrenheit["proposed_canonical_role"] == "supply_temperature"
    assert fahrenheit["unit"]["inferred_unit"] == "degF"
    assert fahrenheit["unit"]["normalized_unit"] == "degC"
    assert fahrenheit["unit"]["conversion_formula"] == "(x - 32) * 5 / 9"
    assert handoff["rows"][0]["Supply Temp F"] == 6.111111111111

    pressure = _signal(record, "Header Pressure psi")
    assert pressure["unit"]["normalized_unit"] == "kPa"
    assert handoff["rows"][0]["Header Pressure psi"] == 517.1067969876

    fraction = _signal(record, "Damper Command fraction")
    assert fraction["unit"]["inferred_unit"] == "fraction"
    assert fraction["unit"]["normalized_unit"] == "%"
    assert handoff["rows"][1]["Damper Command fraction"] == 5.0

    stuck = _signal(record, "Stuck Sensor")
    assert stuck["quality"]["stuck"] is True
    assert stuck["quality"]["relationship_fitness"] == "insufficient"
    assert stuck["included_for_analysis"] is False

    duplicate = _signal(record, "Flow B")
    assert duplicate["mapping_state"] == "excluded"
    assert duplicate["duplicate_of"] == _signal(record, "Flow A")["canonical_signal_id"]
    assert any(item["type"] == "exact_duplicate" for item in record["duplicate_channels"])
    assert any(item["type"] == "nearly_duplicate" for item in record["duplicate_channels"])

    mixed = _signal(record, "Mixed Signal")
    assert mixed["quality"]["invalid_numeric_count"] == 2
    assert {item["value"] for item in mixed["quality"]["unexpected_string_states"]} == {"manual"}
    assert record["configuration_profile"]["status"] == "explicit_configuration_boundary"
    assert record["readiness"]["outcome"] == "ready_with_limitations"
    assert record["summary"]["signal_counts"]["need_review"] >= 1

    page = canonical_rows_page("messy", offset=0, limit=200)
    assert page["total"] == record["canonical_dataset"]["row_count"]
    assert any(not row["included_for_analysis"] for row in page["rows"])
    assert set(page["rows"][0]["source_values"]) == set(record["source_schema"]["columns"])
    assert page["rows"][0]["values"][duplicate["canonical_signal_id"]]["included_for_analysis"] is False
    missing_row = next(
        row for row in page["rows"]
        if row["values"].get(fahrenheit["canonical_signal_id"], {}).get("original_value") == ""
    )
    assert missing_row["values"][fahrenheit["canonical_signal_id"]]["normalized_value"] is None


def test_timestamp_ambiguity_and_timezone_edges_are_explicit() -> None:
    ambiguous, _ = build_historical_ingestion(
        FIXTURES / "multiple_timestamp_candidates.csv",
        dataset_id="multiple-time",
        filename="multiple_timestamp_candidates.csv",
    )
    assert ambiguous["timestamp_profile"]["integrity"] == "unavailable"
    assert ambiguous["timestamp_profile"]["selected_column"] is None
    assert len(ambiguous["timestamp_profile"]["candidates"]) == 2
    assert ambiguous["timestamp_profile"]["review_required"] is True
    assert "temporal_analysis" in ambiguous["readiness"]["blocked_methods"]

    dst, handoff = build_historical_ingestion(
        FIXTURES / "timezone_dst_edges.csv",
        dataset_id="dst",
        filename="timezone_dst_edges.csv",
    )
    assert dst["timestamp_profile"]["timezone_status"] == "explicit"
    assert dst["timestamp_profile"]["integrity"] == "high"
    assert handoff["rows"][0]["Timestamp"] == "2026-11-01T05:00:00Z"
    assert handoff["rows"][-1]["Timestamp"] == "2026-11-01T07:30:00Z"


def test_ambiguous_mapping_and_unit_review_rebuilds_canonical_revision(tmp_path: Path) -> None:
    source = tmp_path / "ambiguous.csv"
    source.write_text(
        "Timestamp,Supply Temp psi,Mystery Flow\n"
        + "\n".join(
            f"2026-01-01T00:{index:02d}:00Z,{10 + index},{100 + index}"
            for index in range(12)
        )
        + "\n",
        encoding="utf-8",
    )
    record, _ = build_historical_ingestion(
        source,
        dataset_id="reviewable",
        filename="ambiguous.csv",
    )
    ambiguous = _signal(record, "Supply Temp psi")
    flow = _signal(record, "Mystery Flow")
    assert ambiguous["mapping_state"] == "ambiguous"
    assert ambiguous["included_for_analysis"] is False
    assert flow["unit"]["unit_status"] == "unresolved"
    original_identity = record["dataset_identity"]
    original_hash = record["raw_source"]["sha256"]

    reviewed = apply_review(
        "reviewable",
        actor="operator@example.com",
        decisions=[
            {
                "signal_id": ambiguous["canonical_signal_id"],
                "mapping_action": "choose_role",
                "canonical_role": "pressure",
                "unit": "psi",
            },
            {"signal_id": flow["canonical_signal_id"], "unit": "gpm"},
        ],
    )

    assert reviewed["revision"] == 2
    assert reviewed["dataset_identity"] != original_identity
    assert reviewed["raw_source"]["sha256"] == original_hash
    assert len(reviewed["review"]["history"]) == 2
    assert all(item["actor"] == "operator@example.com" for item in reviewed["review"]["history"])
    assert _signal(reviewed, "Supply Temp psi")["mapping_state"] == "confidently_mapped"
    assert _signal(reviewed, "Mystery Flow")["unit"]["unit_confidence"] == "human_confirmed"
    assert reviewed["analysis_handoff"]["status"] == "reanalysis_required"


def test_ingestion_records_are_isolated_by_tenant_and_workspace() -> None:
    plant_a = build_dataset_scope(user_id="alice@example.com", workspace_id="plant-a")
    plant_b = build_dataset_scope(user_id="alice@example.com", workspace_id="plant-b")
    set_current_dataset_scope(plant_a)
    build_historical_ingestion(
        FIXTURES / "clean_historian.csv",
        dataset_id="tenant-data",
        filename="clean.csv",
    )
    plant_a_identity = read_ingestion_record("tenant-data")["dataset_identity"]

    set_current_dataset_scope(plant_b)
    assert read_ingestion_record("tenant-data") is None
    build_historical_ingestion(
        FIXTURES / "messy_industrial.csv",
        dataset_id="tenant-data",
        filename="messy.csv",
    )
    plant_b_identity = read_ingestion_record("tenant-data")["dataset_identity"]
    assert plant_b_identity != plant_a_identity

    set_current_dataset_scope(plant_a)
    assert read_ingestion_record("tenant-data")["dataset_identity"] == plant_a_identity
    set_current_dataset_scope(build_dataset_scope(user_id="bob@example.com", workspace_id="plant-a"))
    assert read_ingestion_record("tenant-data") is None


def test_versioned_api_is_pure_and_records_human_review(client, tmp_path: Path) -> None:
    source = tmp_path / "api-review.csv"
    source.write_text(
        "Timestamp,Supply Temp psi,Flow\n"
        + "\n".join(f"2026-01-01T00:{index:02d}:00Z,{index + 10},{index + 100}" for index in range(12))
        + "\n",
        encoding="utf-8",
    )
    record, _ = build_historical_ingestion(source, dataset_id="api-review", filename="api-review.csv")
    signal = _signal(record, "Supply Temp psi")
    state_files_before = {
        path: (path.stat().st_mtime_ns, path.read_bytes())
        for path in runtime_state().runtime_dir.rglob("*")
        if path.is_file()
    }

    profile_response = client.get("/api/data/ingestion/v1/datasets/api-review")
    canonical_response = client.get("/api/data/ingestion/v1/datasets/api-review/canonical?limit=2")
    assert profile_response.status_code == 200
    assert canonical_response.status_code == 200
    assert canonical_response.json()["rows"]
    state_files_after = {
        path: (path.stat().st_mtime_ns, path.read_bytes())
        for path in state_files_before
    }
    assert state_files_after == state_files_before

    inconsistent_unit = client.patch(
        "/api/data/ingestion/v1/datasets/api-review/review",
        json={
            "decisions": [{
                "signal_id": signal["canonical_signal_id"],
                "mapping_action": "choose_role",
                "canonical_role": "pressure",
                "unit": "degF",
            }]
        },
    )
    assert inconsistent_unit.status_code == 422
    assert "dimensionally inconsistent" in inconsistent_unit.json()["detail"]

    review = client.patch(
        "/api/data/ingestion/v1/datasets/api-review/review",
        json={
            "decisions": [{
                "signal_id": signal["canonical_signal_id"],
                "mapping_action": "choose_role",
                "canonical_role": "pressure",
                "unit": "psi",
            }]
        },
    )
    assert review.status_code == 200
    assert review.json()["revision"] == 2
    assert review.json()["review"]["history"][0]["provenance"] == "human_review"

    rejected = client.patch(
        "/api/data/ingestion/v1/datasets/api-review/review",
        json={"decisions": [{"signal_id": signal["canonical_signal_id"], "mapping_action": "choose_role", "canonical_role": "root_cause"}]},
    )
    assert rejected.status_code == 422


def test_malformed_source_never_silently_repairs_rows() -> None:
    record, _ = build_historical_ingestion(
        FIXTURES / "malformed_export.csv",
        dataset_id="malformed",
        filename="malformed_export.csv",
    )
    assert record["source_schema"]["malformed_row_counts"]["column_count_mismatch"] == 1
    assert record["timestamp_profile"]["malformed_or_impossible_count"] == 1
    assert record["canonical_dataset"]["major_gaps_interpolated"] is False
    assert record["provenance"]["no_silent_repairs"] is True
    assert record["readiness"]["outcome"] == "insufficient_trustworthy_data"
    assert json.dumps(record).count("trust_score") == 0
