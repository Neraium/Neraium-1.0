from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from app.services.authority_contract_common import (
    AuthorityScope,
    ContractValidationError,
    ContractVersion,
    ScopeLevel,
    TypedDigest,
    VersionBundle,
)
from app.services.authority_identity import (
    AnalyticalFindingIdentity,
    AnalyticalReferenceIdentity,
    AuthorityExecutionIdentity,
    CanonicalObservationIdentity,
    CanonicalPackageIdentity,
    ChronologyExecutionIdentity,
    ChronologySlotIdentity,
    ClassificationBindingIdentity,
    ConfidenceBindingIdentity,
    EvidenceBindingIdentity,
    EvidenceFactIdentity,
    NativeResultIdentity,
    PersistenceAssessmentIdentity,
    SectionIdentity,
    WorkflowCaseIdentity,
    ordered_identity_set_digest,
    unordered_identity_set_digest,
)
from app.services.telemetry_result_artifact import canonical_result_id


FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "reconciled_authority_identity_vectors.v1.json"
)
WINDOW_ID = "00000000-0000-5000-8000-000000000101"
EXECUTION_CONTRACT = "analysis-window-execution.v1"
P01_RESULT_ID = "701d3bbf-9bf6-58cf-8c5d-8bd31ce86502"


def _digest(contract: str, marker: str) -> TypedDigest:
    return TypedDigest.from_value(contract, {"fixture_marker": marker})


def _scope(*, connection_id: str = "connection-fixture-a", asset_id: str | None = None) -> AuthorityScope:
    return AuthorityScope(
        level=ScopeLevel.ASSET,
        tenant_id="tenant-fixture",
        workspace_id="workspace-fixture",
        resource_scope_id="resource-fixture",
        facility_id="facility-fixture",
        connection_id=connection_id,
        system_id="system-fixture",
        asset_id=asset_id,
        native_result_id=None,
        authority_execution_id=None,
        finding_id=None,
    )


def _graph(mutation: str | None = None) -> dict[str, Any]:
    """Build the vector graph; mutations alter one direct identity input only."""

    scope = _scope()
    observation = CanonicalObservationIdentity(
        scope=scope,
        value=(
            "00000000-0000-5000-8000-000000000202"
            if mutation == "canonical_observation.existing_observation_id"
            else "00000000-0000-5000-8000-000000000201"
        ),
    )
    versions = VersionBundle(
        versions=(
            ContractVersion("analytical-authority", "1"),
            ContractVersion("authority-configuration", "1"),
            ContractVersion("finding-determination", "1"),
            ContractVersion("chronology-reference", "1"),
        )
    )
    analytical_reference = AnalyticalReferenceIdentity(
        scope=scope,
        producer_family="sii",
        model_id="fixture-model",
        model_version="3",
        learning_generation=7,
        configuration_generation=4,
        snapshot_id=(
            "snapshot-fixture-mutated"
            if mutation == "analytical_reference.snapshot_id"
            else "snapshot-fixture"
        ),
        snapshot_digest=_digest("fixture.snapshot.v1", "snapshot"),
        causal_frontier_digest=_digest("fixture.frontier.v1", "frontier"),
        chronology_binding_digest=_digest("fixture.chronology-binding.v1", "binding"),
        method_identity=ContractVersion("fixture-analysis-method", "3"),
        configuration_identity=_digest("fixture.analysis-config.v1", "config"),
        integrity_identity=_digest("fixture.reference-integrity.v1", "integrity"),
    )
    slot = ChronologySlotIdentity(
        scope=scope,
        authority_digest=_digest("fixture.chronology-authority.v1", "authority"),
        analysis_config_digest=_digest("fixture.analysis-config.v1", "config"),
        cadence_origin=datetime(2026, 1, 1, tzinfo=timezone.utc),
        evaluation_endpoint=datetime(2026, 1, 2, 12, tzinfo=timezone.utc),
        contribution_start=datetime(2026, 1, 2, 11, tzinfo=timezone.utc),
        contribution_end=datetime(2026, 1, 2, 12, tzinfo=timezone.utc),
        lookback_start=datetime(2026, 1, 1, 12, tzinfo=timezone.utc),
        lookback_end=datetime(2026, 1, 2, 12, tzinfo=timezone.utc),
        learning_generation=(
            8 if mutation == "chronology_slot.learning_generation" else 7
        ),
    )
    chronology_execution = ChronologyExecutionIdentity(
        chronology_slot_id=slot,
        analysis_generation=3,
        execution_mode="active",
        manifest_digest=_digest("fixture.manifest.v1", "manifest"),
        analytical_input_digest=_digest("fixture.analytical-input.v1", "input"),
        expected_progress_revision=(
            12
            if mutation == "chronology_execution.expected_progress_revision"
            else 11
        ),
        predecessor_reference_id=analytical_reference,
        predecessor_reference_digest=_digest(
            "fixture.predecessor-reference.v1", "predecessor"
        ),
        authority_digest=_digest("fixture.chronology-authority.v1", "authority"),
        configuration_digest=_digest("fixture.chronology-config.v1", "config"),
    )
    native_window = (
        "00000000-0000-5000-8000-000000000102"
        if mutation == "native_result.window_id"
        else WINDOW_ID
    )
    native_result = NativeResultIdentity.from_window(
        scope=scope,
        window_id=native_window,
        execution_contract_version=EXECUTION_CONTRACT,
    )
    authority_execution = AuthorityExecutionIdentity(
        scope=scope,
        source_kind=(
            "telemetry_connector"
            if mutation == "authority_execution.source_kind"
            else "connector"
        ),
        native_terminal_source_id=native_result.value,
        native_terminal_digest=_digest("fixture.native-terminal.v1", "native"),
        chronology_execution_id=chronology_execution,
        versions=versions,
    )
    finding = AnalyticalFindingIdentity(
        authority_execution_id=authority_execution,
        determination_contract=ContractVersion("finding-determination", "1"),
        finding_type="structural_change",
        affected_scope=scope,
        subject_identity=(
            "subject-fixture-mutated"
            if mutation == "analytical_finding.subject_identity"
            else "subject-fixture"
        ),
        relationship_metric_identities=("metric.alpha", "metric.beta"),
        analytical_reference_id=analytical_reference,
    )
    fact = EvidenceFactIdentity(
        authority_execution_id=authority_execution,
        fact_type=(
            "relationship_delta_mutated"
            if mutation == "evidence_fact.fact_type"
            else "relationship_delta"
        ),
        producer_schema=ContractVersion("fixture-evidence-fact", "1"),
        subject_scope=scope,
        subject_identity="subject-fixture",
        dimensions=(("signal_b", "flow"), ("signal_a", "pressure")),
        value_unit_event_time_digest=_digest("fixture.fact-value.v1", "fact"),
        analytical_reference_id=analytical_reference,
    )
    evidence_binding = EvidenceBindingIdentity(
        authority_execution_id=authority_execution,
        analytical_finding_id=finding,
        evidence_fact_id=fact,
        role="contradictory" if mutation == "evidence_binding.role" else "supporting",
        qualification="admitted",
        qualification_contract=ContractVersion("fixture-qualification", "1"),
        limitation_set_digest=_digest("fixture.limitation-set.v1", "limitations"),
    )
    binding_set = ordered_identity_set_digest(
        (evidence_binding,), contract="fixture.ordered-evidence-bindings.v1"
    )
    classification = ClassificationBindingIdentity(
        analytical_finding_id=finding,
        classifier_rule=ContractVersion(
            "finding-classification", "deterministic_finding_classification_v3"
        ),
        input_contract=ContractVersion(
            "fixture-classification-input",
            "2" if mutation == "classification_binding.input_contract.version" else "1",
        ),
        ordered_binding_set_digest=binding_set,
    )
    persistence = PersistenceAssessmentIdentity(
        analytical_finding_id=finding,
        method=ContractVersion("fixture-persistence-method", "1"),
        chronology_execution_id=chronology_execution,
        event_time_window_digest=_digest("fixture.event-time-window.v1", "window"),
        exact_fact_set_digest=_digest(
            "fixture.exact-fact-set.v1",
            "facts-mutated"
            if mutation == "persistence_assessment.exact_fact_set_digest"
            else "facts",
        ),
    )
    confidence = ConfidenceBindingIdentity(
        analytical_finding_id=finding,
        confidence_contract=ContractVersion(
            "finding-confidence", "finding-confidence-v1"
        ),
        exact_input_set_digest=_digest(
            "fixture.confidence-input-set.v1",
            "confidence-mutated"
            if mutation == "confidence_binding.exact_input_set_digest"
            else "confidence",
        ),
        persistence_assessment_id=persistence,
    )
    package = CanonicalPackageIdentity(
        authority_execution_id=authority_execution,
        package_schema=ContractVersion(
            "fixture-canonical-package",
            "2" if mutation == "canonical_package.package_schema.version" else "1",
        ),
    )
    section = SectionIdentity(
        package_id=package,
        section_family="findings",
        section_schema=ContractVersion("fixture-findings-section", "1"),
        sequence_number=2 if mutation == "section.sequence_number" else 1,
    )
    finding_scope = AuthorityScope(
        level=ScopeLevel.FINDING,
        tenant_id=scope.tenant_id,
        workspace_id=scope.workspace_id,
        resource_scope_id=scope.resource_scope_id,
        facility_id=scope.facility_id,
        connection_id=scope.connection_id,
        system_id=scope.system_id,
        asset_id=scope.asset_id,
        native_result_id=str(native_result.value),
        authority_execution_id=str(authority_execution.value),
        finding_id=str(finding.value),
    )
    workflow = WorkflowCaseIdentity(
        scope=finding_scope,
        authority_execution_id=authority_execution,
        analytical_finding_id=finding,
        workflow_contract=ContractVersion(
            "fixture-workflow",
            "2" if mutation == "workflow_case.workflow_contract.version" else "1",
        ),
    )
    return {
        "canonical_observation": observation,
        "chronology_slot": slot,
        "chronology_execution": chronology_execution,
        "native_result": native_result,
        "authority_execution": authority_execution,
        "analytical_reference": analytical_reference,
        "analytical_finding": finding,
        "evidence_fact": fact,
        "evidence_binding": evidence_binding,
        "classification_binding": classification,
        "persistence_assessment": persistence,
        "confidence_binding": confidence,
        "canonical_package": package,
        "section": section,
        "workflow_case": workflow,
    }


def _vectors() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["vectors"]


def test_frozen_identity_vectors_are_stable_and_mutation_sensitive() -> None:
    graph = _graph()
    vectors = _vectors()
    assert set(vectors) == set(graph)

    for name, identity in graph.items():
        vector = vectors[name]
        identity_dict = identity.as_dict()
        assert vector["contract"] == identity.CONTRACT
        assert vector["canonical_components"] == identity_dict["canonical_components"]
        assert vector["canonical_serialized"]["encoding"] == "hex"
        assert vector["canonical_serialized"]["value"] == identity.canonical_hex
        assert vector["expected_id"] == str(identity.value)
        assert vector["stability"] == {"repeat_runs": 3, "expected": "identical"}
        assert str(_graph()[name].value) == vector["expected_id"]
        assert str(_graph(vector["mutation"]["name"])[name].value) == vector["mutation"]["expected_different_id"]
        assert vector["mutation"]["expected_different_id"] != vector["expected_id"]


def test_identity_equality_and_hash_semantics_are_value_object_stable() -> None:
    left = _graph()
    right = _graph()

    for name, identity in left.items():
        assert identity == right[name]
        assert hash(identity) == hash(right[name])
        assert len({identity, right[name]}) == 1


def test_p01_result_identity_is_delegated_and_byte_compatible() -> None:
    vector = _vectors()["native_result"]
    assert vector["namespace"] == "existing/delegated"
    assert canonical_result_id(
        window_id=WINDOW_ID,
        execution_contract_version=EXECUTION_CONTRACT,
    ) == P01_RESULT_ID
    identity = _graph()["native_result"]
    assert str(identity.value) == P01_RESULT_ID
    assert identity.as_dict()["allocation"] == "existing_p0.1_canonical_result_id"


def test_canonical_observation_preserves_the_supplied_uuid() -> None:
    identity = _graph()["canonical_observation"]
    vector = _vectors()["canonical_observation"]
    assert str(identity.value) == vector["canonical_inputs"]["existing_observation_id"]["value"]
    assert identity.as_dict()["allocation"] == "existing_supplied_uuid"
    assert "namespace" not in identity.as_dict()


def test_set_digest_ordering_contract_is_explicit() -> None:
    graph = _graph()
    values = (graph["evidence_fact"], graph["evidence_binding"])
    assert unordered_identity_set_digest(
        values, contract="fixture.unordered.v1"
    ) == unordered_identity_set_digest(
        reversed(values), contract="fixture.unordered.v1"
    )
    assert ordered_identity_set_digest(
        values, contract="fixture.ordered.v1"
    ) != ordered_identity_set_digest(
        reversed(values), contract="fixture.ordered.v1"
    )


def test_scope_equality_is_exact_and_null_asset_is_not_a_wildcard() -> None:
    scope = _scope()
    same = _scope()
    concrete_asset = _scope(asset_id="asset-fixture")
    other_connection = _scope(connection_id="connection-fixture-b")
    assert scope == same
    assert scope.asset_id is None
    assert scope != concrete_asset
    assert scope != other_connection
    assert scope.digest == same.digest
    assert scope.digest != concrete_asset.digest
    assert scope.digest != other_connection.digest
    with pytest.raises(ContractValidationError, match="scope_asset_wildcard_forbidden"):
        _scope(asset_id="*")
    with pytest.raises(ContractValidationError, match="authority_scope_exact_match_required"):
        scope.require_exact(other_connection)


def test_cross_connection_identity_binding_is_rejected() -> None:
    graph = _graph()
    with pytest.raises(ValueError, match="authority_execution_chronology_scope_mismatch"):
        replace(graph["authority_execution"], scope=_scope(connection_id="connection-fixture-b"))
    with pytest.raises(ValueError, match="evidence_fact_scope_mismatch"):
        replace(graph["evidence_fact"], subject_scope=_scope(connection_id="connection-fixture-b"))
    with pytest.raises(ValueError, match="predecessor_scope_mismatch"):
        replace(
            graph["chronology_execution"],
            predecessor_reference_id=replace(
                graph["analytical_reference"],
                scope=_scope(connection_id="connection-fixture-b"),
            ),
        )
    with pytest.raises(ValueError, match="workflow_case_scope_base_mismatch"):
        replace(
            graph["workflow_case"],
            scope=replace(
                graph["workflow_case"].scope,
                connection_id="connection-fixture-b",
            ),
        )


def test_upstream_identities_have_no_downstream_cycle_inputs() -> None:
    graph = _graph()
    components = {
        name: {item.name for item in identity.canonical_components}
        for name, identity in graph.items()
    }
    downstream_names = {
        "analytical_finding_id",
        "evidence_fact_id",
        "evidence_binding_id",
        "canonical_package_id",
        "workflow_case_id",
    }
    for upstream in (
        "canonical_observation",
        "analytical_reference",
        "chronology_slot",
        "chronology_execution",
        "native_result",
        "authority_execution",
    ):
        assert components[upstream].isdisjoint(downstream_names)
    assert "authority_execution_id" not in components["analytical_reference"]
    assert "analytical_reference_id" not in components["authority_execution"]
