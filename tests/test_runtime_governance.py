"""Production adapter integration and adversarial replay boundaries."""
from copy import deepcopy
from datetime import timedelta

import pytest

from app.governance.authority_store import InMemoryAuthorityDecisionStore, RuntimeAuthorityDecisionStore, parse_basis, parse_decision
from app.governance.context import ContextRegistry
from app.governance.policy import PolicyRegistry
from app.governance.maturity import replay_maturity
from app.services import live_analysis, live_intelligence
from app.services.dataset_scope import build_dataset_scope, dataset_scope_context
from app.services.finding_workflow import read_finding_case, governance_lifecycle_history
from app.services.runtime_governance import (
    adapt_relationships, evaluate_runtime_finding, model_reference_snapshot, read_runtime_history,
)
from test_evidence_governance import SCOPE
from test_governance_phase2 import anchor, changed
from test_live_analysis_phase2 import _baseline, _configuration, _insert_changed_series, NOW, SYSTEM_ID

AT = NOW.isoformat()


def real_detection():
    start = NOW - timedelta(hours=1)
    window = {"window_start": start.isoformat(), "window_end": AT,
        "rows_included": 30, "overall_coverage": 100, "signals_included": ["pump_power", "flow"],
        "rows": [{"timestamp": (start + timedelta(minutes=2*i)).isoformat(),
                  "pump_power": float(i+1), "flow": float(100-2*i)} for i in range(30)]}
    result = live_intelligence.analyze_live_window(run_id="run-1", system_id="system-1", baseline=_baseline(), window=window)
    assert len(result["detections"]) == 1
    return result["detections"][0], window


def inputs():
    detection, window = real_detection()
    return dict(scope=SCOPE, finding_id="finding-1", system="system-1", run_id="run-1", at=AT,
        relationships=[detection], source_ref="live-analysis-result:run-1",
        source_window={"start": window["window_start"], "end": window["window_end"]},
        model_snapshot=model_reference_snapshot(model_id="bdm-1", model_hash="frozen-hash", system="system-1", at=AT, source_ref="run-1"))


@pytest.fixture(params=[InMemoryAuthorityDecisionStore, RuntimeAuthorityDecisionStore])
def storage(request):
    return request.param()


def test_real_analytical_output_lineage_persistence_and_immutable_decision(storage):
    args = inputs()
    original = deepcopy(args["relationships"])
    snapshot = evaluate_runtime_finding(storage=storage, **args)
    assert args["relationships"] == original
    assert snapshot["maturity_label"] == "Persistent"
    evidence = snapshot["graph"]["evidence"][0]
    assert evidence["source_signals"] == ["flow", "pump_power"]
    assert evidence["source_run_id"] == "run-1"
    assert evidence["source_window"]["started_at"] == args["source_window"]["start"].replace("+00:00", "Z")
    assert evidence["payload"]["persistence_windows"] == original[0]["persistence"]["windows"]
    assert evidence["provenance"]["reference_ids"] == ["live-analysis-result:run-1"]
    assert "confidence_score" not in evidence["payload"]
    decision = parse_decision(snapshot["authority_decision"])
    basis = parse_basis(snapshot["audit_record"]["basis"])
    basis.validate_for(decision)
    assert replay_maturity(basis.maturity, basis.graph) == basis.maturity
    assert decision.decision_outcome.value == "deferred"
    assert decision.active_model_before == decision.active_model_after
    assert snapshot["classification"]["tier"] == "tier_b"
    assert snapshot["execution_authorized"] is False


def test_missing_context_and_consequence_never_elevate_maturity(storage):
    snapshot = evaluate_runtime_finding(storage=storage, **inputs(), consequence={"status": "quantified", "value": 99999})
    assert snapshot["maturity"]["level"] == "L1"
    assert snapshot["context_qualification"]["applicable_context_ids"] == []
    assert snapshot["consequence"]["value"] == 99999
    conditions = {a["condition"]: a["status"] for a in snapshot["classification"]["assessments"]}
    assert conditions["instrumentation_concern"] == conditions["excessive_evolution_rate"] == "unknown"


@pytest.mark.parametrize("limitation", ["limited", "missing_sibling"])
def test_limited_or_unadaptable_source_evidence_remains_explicit(limitation):
    args = inputs()
    if limitation == "limited":
        args["relationships"][0]["status"] = "limited"
    else:
        args["relationships"].append({"correlation_delta": -.5})
    snapshot = evaluate_runtime_finding(storage=InMemoryAuthorityDecisionStore(), **args)
    assert snapshot["maturity_label"] == "Observed"
    assert snapshot["authority_decision"]["decision_outcome"] == "deferred"
    assert snapshot["graph"]["evidence"][0]["payload"]["status"] == "limited"


def test_later_context_and_policy_cannot_rewrite_retry_or_replay(storage):
    args = inputs()
    original = evaluate_runtime_finding(storage=storage, **args)
    later = (NOW + timedelta(days=1)).isoformat()
    ContextRegistry(storage).append(SCOPE, changed(anchor(), created_at=later, effective_from=AT))
    policy = PolicyRegistry(storage).history(SCOPE, "system-1")[0]
    PolicyRegistry(storage).append(SCOPE, changed(policy, policy_version=2, supersedes=policy.policy_record_id,
                                                 created_at=later, effective_from=AT))
    assert evaluate_runtime_finding(storage=storage, **{**args, "at": later}) == original
    assert read_runtime_history(storage, SCOPE, "system-1", "finding-1") == [original]
    parse_basis(original["audit_record"]["basis"]).validate_for(parse_decision(original["authority_decision"]))


def test_retry_with_changed_source_is_rejected(storage):
    args = inputs()
    evaluate_runtime_finding(storage=storage, **args)
    args["relationships"][0]["correlation_delta"] = -.2
    with pytest.raises(ValueError, match="immutable_source_conflict"):
        evaluate_runtime_finding(storage=storage, **args)


def test_retry_cannot_reveal_later_record_to_an_earlier_evaluation(storage):
    args = inputs()
    evaluate_runtime_finding(storage=storage, **args)
    with pytest.raises(ValueError, match="retry_precedes_record"):
        evaluate_runtime_finding(storage=storage, **{**args, "at": (NOW-timedelta(minutes=1)).isoformat()})


def test_future_evidence_is_rejected(storage):
    args = inputs()
    args["at"] = (NOW - timedelta(hours=2)).isoformat()
    with pytest.raises(ValueError, match="later_knowledge"):
        evaluate_runtime_finding(storage=storage, **args)
    assert read_runtime_history(storage, SCOPE, "system-1", "finding-1") == []


def test_real_finding_maturity_regresses_without_rewriting_history(storage):
    args = inputs()
    before = evaluate_runtime_finding(storage=storage, **args)
    args.update(run_id="run-2", at=(NOW + timedelta(hours=1)).isoformat(), source_ref="live-analysis-result:run-2")
    args["relationships"][0]["persistence"] = {}
    after = evaluate_runtime_finding(storage=storage, **args)
    assert after["maturity_label"] == "Observed"
    assert after["lifecycle"]["state"] == "unresolved"
    assert after["lifecycle"]["previous_event_id"] == before["lifecycle"]["event_id"]
    assert read_runtime_history(storage, SCOPE, "system-1", "finding-1")[0] == before


def test_scheduled_live_path_persists_api_basis_and_existing_lifecycle(monkeypatch):
    with dataset_scope_context(build_dataset_scope(user_id="runtime-user")):
        _configuration()
        _insert_changed_series()
        monkeypatch.setattr(live_analysis.behavioral_model_repository, "read_model", lambda _: _baseline())
        run = live_analysis.trigger_live_analysis(SYSTEM_ID, now=NOW)
        assert run["status"] == "completed"
        finding = live_analysis.list_live_findings(system_id=SYSTEM_ID)[0]
        detail = read_finding_case(finding["finding_id"])
        assert detail["governance"]["maturity_label"] == "Persistent"
        assert detail["governance"]["authority_decision"]["source_run_id"] == run["run_id"]
        assert governance_lifecycle_history(finding["finding_id"])[0] == detail["governance"]["lifecycle"]
        assert detail["workflow"]["status"] == "open"


def test_real_sii_relationship_output_preserves_comparison_windows():
    from app.engine.sii_engine import evaluate_sii
    from test_sii_engine_v2 import _profiles
    columns = ["timestamp", "flow_rate", "supply_pressure", "pump_power"]
    rows = []
    for i in range(120):
        timestamp = f"2026-01-02T{i//60:02d}:{i%60:02d}:00Z"
        rows.append({"timestamp": timestamp, "flow_rate": 80+i*.25,
            "supply_pressure": 10+(80+i*.25)*.5 if i < 84 else 35+(i*17)%11,
            "pump_power": 15+(80+i*.25)*.2, "__source_row_number": i+2, "__source_timestamp": timestamp})
    sii = evaluate_sii(columns=columns, rows=rows, numeric_profiles=_profiles(columns),
        timestamp_column="timestamp", config={"numeric_columns": columns[1:]})
    relationships = sii["relationship_analysis"]["top_relationship_changes"]
    original = deepcopy(relationships)
    graph, _ = adapt_relationships(finding_id="f", system="system-1", run_id="real-sii", relationships=relationships,
        available_at=AT, source_ref="canonical-analysis:real-sii")
    assert graph.evidence
    assert relationships == original
    for evidence in graph.evidence:
        assert evidence.source_run_id == "real-sii"
        assert set(evidence.source_signals) <= set(columns[1:])
        assert evidence.payload["source_windows"]
        assert evidence.payload["metrics"]["baseline_sample_size"] == 84
        assert evidence.payload["metrics"]["recent_sample_size"] == 36


def test_upload_finding_api_returns_persisted_state_and_never_backfills(client):
    from app.services.evidence_store import upsert_evidence_run
    from app.services.finding_workflow import evidence_finding_id
    from test_finding_workflow import _record
    record = _record("api-run")
    upsert_evidence_run(record)
    finding_id = evidence_finding_id("api-run", "condition-a")
    first = client.get(f"/api/findings/{finding_id}")
    assert first.status_code == 200
    governance = first.json()["governance"]
    assert governance["status"] == "unavailable"
    assert governance["execution_authorized"] is False
    record["governance"] = {"maturity_label": "Context-qualified", "authority_label": "Permitted"}
    upsert_evidence_run(record)
    assert client.get(f"/api/findings/{finding_id}").json()["governance"] == governance


def test_connector_artifact_and_product_api_preserve_exact_governance():
    from dataclasses import replace
    from types import SimpleNamespace
    from app.services.runtime_governance import govern_connector_execution
    from app.services.phase4_scope import ServerBoundSystemIdentityV2
    from app.services.telemetry_result_artifact import build_canonical_result_artifact, decode_canonical_result_artifact
    from app.services.telemetry_result_projection import build_canonical_result_projection
    from test_telemetry_result_artifact import _execution
    from test_telemetry_result_projection import _execution as projected_execution, _metadata, _scope
    execution = _execution()
    detection, window_data = real_detection()
    analysis = {**execution.analysis_result, "conditions": [{"id": "condition-1", "supporting_relationships": [detection]}]}
    execution = replace(execution, analysis_result=analysis)
    window = SimpleNamespace(phase4_scope=SCOPE,
        phase4_system_identity=ServerBoundSystemIdentityV2(system_id="system-1", resource_scope_id=SCOPE.resource_scope_id, authority_record_digest="a"*64),
        window_start=NOW-timedelta(hours=1), window_end=NOW)
    governed = govern_connector_execution(execution, window, at=AT)
    assert governed.sii_result == execution.sii_result
    frozen = governed.analysis_result["governance"]
    assert frozen["condition-1"]["authority_decision"]["source_run_id"] == execution.source_run_id
    artifact = build_canonical_result_artifact(governed)
    assert decode_canonical_result_artifact(artifact)["analysis_result"]["governance"] == frozen
    # Exercise the existing product API projection with a valid scoped envelope.
    transport = projected_execution()
    transport["analysis_result"]["governance"] = frozen
    projection = build_canonical_result_projection(transport, artifact_metadata=_metadata(), scope=_scope(), lineage_verified=True)
    assert projection.product_result["governance"] == frozen


def test_expired_policy_rejected_and_historical_decision_kept(storage):
    args = inputs()
    first = evaluate_runtime_finding(storage=storage, **args)
    policy = PolicyRegistry(storage).history(SCOPE, "system-1")[0]
    later = (NOW + timedelta(hours=1)).isoformat()
    PolicyRegistry(storage).append(SCOPE, changed(policy, policy_version=2, supersedes=policy.policy_record_id,
        created_at=AT, effective_from=AT, effective_to=later))
    with pytest.raises(ValueError, match="policy_expired"):
        evaluate_runtime_finding(storage=storage, **{**args, "run_id": "later", "at": later})
    assert read_runtime_history(storage, SCOPE, "system-1", "finding-1") == [first]


def test_upload_writer_connects_authenticated_scope_to_immutable_finding():
    from app.services.phase4_scope import authenticated_phase4_scope_context, server_bound_system_identity_context, ServerBoundSystemIdentity
    from app.services.evidence_store import upsert_evidence_run
    from app.services.upload_evidence import build_evidence_record_from_result
    from app.services.finding_workflow import evidence_finding_id
    from app.services.runtime_governance import evidence_run_governance
    dataset = build_dataset_scope(user_id="operator", tenant_id=SCOPE.tenant_scope_id, workspace_id=SCOPE.workspace_id)
    detection, window = real_detection()
    detection["time_window"] = {"start": window["window_start"], "end": window["window_end"]}
    identity = ServerBoundSystemIdentity(system_id="system-1", dataset_scope_storage_id=dataset.storage_id, authority_record_digest="a"*64)
    record = build_evidence_record_from_result(run_id="upload-real", filename="telemetry.csv", source_type="csv_upload",
        created_at=AT, completed_at=AT, status="completed", initiated_by="operator",
        result={"row_count": 30, "column_count": 3, "system_id": "system-1",
            "active_baseline_reference": {"model_id": "baseline-1", "model_hash": "a"*64},
            "analysis_result": {"conditions": [{"condition_id": "condition-1", "supporting_relationships": [detection]}]}})
    with dataset_scope_context(dataset), authenticated_phase4_scope_context(SCOPE), server_bound_system_identity_context(identity):
        upsert_evidence_run(record)
        detail = read_finding_case(evidence_finding_id("upload-real", "condition-1"))
        assert detail["governance"]["status"] == "evaluated"
        assert detail["governance"]["authority_decision"]["decision_outcome"] == "deferred"
        assert evidence_run_governance("upload-real")["condition-1"] == detail["governance"]
        old_source = deepcopy(detail["evidence"])
        upsert_evidence_run({**record, "governance": {"maturity_label": "Context-qualified"}})
        assert read_finding_case(detail["finding_id"])["evidence"] == old_source


def test_invalid_governance_rolls_back_partial_writes_without_discarding_analysis():
    from app.services.runtime_db import db_connection
    from app.services.runtime_governance import _evaluate_in_transaction
    args = inputs()
    with db_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        args["relationships"][0]["persistence"]["windows"][0]["supports_change"] = False
        snapshot = _evaluate_in_transaction(connection, **args)
        assert _evaluate_in_transaction(connection, **args) == snapshot
    assert snapshot["status"] == "unavailable"
    assert snapshot["execution_authorized"] is False
    assert RuntimeAuthorityDecisionStore().history(SCOPE, "system-1") == []
    assert read_runtime_history(RuntimeAuthorityDecisionStore(), SCOPE, "system-1", "finding-1") == [snapshot]


def test_existing_lifecycle_is_orthogonal_to_maturity(storage):
    args = inputs()
    args["relationships"][0]["persistence"] = {}
    snapshot = evaluate_runtime_finding(storage=storage, **args, lifecycle_state="persistent")
    assert snapshot["maturity_label"] == "Observed"
    assert snapshot["lifecycle"]["state"] == "persistent"
    resolved = evaluate_runtime_finding(storage=storage, **{**args, "relationships": [], "run_id": "resolved",
        "at": (NOW+timedelta(hours=1)).isoformat()}, lifecycle_state="closed")
    assert resolved["status"] == "unavailable"
    assert resolved["lifecycle"]["state"] == "closed"
    assert resolved["lifecycle"]["previous_event_id"] == snapshot["lifecycle"]["event_id"]
    assert "authority_decision" not in resolved


def test_real_connector_path_uses_normalized_windows_not_timezone_free_display_text():
    from datetime import datetime, UTC
    from app.services.telemetry_analysis_window import build_canonical_analysis_window, run_analysis_window
    from app.services.runtime_governance import govern_connector_execution
    from test_telemetry_analysis_handoff import _scope, _identity, _observation, DIGEST, SIGNAL
    scope = _scope()
    start = datetime(2026, 8, 25, tzinfo=UTC)
    signals = [SIGNAL, "4385267d-f840-59c4-ba65-06a6726e3189", "cdf5dc57-eefc-486c-b819-e49550f1bbd7"]
    observations = []
    for i in range(120):
        values = [80+i*.25, 10+(80+i*.25)*.5 if i < 84 else 35+(i*17)%11, 15+(80+i*.25)*.2]
        for j, (signal, value) in enumerate(zip(signals, values)):
            observations.append({**_observation(i*3+j, signal, start+timedelta(minutes=i), value), "canonical_signal_name": f"pressure_{j}"})
    window = build_canonical_analysis_window(window_id="window-real", source_run_id="run-a", scope=scope,
        system_id="system-a", asset_id="asset-a", persisted_authority_digest=DIGEST,
        phase4_system_identity=_identity(scope), observations=observations)
    execution = run_analysis_window(window)
    assert execution.analysis_result["conditions"]
    original = deepcopy(dict(execution.sii_result))
    result = govern_connector_execution(execution, window, at="2026-09-07T00:00:00Z")
    assert result.sii_result == original
    for snapshot in result.analysis_result["governance"].values():
        assert snapshot["status"] == "evaluated"
        assert snapshot["maturity_label"] == "Observed"
        for evidence in snapshot["graph"]["evidence"]:
            assert evidence["source_window"]["started_at"] == "2026-08-25T00:00:00Z"
            assert evidence["source_window"]["ended_at"] == "2026-08-25T01:59:00Z"
            assert evidence["payload"]["source_evidence_refs"]
