from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json

import pytest

from app.engine.sii.behavioral_model_contract import canonical_phase4_resource_scope_id
from app.services import relationship_lineage as v1
from app.services.relationship_lineage_v2 import (
    ARTIFACT_CONTRACT,
    RelationshipLineageV2Error,
    build_artifact,
    issue,
    readback,
    verify,
)
from app.services.telemetry_domain import TelemetryScopeRef
from app.services.telemetry_relationship_lineage_v2_repository import (
    EndpointLineageV2Conflict,
    PostgreSQLEndpointLineageV2Repository,
)
from db.migrations.create_relationship_lineage_v2_artifacts import DDL, MIGRATION_ID, REQUIRED_MIGRATIONS
from test_telemetry_analysis_window_v2 import _binding, _observation, _scope, _window


def _pair(window):
    pressure = [item.series_id for item in window.series if item.identity.canonical_concept_id == window.series[0].identity.canonical_concept_id]
    flow = next(item.series_id for item in window.series if item.identity.canonical_concept_id != window.series[0].identity.canonical_concept_id)
    return window.relationship_pair(pressure[0], flow)


def _artifact(window=None, pair=None):
    window = window or _window()
    pair = pair or _pair(window)
    return build_artifact(
        window, pair,
        result={"status": "evaluated", "correlation": 0.75},
        evidence={"sample_count": 2, "basis": "test-only"},
    )


def test_endpoint_pair_survives_json_roundtrip_and_exact_readback() -> None:
    window = _window()
    pair = _pair(window)
    artifact = _artifact(window, pair)
    loaded = readback(json.loads(json.dumps(artifact)), window=window, pair=pair)
    lineage = loaded["payload"]["lineage"]
    assert loaded == artifact
    assert lineage["payload"]["source_endpoint"] == pair.source.as_dict()
    assert lineage["payload"]["target_endpoint"] == pair.target.as_dict()
    assert lineage["payload"]["source_endpoint"]["mapping_revision"] == 3
    assert lineage["payload"]["scope"]["resource_scope_id"] == window.scope.resource_scope_id
    assert loaded["payload"]["result"]["relationship_lineage_ref"] == lineage["ref"]
    assert loaded["payload"]["evidence"]["relationship_lineage_ref"] == lineage["ref"]


def test_same_concept_physical_sources_remain_distinct_and_ordered() -> None:
    window = _window()
    first = _pair(window)
    other_source = next(
        item.series_id for item in window.series
        if item.identity.canonical_concept_id == first.source.canonical_concept_id
        and item.series_id != first.source.endpoint_id
    )
    second = window.relationship_pair(other_source, first.target.endpoint_id)
    assert first.source.canonical_concept_id == second.source.canonical_concept_id
    assert first.source.endpoint_id != second.source.endpoint_id
    assert issue(window, first)["ref"] != issue(window, second)["ref"]
    assert issue(window, first)["ref"] != issue(window, window.relationship_pair(
        first.target.endpoint_id, first.source.endpoint_id
    ))["ref"]
    assert issue(window, first) == issue(window, first)


def test_deterministic_replay_independent_of_observation_input_order() -> None:
    bindings = (_binding(1), _binding(2), _binding(3, "00000000-0000-0000-0000-000000000302"))
    observations = tuple(_observation(binding, minute) for minute in (0, 1) for binding in bindings)
    first = _window(bindings, observations)
    replay = _window(tuple(reversed(bindings)), tuple(reversed(observations)))
    first_pair = _pair(first)
    replay_pair = replay.relationship_pair(first_pair.source.endpoint_id, first_pair.target.endpoint_id)
    assert first.schema_fingerprint == replay.schema_fingerprint
    assert first.content_digest == replay.content_digest
    assert issue(first, first_pair) == issue(replay, replay_pair)
    assert _artifact(first, first_pair) == _artifact(replay, replay_pair)


@pytest.mark.parametrize("field,value", [
    ("mapping_revision", 4),
    ("authority_digest", "b" * 64),
    ("system_id", "system-b"),
    ("asset_id", "pump-2"),
    ("canonical_concept_id", "00000000-0000-0000-0000-000000000999"),
    ("connection_id", "00000000-0000-0000-0000-000000000999"),
    ("external_signal_id", "00000000-0000-0000-0000-000000000999"),
])
def test_corrupt_endpoint_authority_fails_readback(field, value) -> None:
    window = _window()
    pair = _pair(window)
    artifact = _artifact(window, pair)
    corrupted = deepcopy(artifact)
    corrupted["payload"]["lineage"]["payload"]["source_endpoint"][field] = value
    with pytest.raises(RelationshipLineageV2Error, match="lineage_mismatch"):
        readback(corrupted, window=window, pair=pair)


def test_missing_endpoint_or_changed_window_fingerprint_fails_closed() -> None:
    window = _window()
    pair = _pair(window)
    artifact = _artifact(window, pair)
    for field in ("mapping_id", "authority_digest", "resource_scope_id"):
        corrupted = deepcopy(artifact)
        del corrupted["payload"]["lineage"]["payload"]["source_endpoint"][field]
        with pytest.raises(RelationshipLineageV2Error, match="lineage_mismatch"):
            readback(corrupted, window=window, pair=pair)
    for field in ("schema_fingerprint", "window_content_digest"):
        corrupted = deepcopy(artifact)
        corrupted["payload"]["lineage"]["payload"][field] = "stale"
        with pytest.raises(RelationshipLineageV2Error, match="lineage_mismatch"):
            readback(corrupted, window=window, pair=pair)


def test_stale_projection_and_wrong_pair_fail_closed() -> None:
    window = _window()
    pair = _pair(window)
    stale = replace(pair, source=replace(pair.source, mapping_revision=4))
    with pytest.raises(RelationshipLineageV2Error, match="pair_mismatch"):
        issue(window, stale)
    different = window.relationship_pair(pair.target.endpoint_id, pair.source.endpoint_id)
    with pytest.raises(RelationshipLineageV2Error, match="lineage_mismatch"):
        readback(_artifact(window, pair), window=window, pair=different)


def test_v1_and_v2_lineage_readers_do_not_alias() -> None:
    window = _window()
    pair = _pair(window)
    descriptor = issue(window, pair)
    assert not v1.verify(descriptor)
    assert not verify({"ref": "v1", "payload": {"contract": "relationship-lineage.v1"}}, window=window, pair=pair)
    with pytest.raises(RelationshipLineageV2Error):
        readback({"ref": "v1", "payload": {"contract_version": "relationship-lineage.v1"}}, window=window, pair=pair)
    assert not verify({"ref": descriptor["ref"], "payload": {**descriptor["payload"], "contract_version": "relationship-lineage.v1"}}, window=window, pair=pair)


def test_result_and_evidence_identity_or_digest_corruption_fails_closed() -> None:
    window = _window()
    pair = _pair(window)
    artifact = _artifact(window, pair)
    bad_evidence = deepcopy(artifact)
    bad_evidence["payload"]["evidence"]["relationship_lineage_ref"] = "wrong"
    with pytest.raises(RelationshipLineageV2Error, match="evidence_identity_mismatch"):
        readback(bad_evidence, window=window, pair=pair)
    bad_result = deepcopy(artifact)
    bad_result["payload"]["result"]["payload"]["correlation"] = 0.1
    with pytest.raises(RelationshipLineageV2Error, match="artifact_digest_mismatch"):
        readback(bad_result, window=window, pair=pair)
    assert artifact["payload"]["contract_version"] == ARTIFACT_CONTRACT


class _Connection:
    def __init__(self, rows):
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def cursor(self):
        return _Cursor(self.rows)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


class _Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.result = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params):
        if "INSERT INTO telemetry.relationship_lineage_artifacts_v2" in sql:
            keys = (
                "artifact_ref", "lineage_ref", "contract_version", "resource_scope_id",
                "tenant_scope_id", "workspace_id", "facility_id", "system_id", "asset_id",
                "window_id", "source_run_id", "schema_fingerprint", "window_content_digest",
                "pair_ref", "source_endpoint_id", "target_endpoint_id", "artifact_payload",
            )
            row = dict(zip(keys, params, strict=True))
            row["artifact_payload"] = json.loads(row["artifact_payload"])
            self.rows.setdefault((row["resource_scope_id"], row["lineage_ref"]), row)
            self.result = None
        elif "SELECT artifact_ref" in sql:
            self.result = self.rows.get((params[0], params[-1]))
            if self.result is not None and tuple(self.result[key] for key in (
                "resource_scope_id", "tenant_scope_id", "workspace_id", "facility_id"
            )) != tuple(params[:4]):
                self.result = None
        else:
            raise AssertionError("Unexpected repository SQL")

    def fetchone(self):
        return self.result


def test_repository_persist_and_readback_verify_exact_pair_and_scope() -> None:
    rows = {}
    repository = PostgreSQLEndpointLineageV2Repository(lambda: _Connection(rows))
    window = _window()
    pair = _pair(window)
    stored = repository.persist(window.scope, window=window, pair=pair,
                                result={"correlation": 0.75}, evidence={"basis": "test-only"})
    assert repository.read(window.scope, window=window, pair=pair) == stored
    assert repository.persist(window.scope, window=window, pair=pair,
                              result={"correlation": 0.75}, evidence={"basis": "test-only"}) == stored
    with pytest.raises(EndpointLineageV2Conflict, match="immutable_conflict"):
        repository.persist(window.scope, window=window, pair=pair,
                           result={"correlation": 0.1}, evidence={"basis": "test-only"})
    with pytest.raises(EndpointLineageV2Conflict, match="scope_mismatch"):
        repository.read(TelemetryScopeRef(
            tenant_scope_id="tenant-b", workspace_id="ws-facility-a",
            resource_scope_id=canonical_phase4_resource_scope_id("tenant-b", "ws-facility-a"),
            facility_id="ws-facility-a",
        ), window=window, pair=pair)
    rows[(window.scope.resource_scope_id, issue(window, pair)["ref"])]["source_endpoint_id"] = "corrupt"
    with pytest.raises(EndpointLineageV2Conflict, match="stored_authority_mismatch"):
        repository.read(window.scope, window=window, pair=pair)


def test_migration_is_additive_and_v2_artifacts_are_immutable() -> None:
    assert MIGRATION_ID == "008_create_relationship_lineage_v2_artifacts"
    assert REQUIRED_MIGRATIONS == ("007_create_relationship_temporal_state",)
    assert "CREATE TABLE telemetry.relationship_lineage_artifacts_v2" in DDL
    assert "BEFORE UPDATE OR DELETE" in DDL
    assert "relationship-lineage[.]v2" in DDL
    assert "DROP INDEX" not in DDL
    assert "ALTER TABLE telemetry.signal_mappings" not in DDL
    assert "ALTER TABLE telemetry.analysis_result_artifacts" not in DDL
