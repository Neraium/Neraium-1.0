from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json
from types import SimpleNamespace

import pytest

from app.services import relationship_temporal_state as gate
from app.services.telemetry_domain import TelemetryScopeRef
from app.engine.sii.behavioral_model_contract import canonical_phase4_resource_scope_id
from app.services.telemetry_repository import _relationship_state_identity, _relationship_state_payload


def _scope():
    return TelemetryScopeRef("tenant-a", "workspace-a",
        canonical_phase4_resource_scope_id("tenant-a", "workspace-a"), "workspace-a")


def _descriptor(**changes):
    payload = {
        "contract": "relationship-lineage.v1", "scope_ref": "scope-ref",
        "scope": {"tenant_scope_id": "tenant-a", "workspace_id": "workspace-a",
                  "resource_scope_id": _scope().resource_scope_id,
                  "system_id": "system-a", "asset_id": "asset-a"},
        "endpoints": ["signal-a", "signal-b"],
        "relationship_semantics": "linear_correlation.v1", "semantic_version": "pearson-global.v1",
        "assessment_basis": "global_relationship_model", "mode_identity": None,
    }
    payload.update(changes)
    return {"ref": "lineage-1", "payload": payload, "continuation_eligible": True}


def _evidence(**changes):
    record = {"basis": "global_relationship_model", "source": {"columns": ["signal-a", "signal-b"]},
        "temporal": {"status": "available", "method": gate.REDUCER,
                     "identity": {"basis": "global_relationship_model", "columns": ["signal-a", "signal-b"], "baseline_correlation": .2},
                     "parameters": {"minimum_quality": .35}},
        "reference": {"reference_dataset_id": "dataset-1"},
        "context": {"mode_conditioning": {}, "operating_mode": {"recent_mode": "normal"}}}
    record.update(changes)
    return record


def _stored(record=None, descriptor=None, **changes):
    record, descriptor = record or _evidence(), descriptor or _descriptor()
    at = datetime(2026, 1, 1, tzinfo=UTC)
    row = {"state_schema": gate.SCHEMA,
        "compatibility_digest": gate.compatibility_digest(record, descriptor),
        "reducer_state": {"version": 1, "identity": record["temporal"]["identity"],
            "observations": [{"observed_at": at.isoformat(), "time_window": {}, "source_rows": [],
                "source_dataset_id": None, "signed_correlation_delta": .2,
                "edge_confidence": .8, "data_quality_factor": .9,
                "eligible": True, "acceptable": True}]},
        "head_event_ref": "event-1", "head_event_time": at, "storage_revision": 1}
    _body, row["state_digest"] = _relationship_state_payload(
        _relationship_state_identity(_scope(), "system-a", "asset-a", descriptor["ref"]),
        row["compatibility_digest"], row["reducer_state"],
        head_event_ref=row["head_event_ref"], head_event_time=at)
    row.update(changes)
    if "state_digest" not in changes:
        identity = _relationship_state_identity(_scope(), "system-a", "asset-a", descriptor["ref"])
        body = {"schema": gate.SCHEMA, "version": 1, "scope": list(identity[:4]),
            "system_id": identity[4], "asset_id": identity[5], "lineage_ref": identity[6],
            "compatibility_digest": row["compatibility_digest"], "reducer_state": row["reducer_state"],
            "head_event_ref": row["head_event_ref"], "head_event_time": row["head_event_time"].isoformat()}
        row["state_digest"] = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"),
            allow_nan=False).encode("utf-8")).hexdigest()
    return row


def _run(monkeypatch, stored, *, descriptor=None, evidence=None, candidate=None, scope=None):
    descriptor, evidence = descriptor or _descriptor(), evidence or _evidence()
    candidate = candidate or {"relationship_evidence_ref": "evidence-1", "relationship_source_ref": "source-1",
                              "relationship_assessment_binding": "binding-1", "relationship_lineage_ref": descriptor["ref"]}
    registry = {"relationship_lineage": {"evidence-1": descriptor}}
    monkeypatch.setattr(gate, "resolve", lambda *a, **k: evidence)
    monkeypatch.setattr(gate, "verify_for_evidence", lambda *a, **k: True)
    class Repo:
        def read_relationship_temporal_state(self, _scope, **kwargs):
            self.key = kwargs
            return stored
    repo = Repo()
    value = gate.load_prior_relationship_state(repo, scope or _scope(), system_id="system-a", asset_id="asset-a",
        candidate=candidate, registry=registry, authorized_scope="authorized")
    return value, repo


def test_exact_compatible_state_loads_and_absent_is_clean(monkeypatch):
    record, descriptor = _evidence(), _descriptor()
    value, repo = _run(monkeypatch, _stored(record, descriptor), descriptor=descriptor, evidence=record)
    assert value["observations"][0]["signed_correlation_delta"] == .2
    assert repo.key == {"system_id": "system-a", "asset_id": "asset-a", "lineage_ref": "lineage-1"}
    value, _ = _run(monkeypatch, None, descriptor=descriptor, evidence=record)
    assert value is None


@pytest.mark.parametrize("field,value", [
    ("endpoints", ["signal-a", "signal-c"]),
    ("assessment_basis", "mode_conditioned_relationships"),
    ("semantic_version", "pearson-global.v2"),
    ("mode_identity", {"mode_id": "mode-2", "features": {"shift": "night"}}),
])
def test_compatibility_changes_reject_stored_state(monkeypatch, field, value):
    descriptor, record = _descriptor(), _evidence()
    old = _stored(record, descriptor)
    new_descriptor = _descriptor(**{field: value})
    value, _ = _run(monkeypatch, old, descriptor=new_descriptor, evidence=record)
    assert value is None


def test_scope_system_asset_lineage_and_missing_authority_isolation(monkeypatch):
    descriptor, record = _descriptor(), _evidence()
    original = _stored(record, descriptor)
    value, _ = _run(monkeypatch, original, scope=TelemetryScopeRef("tenant-b", "workspace-b",
        canonical_phase4_resource_scope_id("tenant-b", "workspace-b"), "workspace-b"))
    assert value is None
    for kwargs in ({"system_id": "system-b"}, {"asset_id": "asset-b"}):
        candidate = {"relationship_evidence_ref": "evidence-1", "relationship_lineage_ref": "lineage-1"}
        registry = {"relationship_lineage": {"evidence-1": descriptor}}
        monkeypatch.setattr(gate, "resolve", lambda *a, **k: record)
        monkeypatch.setattr(gate, "verify_for_evidence", lambda *a, **k: True)
        assert gate.load_prior_relationship_state(SimpleNamespace(read_relationship_temporal_state=lambda *a, **k: original),
            _scope(), system_id=kwargs.get("system_id", "system-a"), asset_id=kwargs.get("asset_id", "asset-a"),
            candidate=candidate, registry=registry, authorized_scope="authorized") is None
    value, _ = _run(monkeypatch, original, candidate={"relationship_evidence_ref": "evidence-1"})
    assert value is None
    monkeypatch.setattr(gate, "resolve", lambda *a, **k: None)
    assert gate.load_prior_relationship_state(None, _scope(), system_id="system-a", asset_id="asset-a",
        candidate={"relationship_evidence_ref": "evidence-1", "relationship_lineage_ref": "lineage-1"},
        registry={"relationship_lineage": {}}, authorized_scope="authorized") is None


def test_fallback_global_mode_and_failed_authority_cannot_borrow(monkeypatch):
    descriptor, record = _descriptor(), _evidence()
    fallback = deepcopy(record)
    fallback["basis"] = "global_relationship_model_failure_fallback"
    value, _ = _run(monkeypatch, _stored(record, descriptor), descriptor=descriptor, evidence=fallback)
    assert value is None
    monkeypatch.setattr(gate, "resolve", lambda *a, **k: None)  # failed / unavailable A-B resolution
    assert gate.load_prior_relationship_state(None, _scope(), system_id="system-a", asset_id="asset-a",
        candidate={"relationship_evidence_ref": "evidence-1", "relationship_lineage_ref": "lineage-1"},
        registry={"relationship_lineage": {"evidence-1": descriptor}}, authorized_scope="authorized") is None


@pytest.mark.parametrize("changes", [
    {"compatibility_digest": "0" * 64}, {"state_schema": "relationship-temporal-state.v0"},
    {"state_digest": "0" * 64},
    {"storage_revision": 0}, {"head_event_ref": ""},
    {"reducer_state": {"version": 2, "identity": {}, "observations": []}},
    {"reducer_state": {"version": 1, "identity": {}, "observations": [{}] * 9}},
    {"reducer_state": {"version": 1, "identity": _evidence()["temporal"]["identity"], "observations": []}},
    {"reducer_state": {"version": 1, "identity": _evidence()["temporal"]["identity"],
        "observations": [{"observed_at": "2026-01-01T00:00:00+00:00", "signed_correlation_delta": .2}]}},
    {"head_event_time": datetime(2026, 1, 2, tzinfo=UTC)},
])
def test_tampered_schema_and_bounds_fail_closed(monkeypatch, changes):
    record, descriptor = _evidence(), _descriptor()
    value, _ = _run(monkeypatch, _stored(record, descriptor, **changes), descriptor=descriptor, evidence=record)
    assert value is None


def test_compatibility_ignores_volatile_and_presentation_fields():
    record, descriptor = _evidence(), _descriptor()
    before = gate.compatibility_digest(record, descriptor)
    noisy = deepcopy(record)
    noisy.update(rank=1, primary=True, group="x", presentation={"label": "old"}, runtime_id="r1", retry_id="t1")
    assert gate.compatibility_digest(noisy, descriptor) == before


def test_failed_load_does_not_mutate_current_analysis(monkeypatch):
    analysis = {"current_relationships": [{"score": .7}], "ranking": ["a"]}
    before = deepcopy(analysis)
    value, _ = _run(monkeypatch, {"malformed": True})
    assert value is None
    assert analysis == before
