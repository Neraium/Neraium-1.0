from __future__ import annotations

from dataclasses import fields, replace
from datetime import datetime, timezone
from uuid import UUID

import pytest

from app.services.analytical_authority_contract import (
    AnalyticalReference,
    AuthoritativeAnalysis,
    AuthoritativeFinding,
    AuthorityStatus,
    ClassificationBinding,
    ConfidenceBinding,
    ConfidenceDimension,
    FindingConfidencePayload,
    EvidenceAdmissibility,
    EvidenceBinding,
    EvidenceFact,
    EvidenceRole,
    NativeExecutionBinding,
    P05DependencyState,
    PersistenceAssessment,
    PersistencePayload,
    ProjectionCursorReference,
    ProjectionEnvelope,
    TerminalOutcome,
    authoritative_evidence_set_digest,
    classification_output_digest,
    confidence_input_set_digest,
    confidence_output_digest,
    persistence_output_digest,
    validate_terminal_outcome_cardinality,
    CLASSIFICATION_OUTPUT_VERSION,
    CONFIDENCE_INPUT_VERSION,
    CONFIDENCE_OUTPUT_VERSION,
    PERSISTENCE_OUTPUT_VERSION,
)
from app.services.authority_contract_common import (
    AllowedLatenessConfiguration,
    AuthorityScope,
    Completeness,
    CompletenessState,
    ConfigurationStatus,
    ContractValidationError,
    ContractVersion,
    EvaluationCadenceConfiguration,
    ExistingStreamEnrollmentMode,
    ExistingStreamEnrollmentPolicy,
    FutureSkewConfiguration,
    GovernanceOwner,
    Integrity,
    LegacyCompatibilityPolicy,
    ParityCutoverPolicy,
    Provenance,
    ReplayPolicyConfiguration,
    ScopeLevel,
    TypedDigest,
    VersionBundle,
    canonical_json_bytes,
)
from app.services.authority_identity import (
    AnalyticalFindingIdentity,
    AnalyticalReferenceIdentity,
    AuthorityExecutionIdentity,
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
    ordered_identity_set_digest,
    unordered_identity_set_digest,
)
from app.services.canonical_authority_package import (
    CanonicalAuthorityPackageMetadata,
    ObjectFamilyCountDigestDescriptor,
    ObjectIndexDescriptor,
    PackageBuildMode,
    PackageCompletenessDescriptor,
    PackageIntegrityDescriptor,
    PackageVersionBundleBinding,
    SectionDescriptor,
    SectionIntegrityEntry,
)
from app.services.finding_confidence import build_finding_confidence
from app.services.telemetry_event_time import (
    ChronologyDisposition,
    ChronologyExecutionMode,
    ChronologyLifecycleState,
    ChronologyReadinessBinding,
    ChronologyReference,
    LearningFinalizationState,
    chronology_readiness_configuration_identity,
)


UTC = timezone.utc


def _digest(contract: str, marker: str) -> TypedDigest:
    return TypedDigest.from_value(contract, {"marker": marker})


def _integrity(contract: str, marker: str) -> Integrity:
    return Integrity(
        digest=_digest(contract, marker),
        contract_version=ContractVersion(f"{contract}-integrity", "1"),
    )


def _asset_scope(
    *, connection_id: str = "connection-a", asset_id: str | None = None
) -> AuthorityScope:
    return AuthorityScope(
        level=ScopeLevel.ASSET,
        tenant_id="tenant-a",
        workspace_id="workspace-a",
        resource_scope_id="resource-a",
        facility_id="facility-a",
        connection_id=connection_id,
        system_id="system-a",
        asset_id=asset_id,
        native_result_id=None,
        authority_execution_id=None,
        finding_id=None,
    )


def _projection_scope(graph: dict[str, object]) -> AuthorityScope:
    native = graph["native"]
    authority = graph["authority"]
    assert isinstance(native, NativeResultIdentity)
    assert isinstance(authority, AuthorityExecutionIdentity)
    scope = authority.scope
    return AuthorityScope(
        level=ScopeLevel.AUTHORITY_EXECUTION,
        tenant_id=scope.tenant_id,
        workspace_id=scope.workspace_id,
        resource_scope_id=scope.resource_scope_id,
        facility_id=scope.facility_id,
        connection_id=scope.connection_id,
        system_id=scope.system_id,
        asset_id=scope.asset_id,
        native_result_id=str(native.value),
        authority_execution_id=str(authority.value),
        finding_id=None,
    )


def _configured_cadence() -> EvaluationCadenceConfiguration:
    return EvaluationCadenceConfiguration(
        status=ConfigurationStatus.CONFIGURED,
        cadence_seconds=300,
        lookback_seconds=3600,
        utc_origin=datetime(2026, 1, 1, tzinfo=UTC),
        partial_edge_policy="fixture-edge-policy",
        overlapping_context_learning_policy="fixture-learning-policy",
    )


def _configured_lateness() -> AllowedLatenessConfiguration:
    return AllowedLatenessConfiguration(
        status=ConfigurationStatus.CONFIGURED,
        source_contract="fixture-source.v1",
        allowed_lateness_seconds=30,
    )


def _configured_future_skew() -> FutureSkewConfiguration:
    return FutureSkewConfiguration(
        status=ConfigurationStatus.CONFIGURED,
        source_contract="fixture-source.v1",
        maximum_future_skew_seconds=15,
        release_policy="fixture-reviewed-release",
    )


def _graph(
    *,
    connection_id: str = "connection-a",
    execution_mode: ChronologyExecutionMode = ChronologyExecutionMode.ACTIVE,
    lifecycle: ChronologyLifecycleState = ChronologyLifecycleState.ANALYZING,
    finalization: LearningFinalizationState = LearningFinalizationState.PENDING,
    disposition: ChronologyDisposition = ChronologyDisposition.NORMAL,
    include_analysis: bool = True,
) -> dict[str, object]:
    scope = _asset_scope(connection_id=connection_id)
    readiness_configuration = chronology_readiness_configuration_identity(
        _configured_cadence(), _configured_lateness(), _configured_future_skew()
    )
    versions = VersionBundle(
        (
            ContractVersion("analytical-authority", "1"),
            ContractVersion("authority-configuration", "1"),
            ContractVersion("finding-determination", "1"),
            ContractVersion("analytical-reference", "1"),
            ContractVersion("sii-method", "3"),
            ContractVersion("evidence-fact", "1"),
            ContractVersion(
                "finding-classification", "deterministic_finding_classification_v3"
            ),
            ContractVersion("classification-input", "1"),
            ContractVersion("finding-confidence", "finding-confidence-v1"),
            ContractVersion("persistence-method", "1"),
            ContractVersion("chronology-reference", "1"),
        )
    )
    reference_integrity_digest = _digest("reference-integrity.v1", "reference")
    reference_id = AnalyticalReferenceIdentity(
        scope=scope,
        producer_family="sii",
        model_id="model-a",
        model_version="3",
        learning_generation=7,
        configuration_generation=2,
        snapshot_id="snapshot-a",
        snapshot_digest=_digest("snapshot.v1", "snapshot"),
        causal_frontier_digest=_digest("frontier.v1", "frontier"),
        chronology_binding_digest=_digest("chronology-binding.v1", "binding"),
        method_identity=ContractVersion("sii-method", "3"),
        configuration_identity=_digest("analysis-config.v1", "config"),
        integrity_identity=reference_integrity_digest,
    )
    slot = ChronologySlotIdentity(
        scope=scope,
        authority_digest=_digest("chronology-authority.v1", "authority"),
        analysis_config_digest=_digest("analysis-config.v1", "config"),
        cadence_origin=datetime(2026, 1, 1, tzinfo=UTC),
        evaluation_endpoint=datetime(2026, 1, 2, 12, tzinfo=UTC),
        contribution_start=datetime(2026, 1, 2, 11, tzinfo=UTC),
        contribution_end=datetime(2026, 1, 2, 12, tzinfo=UTC),
        lookback_start=datetime(2026, 1, 1, 12, tzinfo=UTC),
        lookback_end=datetime(2026, 1, 2, 12, tzinfo=UTC),
        learning_generation=7,
    )
    predecessor_digest = _digest("predecessor-reference.v1", "predecessor")
    execution = ChronologyExecutionIdentity(
        chronology_slot_id=slot,
        analysis_generation=3,
        execution_mode=execution_mode.value,
        manifest_digest=_digest("manifest.v1", "manifest"),
        analytical_input_digest=_digest("analytical-input.v1", "input"),
        expected_progress_revision=11,
        predecessor_reference_id=reference_id,
        predecessor_reference_digest=predecessor_digest,
        authority_digest=_digest("chronology-authority.v1", "authority"),
        configuration_digest=readiness_configuration,
    )
    chronology = ChronologyReference(
        slot_identity=slot,
        execution_identity=execution,
        analysis_generation=3,
        learning_generation=7,
        execution_mode=execution_mode,
        predecessor_reference_id=reference_id,
        predecessor_reference_digest=predecessor_digest,
        selected_analytical_reference_id=reference_id,
        contribution_start=slot.contribution_start,
        contribution_end=slot.contribution_end,
        lookback_start=slot.lookback_start,
        lookback_end=slot.lookback_end,
        manifest_digest=execution.manifest_digest,
        analytical_input_digest=execution.analytical_input_digest,
        expected_progress_revision=11,
        lifecycle_state=lifecycle,
        learning_finalization=finalization,
        disposition=disposition,
        configuration_identity=execution.configuration_digest,
        version_identity=ContractVersion("chronology-reference.v1", "1"),
        integrity=_integrity("chronology-reference.v1", "chronology"),
    )
    native = NativeResultIdentity.from_window(
        scope=scope,
        window_id="00000000-0000-5000-8000-000000000101",
        execution_contract_version="analysis-window-execution.v1",
    )
    native_digest = _digest("native-terminal.v1", "native")
    authority = AuthorityExecutionIdentity(
        scope=scope,
        source_kind="connector",
        native_terminal_source_id=native.value,
        native_terminal_digest=native_digest,
        chronology_execution_id=execution,
        versions=versions,
    )
    reference = AnalyticalReference(
        identity=reference_id,
        scope=scope,
        producer_family="sii",
        state_identity="model-a",
        state_version="3",
        snapshot_identity="snapshot-a",
        chronology_generation=7,
        chronology_binding=reference_id.chronology_binding_digest,
        method_identity=reference_id.method_identity,
        configuration_identity=reference_id.configuration_identity,
        integrity=Integrity(
            reference_integrity_digest,
            ContractVersion("analytical-reference-integrity", "1"),
        ),
        versions=versions,
    )
    finding_id = AnalyticalFindingIdentity(
        authority_execution_id=authority,
        determination_contract=ContractVersion("finding-determination", "1"),
        finding_type="structural_change",
        affected_scope=scope,
        subject_identity="subject-a",
        relationship_metric_identities=("metric-a",),
        analytical_reference_id=reference_id,
    )
    fact_value_digest = _digest("fact-value.v1", "fact")
    fact_id = EvidenceFactIdentity(
        authority_execution_id=authority,
        fact_type="relationship_delta",
        producer_schema=ContractVersion("evidence-fact", "1"),
        subject_scope=scope,
        subject_identity="subject-a",
        dimensions=(("signal", "pressure"),),
        value_unit_event_time_digest=fact_value_digest,
        analytical_reference_id=reference_id,
    )
    fact = EvidenceFact(
        identity=fact_id,
        authority_execution_id=authority,
        scope=scope,
        fact_type="relationship_delta",
        schema=ContractVersion("evidence-fact", "1"),
        subject_identity="subject-a",
        value_integrity=Integrity(
            fact_value_digest, ContractVersion("fact-value-integrity", "1")
        ),
        trace_identity="trace-a",
        analytical_reference_id=reference_id,
        limitations=(),
        provenance=Provenance(
            "fixture-producer", ContractVersion("fixture-producer", "1"), ("source-a",)
        ),
        integrity=_integrity("evidence-fact.v1", "fact-record"),
        versions=versions,
    )
    qualification = ContractVersion("evidence-qualification", "1")
    binding_id = EvidenceBindingIdentity(
        authority_execution_id=authority,
        analytical_finding_id=finding_id,
        evidence_fact_id=fact_id,
        role=EvidenceRole.SUPPORTING.value,
        qualification=EvidenceAdmissibility.ADMITTED.value,
        qualification_contract=qualification,
        limitation_set_digest=TypedDigest.from_value("limitation-set.v1", ()),
    )
    binding = EvidenceBinding(
        identity=binding_id,
        authority_execution_id=authority,
        analytical_finding_id=finding_id,
        evidence_fact=fact,
        role=EvidenceRole.SUPPORTING,
        admissibility=EvidenceAdmissibility.ADMITTED,
        qualification_contract=qualification,
        limitations=(),
    )
    persistence_method = ContractVersion("persistence-method", "1")
    persistence_id = PersistenceAssessmentIdentity(
        analytical_finding_id=finding_id,
        method=persistence_method,
        chronology_execution_id=execution,
        event_time_window_digest=_digest("event-time-window.v1", "window"),
        exact_fact_set_digest=unordered_identity_set_digest(
            (fact_id,), contract="persistence-fact-set.v1"
        ),
    )
    persistence = PersistenceAssessment(
        identity=persistence_id,
        analytical_finding_id=finding_id,
        method=persistence_method,
        assessment_value="persistent",
        structured_payload=PersistencePayload.from_mapping(
            {
                "status": "persistent",
                "reason": "fixture persistence evidence",
                "evidence_refs": [str(binding_id.value)],
            }
        ),
        evidence_binding_ids=(binding_id,),
        analytical_reference_id=reference_id,
        limitations=(),
        dependency_state=P05DependencyState.NOT_REQUIRED,
        output_integrity=Integrity(
            persistence_output_digest(
                assessment_value="persistent",
                payload=PersistencePayload.from_mapping(
                    {
                        "status": "persistent",
                        "reason": "fixture persistence evidence",
                        "evidence_refs": [str(binding_id.value)],
                    }
                ),
                evidence_binding_ids=(binding_id,),
                analytical_reference_id=reference_id,
                limitations=(),
                dependency_state=P05DependencyState.NOT_REQUIRED,
            ),
            PERSISTENCE_OUTPUT_VERSION,
        ),
    )
    classification_id = ClassificationBindingIdentity(
        analytical_finding_id=finding_id,
        classifier_rule=ContractVersion(
            "finding-classification", "deterministic_finding_classification_v3"
        ),
        input_contract=ContractVersion("classification-input", "1"),
        ordered_binding_set_digest=ordered_identity_set_digest(
            (binding_id,), contract="classification-evidence-bindings.v1"
        ),
    )
    classification = ClassificationBinding(
        identity=classification_id,
        analytical_finding_id=finding_id,
        value="change",
        trace=("fixture-rule",),
        evidence_binding_ids=(binding_id,),
        input_integrity=Integrity(
            classification_id.ordered_binding_set_digest,
            classification_id.input_contract,
        ),
        output_integrity=Integrity(
            classification_output_digest(
                value="change",
                trace=("fixture-rule",),
                evidence_binding_ids=(binding_id,),
            ),
            CLASSIFICATION_OUTPUT_VERSION,
        ),
    )
    confidence_payload = FindingConfidencePayload.from_mapping(
        {
            "schema_version": "finding-confidence-v1",
            "change_detection": {"level": "high"},
            "interpretation": {"level": "high"},
            "persistence": persistence.structured_payload.as_dict(),
            "operating_context": {"status": "available"},
            "evidence_quality": {"level": "high"},
            "relationship_comparison": {"metric": "pearson_correlation"},
        }
    )
    confidence_dimensions = (
        ConfidenceDimension(
            name="evidence_quality",
            evidence_binding_ids=(binding_id,),
        ),
    )
    confidence_input = confidence_input_set_digest(
        dimensions=confidence_dimensions,
        persistence_assessment_id=persistence_id,
    )
    confidence_id = ConfidenceBindingIdentity(
        analytical_finding_id=finding_id,
        confidence_contract=ContractVersion(
            "finding-confidence", "finding-confidence-v1"
        ),
        exact_input_set_digest=confidence_input,
        persistence_assessment_id=persistence_id,
    )
    confidence = ConfidenceBinding(
        identity=confidence_id,
        analytical_finding_id=finding_id,
        structured_payload=confidence_payload,
        dimensions=confidence_dimensions,
        persistence_assessment=persistence,
        input_integrity=Integrity(
            confidence_input, CONFIDENCE_INPUT_VERSION
        ),
        dependency_state=P05DependencyState.NOT_REQUIRED,
        output_integrity=Integrity(
            confidence_output_digest(
                payload=confidence_payload,
                dimensions=confidence_dimensions,
                persistence_assessment_id=persistence_id,
                dependency_state=P05DependencyState.NOT_REQUIRED,
            ),
            CONFIDENCE_OUTPUT_VERSION,
        ),
    )
    finding = AuthoritativeFinding(
        identity=finding_id,
        authority_execution_id=authority,
        affected_scope=scope,
        category="analytical",
        finding_type="structural_change",
        subject_identity="subject-a",
        analytical_reference=reference,
        evidence_bindings=(binding,),
        classification=classification,
        confidence=confidence,
        persistence=persistence,
        limitations=(),
        versions=versions,
    )
    native_execution = NativeExecutionBinding(
        source_kind="connector",
        source_identity=native.value,
        source_integrity=Integrity(
            native_digest, ContractVersion("native-terminal-integrity", "1")
        ),
        terminal_state="completed",
        native_result_identity=native,
    )
    analysis = None
    if include_analysis:
        analysis = AuthoritativeAnalysis(
            authority_execution_id=authority,
            native_execution=native_execution,
            scope=scope,
            chronology_reference=chronology,
            analytical_reference=reference,
            terminal_outcome=TerminalOutcome.FINDINGS_PRESENT,
            authoritative_findings=(finding,),
            evidence_facts=(fact,),
            finding_set_identity=unordered_identity_set_digest(
                (finding_id,), contract="authoritative-finding-set.v1"
            ),
            evidence_set_identity=authoritative_evidence_set_digest((fact,), (binding,)),
            versions=versions,
            limitations=(),
            provenance=Provenance(
                "authority-fixture", ContractVersion("authority-fixture", "1"), (str(native.value),)
            ),
            integrity=_integrity("authoritative-analysis.v1", "analysis"),
            completeness=Completeness(
                CompletenessState.COMPLETE, ContractVersion("completeness", "1")
            ),
        )
    return locals()


def _zero_finding_analysis(
    graph: dict[str, object], outcome: TerminalOutcome
) -> AuthoritativeAnalysis:
    analysis = graph["analysis"]
    assert isinstance(analysis, AuthoritativeAnalysis)
    terminal_state = (
        outcome.value
        if outcome in {TerminalOutcome.PROCESSING_FAILURE, TerminalOutcome.INELIGIBLE_DATA}
        else "completed"
    )
    return replace(
        analysis,
        native_execution=replace(analysis.native_execution, terminal_state=terminal_state),
        terminal_outcome=outcome,
        authoritative_findings=(),
        evidence_facts=(),
        finding_set_identity=unordered_identity_set_digest(
            (), contract="authoritative-finding-set.v1"
        ),
        evidence_set_identity=authoritative_evidence_set_digest((), ()),
    )


def test_canonical_json_is_deterministic_and_mapping_order_independent() -> None:
    left = {"z": 1, "nested": {"beta": 2, "alpha": 1}}
    right = {"nested": {"alpha": 1, "beta": 2}, "z": 1}

    assert canonical_json_bytes(left) == canonical_json_bytes(right)
    assert canonical_json_bytes(left) == canonical_json_bytes(left)


def test_scope_is_exact_and_null_asset_is_not_empty_or_wildcard() -> None:
    null_asset = _asset_scope(asset_id=None)

    assert null_asset == _asset_scope(asset_id=None)
    assert null_asset != _asset_scope(asset_id="asset-a")
    assert null_asset.digest == _asset_scope(asset_id=None).digest
    with pytest.raises(ContractValidationError, match="asset_id_required"):
        _asset_scope(asset_id="")
    with pytest.raises(ContractValidationError, match="scope_asset_wildcard_forbidden"):
        _asset_scope(asset_id="*")
    with pytest.raises(ContractValidationError, match="authority_scope_exact_match_required"):
        null_asset.require_exact(_asset_scope(connection_id="connection-b"))


@pytest.mark.parametrize(
    ("configuration_type", "owner"),
    (
        (EvaluationCadenceConfiguration, GovernanceOwner.PRODUCT_SYSTEM_BEHAVIOR),
        (AllowedLatenessConfiguration, GovernanceOwner.CONNECTOR_DATA_QUALITY),
        (FutureSkewConfiguration, GovernanceOwner.CONNECTOR_DATA_QUALITY),
        (ReplayPolicyConfiguration, GovernanceOwner.SECURITY_ADMINISTRATIVE),
        (ExistingStreamEnrollmentPolicy, GovernanceOwner.MIGRATION_OPERATIONS),
        (LegacyCompatibilityPolicy, GovernanceOwner.PRODUCT_COMPATIBILITY),
        (ParityCutoverPolicy, GovernanceOwner.VALIDATION),
    ),
)
def test_every_required_configuration_fails_closed_with_owned_role(
    configuration_type: type[object], owner: GovernanceOwner
) -> None:
    configuration = configuration_type(ConfigurationStatus.REQUIRED_BUT_UNRESOLVED)

    assert configuration.owner is owner
    assert configuration.is_configured is False
    with pytest.raises(
        ContractValidationError,
        match=f"configuration_required_but_unresolved:{configuration_type.__name__}:owner={owner.value}",
    ):
        configuration.require_configured()


def test_configured_governance_contracts_retain_explicit_policy_fields() -> None:
    cadence = _configured_cadence()
    future = _configured_future_skew()
    replay = ReplayPolicyConfiguration(
        ConfigurationStatus.CONFIGURED,
        authorization_policy="fixture-authorization",
        hard_limit_executions=1,
        hard_limit_observations=2,
        hard_limit_bytes=3,
        hard_limit_cost_units=4,
        audit_retention_days=5,
        remediation_authority="fixture-remediation-role",
        promotion_authority="fixture-promotion-role",
    )
    enrollment = ExistingStreamEnrollmentPolicy(
        ConfigurationStatus.CONFIGURED,
        ExistingStreamEnrollmentMode.CLEAN_GENERATION,
    )
    parity = ParityCutoverPolicy(
        ConfigurationStatus.CONFIGURED,
        sustained_parity_duration_seconds=60,
        sample_threshold=10,
        scope_threshold=2,
        maximum_unexplained_critical=0,
        cutover_evidence_requirement="fixture-evidence",
    )

    assert cadence.require_configured().utc_origin == datetime(2026, 1, 1, tzinfo=UTC)
    assert cadence.partial_edge_policy == "fixture-edge-policy"
    assert future.require_configured().release_policy == "fixture-reviewed-release"
    assert replay.require_configured().hard_limit_executions == 1
    assert replay.audit_retention_days == 5
    assert enrollment.require_configured().enrollment_mode is ExistingStreamEnrollmentMode.CLEAN_GENERATION
    assert parity.require_configured().maximum_unexplained_critical == 0
    assert parity.cutover_evidence_requirement == "fixture-evidence"


def test_chronology_has_no_processing_time_fallback_and_is_required_by_analysis() -> None:
    graph = _graph()
    chronology_field_names = {item.name for item in fields(ChronologyReference)}
    analysis = graph["analysis"]
    assert isinstance(analysis, AuthoritativeAnalysis)

    assert not chronology_field_names.intersection(
        {"processing_time", "processing_timestamp", "wall_clock", "now"}
    )
    values = {item.name: getattr(analysis, item.name) for item in fields(analysis)}
    values.pop("chronology_reference")
    with pytest.raises(TypeError, match="chronology_reference"):
        AuthoritativeAnalysis(**values)


def test_chronology_can_carry_approved_bootstrap_reference_without_predecessor() -> None:
    graph = _graph(include_analysis=False)
    chronology = graph["chronology"]
    execution = graph["execution"]
    assert isinstance(chronology, ChronologyReference)
    assert isinstance(execution, ChronologyExecutionIdentity)

    bootstrap_execution = ChronologyExecutionIdentity(
        chronology_slot_id=execution.chronology_slot_id,
        analysis_generation=execution.analysis_generation,
        execution_mode=execution.execution_mode,
        manifest_digest=execution.manifest_digest,
        analytical_input_digest=execution.analytical_input_digest,
        expected_progress_revision=0,
        predecessor_reference_id=None,
        predecessor_reference_digest=None,
        authority_digest=execution.authority_digest,
        configuration_digest=execution.configuration_digest,
    )
    bootstrap = replace(
        chronology,
        execution_identity=bootstrap_execution,
        predecessor_reference_id=None,
        predecessor_reference_digest=None,
        expected_progress_revision=0,
    )

    assert bootstrap.predecessor_reference_id is None
    assert bootstrap.selected_analytical_reference_id == graph["reference_id"]
    assert bootstrap.require_authority_bindable() is bootstrap


@pytest.mark.parametrize(
    ("mode", "lifecycle", "finalization", "disposition", "bindable"),
    (
        (
            ChronologyExecutionMode.ACTIVE,
            ChronologyLifecycleState.BLOCKED,
            LearningFinalizationState.BLOCKED,
            ChronologyDisposition.OLD_AFTER_NEW_REJECTED,
            False,
        ),
        (
            ChronologyExecutionMode.HISTORICAL_NON_LEARNING,
            ChronologyLifecycleState.FINALIZED,
            LearningFinalizationState.NOT_APPLICABLE,
            ChronologyDisposition.HISTORICAL_NON_LEARNING,
            True,
        ),
        (
            ChronologyExecutionMode.ACTIVE,
            ChronologyLifecycleState.ANALYZING,
            LearningFinalizationState.PENDING,
            ChronologyDisposition.RETRY_REUSE,
            True,
        ),
        (
            ChronologyExecutionMode.ACTIVE,
            ChronologyLifecycleState.PUBLISHED_PENDING_LEARNING,
            LearningFinalizationState.PENDING,
            ChronologyDisposition.LATE_AFTER_PUBLICATION,
            True,
        ),
        (
            ChronologyExecutionMode.ACTIVE,
            ChronologyLifecycleState.FINALIZED,
            LearningFinalizationState.FINALIZED,
            ChronologyDisposition.NORMAL,
            True,
        ),
        (
            ChronologyExecutionMode.ACTIVE,
            ChronologyLifecycleState.ANALYZING,
            LearningFinalizationState.PENDING,
            ChronologyDisposition.LATE_BEFORE_FREEZE,
            True,
        ),
        (
            ChronologyExecutionMode.ACTIVE,
            ChronologyLifecycleState.BLOCKED,
            LearningFinalizationState.BLOCKED,
            ChronologyDisposition.FUTURE_QUARANTINED,
            False,
        ),
    ),
)
def test_chronology_risk_dispositions_are_representable_without_transitions(
    mode: ChronologyExecutionMode,
    lifecycle: ChronologyLifecycleState,
    finalization: LearningFinalizationState,
    disposition: ChronologyDisposition,
    bindable: bool,
) -> None:
    chronology = _graph(
        execution_mode=mode,
        lifecycle=lifecycle,
        finalization=finalization,
        disposition=disposition,
        include_analysis=False,
    )["chronology"]
    assert isinstance(chronology, ChronologyReference)

    assert chronology.disposition is disposition
    assert chronology.is_authority_bindable is bindable
    if not bindable:
        with pytest.raises(ContractValidationError, match="not_authority_bindable"):
            chronology.require_authority_bindable()


def test_active_readiness_fails_when_architecture_policy_is_unresolved() -> None:
    chronology = _graph()["chronology"]
    assert isinstance(chronology, ChronologyReference)

    with pytest.raises(ContractValidationError, match="EvaluationCadenceConfiguration"):
        ChronologyReadinessBinding(
            chronology_reference=chronology,
            source_scope=chronology.scope,
            source_contract="fixture-source.v1",
            active_readiness_asserted=True,
            evaluation_cadence=EvaluationCadenceConfiguration(
                ConfigurationStatus.REQUIRED_BUT_UNRESOLVED
            ),
            allowed_lateness=_configured_lateness(),
            future_skew=_configured_future_skew(),
        )


def test_active_readiness_rejects_cross_source_scope_and_configuration() -> None:
    chronology = _graph()["chronology"]
    assert isinstance(chronology, ChronologyReference)
    base = ChronologyReadinessBinding(
        chronology_reference=chronology,
        source_scope=chronology.scope,
        source_contract="fixture-source.v1",
        active_readiness_asserted=True,
        evaluation_cadence=_configured_cadence(),
        allowed_lateness=_configured_lateness(),
        future_skew=_configured_future_skew(),
    )
    assert base.active_readiness_asserted

    with pytest.raises(ContractValidationError, match="source_contract_mismatch"):
        replace(base, source_contract="unrelated-source")
    with pytest.raises(ContractValidationError, match="exact_match_required"):
        replace(base, source_scope=_asset_scope(connection_id="connection-b"))
    with pytest.raises(ContractValidationError, match="configuration_identity_mismatch"):
        replace(base, evaluation_cadence=replace(_configured_cadence(), cadence_seconds=600))


@pytest.mark.parametrize("outcome", tuple(TerminalOutcome))
def test_terminal_outcome_accepts_each_mutually_exclusive_valid_cardinality(
    outcome: TerminalOutcome,
) -> None:
    count = 1 if outcome is TerminalOutcome.FINDINGS_PRESENT else 0
    assert validate_terminal_outcome_cardinality(outcome, count) is outcome


@pytest.mark.parametrize("outcome", tuple(TerminalOutcome))
def test_terminal_outcome_rejects_invalid_cardinality(outcome: TerminalOutcome) -> None:
    invalid_count = 0 if outcome is TerminalOutcome.FINDINGS_PRESENT else 1
    with pytest.raises(ContractValidationError):
        validate_terminal_outcome_cardinality(outcome, invalid_count)


def test_canonical_completeness_rejects_partial_and_unavailable() -> None:
    version = ContractVersion("completeness", "1")

    with pytest.raises(ContractValidationError, match="canonical_authority_must_be_complete"):
        Completeness(CompletenessState.PARTIAL, version, ("bounded",)).require_canonical_authority()
    with pytest.raises(ContractValidationError, match="canonical_authority_must_be_complete"):
        Completeness(CompletenessState.UNAVAILABLE, version, ("not-produced",)).require_canonical_authority()


def test_evidence_is_exactly_execution_finding_and_connection_bound() -> None:
    graph = _graph()
    other = _graph(connection_id="connection-b")
    fact_id = graph["fact_id"]
    authority = graph["authority"]
    assert isinstance(fact_id, EvidenceFactIdentity)
    assert isinstance(authority, AuthorityExecutionIdentity)

    with pytest.raises(ValueError, match="evidence_fact_scope_mismatch"):
        EvidenceFactIdentity(
            authority_execution_id=authority,
            fact_type=fact_id.fact_type,
            producer_schema=fact_id.producer_schema,
            subject_scope=other["scope"],
            subject_identity=fact_id.subject_identity,
            dimensions=fact_id.dimensions,
            value_unit_event_time_digest=fact_id.value_unit_event_time_digest,
            analytical_reference_id=None,
        )
    with pytest.raises(
        ContractValidationError,
        match="evidence_binding_authority_mismatch|evidence_binding_cross_execution_forbidden",
    ):
        replace(
            graph["binding"],
            authority_execution_id=other["authority"],
        )
    with pytest.raises(ContractValidationError, match="finding_mismatch"):
        replace(graph["binding"], analytical_finding_id=other["finding_id"])


def test_downstream_bindings_reject_another_findings_evidence() -> None:
    graph = _graph()
    other = _graph(connection_id="connection-b")
    finding_id = graph["finding_id"]
    other_binding_id = other["binding_id"]
    classification = graph["classification"]
    persistence = graph["persistence"]
    confidence = graph["confidence"]
    assert isinstance(finding_id, AnalyticalFindingIdentity)
    assert isinstance(other_binding_id, EvidenceBindingIdentity)
    assert isinstance(classification, ClassificationBinding)
    assert isinstance(persistence, PersistenceAssessment)
    assert isinstance(confidence, ConfidenceBinding)

    cross_classification_id = ClassificationBindingIdentity(
        analytical_finding_id=finding_id,
        classifier_rule=classification.identity.classifier_rule,
        input_contract=classification.identity.input_contract,
        ordered_binding_set_digest=ordered_identity_set_digest(
            (other_binding_id,), contract="classification-evidence-bindings.v1"
        ),
    )
    with pytest.raises(ContractValidationError, match="cross_finding"):
        replace(
            classification,
            identity=cross_classification_id,
            evidence_binding_ids=(other_binding_id,),
        )

    cross_persistence_id = PersistenceAssessmentIdentity(
        analytical_finding_id=finding_id,
        method=persistence.method,
        chronology_execution_id=graph["execution"],
        event_time_window_digest=persistence.identity.event_time_window_digest,
        exact_fact_set_digest=unordered_identity_set_digest(
            (other_binding_id.evidence_fact_id,), contract="persistence-fact-set.v1"
        ),
    )
    with pytest.raises(ContractValidationError, match="cross_finding"):
        replace(
            persistence,
            identity=cross_persistence_id,
            evidence_binding_ids=(other_binding_id,),
        )

    with pytest.raises(ContractValidationError, match="cross_finding"):
        replace(
            confidence,
            dimensions=(
                ConfidenceDimension(
                    name="evidence_quality",
                    evidence_binding_ids=(other_binding_id,),
                ),
            ),
        )


def test_narrative_alone_cannot_satisfy_typed_evidence_contract() -> None:
    fact = _graph()["fact"]
    assert isinstance(fact, EvidenceFact)

    with pytest.raises(ContractValidationError, match="evidence_fact_identity_required"):
        replace(fact, identity="narrative explanation is not a fact")


def test_finding_has_one_v3_classification_v1_confidence_and_persistence_binding() -> None:
    finding = _graph()["finding"]
    assert isinstance(finding, AuthoritativeFinding)

    finding_fields = {item.name for item in fields(finding)}
    assert {"classification", "confidence", "persistence"} <= finding_fields
    assert finding.classification.identity.classifier_rule.version == "deterministic_finding_classification_v3"
    assert finding.confidence.identity.confidence_contract.version == "finding-confidence-v1"
    assert finding.confidence.persistence_assessment is finding.persistence
    assert finding.confidence.as_dict()["aggregate"] == "aggregate_not_defined"


def test_classification_and_confidence_reject_wrong_contract_same_version() -> None:
    graph = _graph()
    classification = graph["classification"]
    confidence = graph["confidence"]
    assert isinstance(classification, ClassificationBinding)
    assert isinstance(confidence, ConfidenceBinding)

    wrong_classification_id = replace(
        classification.identity,
        classifier_rule=ContractVersion(
            "unrelated-contract", "deterministic_finding_classification_v3"
        ),
    )
    with pytest.raises(ContractValidationError, match="classification_rule_version_mismatch"):
        replace(classification, identity=wrong_classification_id)

    wrong_confidence_id = replace(
        confidence.identity,
        confidence_contract=ContractVersion("unrelated-contract", "finding-confidence-v1"),
    )
    with pytest.raises(ContractValidationError, match="confidence_contract_version_mismatch"):
        replace(confidence, identity=wrong_confidence_id)


def test_binding_outputs_are_integrity_bound_under_stable_identity() -> None:
    graph = _graph()
    classification = graph["classification"]
    persistence = graph["persistence"]
    confidence = graph["confidence"]
    assert isinstance(classification, ClassificationBinding)
    assert isinstance(persistence, PersistenceAssessment)
    assert isinstance(confidence, ConfidenceBinding)

    with pytest.raises(ContractValidationError, match="classification_output_integrity_mismatch"):
        replace(classification, value="different-classification")
    with pytest.raises(ContractValidationError, match="persistence_output_integrity_mismatch"):
        replace(
            persistence,
            structured_payload=PersistencePayload.from_mapping(
                {
                    "status": persistence.assessment_value,
                    "reason": "different reason under the same identity",
                    "evidence_refs": [],
                }
            ),
        )
    with pytest.raises(ContractValidationError, match="confidence_exact_input_set_mismatch"):
        replace(
            confidence,
            dimensions=(
                ConfidenceDimension(
                    name="interpretation",
                    evidence_binding_ids=confidence.dimensions[0].evidence_binding_ids,
                ),
            ),
        )
    changed_payload = confidence.structured_payload.as_dict()
    changed_payload["evidence_quality"] = {"level": "low"}
    with pytest.raises(ContractValidationError, match="confidence_output_integrity_mismatch"):
        replace(
            confidence,
            structured_payload=FindingConfidencePayload.from_mapping(changed_payload),
        )


def test_existing_finding_confidence_v1_payload_maps_losslessly() -> None:
    produced = build_finding_confidence(
        classification_type="relationship_change",
        classification_confidence="high",
        classification_reason="fixture classification",
        data_confidence={"confidence_level": "high", "evidence_refs": ["data-a"]},
        sensor_health=[],
        operating_mode={"match": "strong", "evidence_refs": ["mode-a"]},
        persistence={
            "status": "persistent",
            "reason": "fixture persistence",
            "evidence_refs": ["persistence-a"],
        },
        relationship_evidence={
            "baseline_sample_size": 10,
            "recent_sample_size": 10,
            "baseline_value": 0.8,
            "current_value": 0.2,
            "confidence_score": 0.9,
            "evidence_refs": ["relationship-a"],
        },
    )
    payload = FindingConfidencePayload.from_mapping(produced)

    assert payload.as_dict() == produced
    assert payload.as_dict()["schema_version"] == "finding-confidence-v1"


def test_analysis_rejects_source_kind_and_authority_version_rebinding() -> None:
    graph = _graph()
    analysis = graph["analysis"]
    assert isinstance(analysis, AuthoritativeAnalysis)

    with pytest.raises(ContractValidationError, match="native_source_kind_mismatch"):
        replace(
            analysis,
            native_execution=replace(analysis.native_execution, source_kind="different-source"),
        )

    with pytest.raises(ContractValidationError, match="authority_versions_mismatch"):
        replace(
            analysis,
            versions=VersionBundle((ContractVersion("different-authority", "1"),)),
        )


def test_authority_execution_requires_aggregate_determination_and_configuration_versions() -> None:
    graph = _graph()
    authority = graph["authority"]
    assert isinstance(authority, AuthorityExecutionIdentity)

    with pytest.raises(ContractValidationError, match="required_contract_missing"):
        replace(
            authority,
            versions=VersionBundle((ContractVersion("analytical-authority", "1"),)),
        )


def test_p0_5_dependency_blocks_canonical_authoritative_analysis() -> None:
    graph = _graph()
    analysis = graph["analysis"]
    finding = graph["finding"]
    persistence = graph["persistence"]
    confidence = graph["confidence"]
    assert isinstance(analysis, AuthoritativeAnalysis)
    assert isinstance(finding, AuthoritativeFinding)
    assert isinstance(persistence, PersistenceAssessment)
    assert isinstance(confidence, ConfidenceBinding)
    blocked_persistence = replace(
        persistence,
        dependency_state=P05DependencyState.REQUIRED_NON_LOSSLESS_PERSISTENCE,
        output_integrity=Integrity(
            persistence_output_digest(
                assessment_value=persistence.assessment_value,
                payload=persistence.structured_payload,
                evidence_binding_ids=persistence.evidence_binding_ids,
                analytical_reference_id=persistence.analytical_reference_id,
                limitations=persistence.limitations,
                dependency_state=P05DependencyState.REQUIRED_NON_LOSSLESS_PERSISTENCE,
            ),
            PERSISTENCE_OUTPUT_VERSION,
        ),
    )
    blocked_confidence = replace(confidence, persistence_assessment=blocked_persistence)
    blocked_finding = replace(
        finding,
        persistence=blocked_persistence,
        confidence=blocked_confidence,
    )

    with pytest.raises(ContractValidationError, match="blocked_by_p0_5_dependency"):
        replace(analysis, authoritative_findings=(blocked_finding,))


def test_authoritative_analysis_happy_outcomes_cover_findings_and_zero_findings() -> None:
    graph = _graph()
    assert isinstance(graph["analysis"], AuthoritativeAnalysis)

    for outcome in (
        TerminalOutcome.STABLE_NO_CHANGE,
        TerminalOutcome.INSUFFICIENT_EVIDENCE,
        TerminalOutcome.PROCESSING_FAILURE,
        TerminalOutcome.INELIGIBLE_DATA,
    ):
        assert _zero_finding_analysis(graph, outcome).terminal_outcome is outcome


def _projection(
    graph: dict[str, object], state: CompletenessState
) -> ProjectionEnvelope:
    scope = _projection_scope(graph)
    completeness_version = ContractVersion("projection-completeness", "1")
    omissions = () if state is CompletenessState.COMPLETE else ("bounded",)
    returned = (
        (graph["finding_id"].value,)  # type: ignore[union-attr]
        if state is not CompletenessState.UNAVAILABLE
        else ()
    )
    cursor = (
        ProjectionCursorReference(
            "cursor-a",
            ContractVersion("projection-cursor", "1"),
            _integrity("projection-cursor.v1", "cursor"),
        )
        if state is CompletenessState.PARTIAL
        else None
    )
    return ProjectionEnvelope(
        status=(
            AuthorityStatus.UNAVAILABLE
            if state is CompletenessState.UNAVAILABLE
            else AuthorityStatus.AUTHORITATIVE
        ),
        scope=scope,
        native_source_identity=graph["authority"].native_terminal_source_id,
        native_result_identity=graph["native"],
        authority_execution_id=graph["authority"],
        package_id=None,
        finding_id=None,
        completeness=Completeness(state, completeness_version, omissions),
        total=None if state is CompletenessState.UNAVAILABLE else 2 if state is CompletenessState.PARTIAL else 1,
        returned_count=len(returned),
        returned_ids=returned,
        authoritative_set_digest=(
            None if state is CompletenessState.UNAVAILABLE else _digest("projection-set.v1", "set")
        ),
        omissions=omissions,
        cursor=cursor,
        integrity=_integrity("projection.v1", state.value),
        etag_inputs=(_digest("projection-etag.v1", state.value),),
        version=ContractVersion("authority-projection-envelope.v1", "1"),
    )


@pytest.mark.parametrize("state", tuple(CompletenessState))
def test_projection_envelope_represents_complete_partial_and_unavailable(
    state: CompletenessState,
) -> None:
    projection = _projection(_graph(), state)

    assert projection.completeness.state is state
    if state is CompletenessState.PARTIAL:
        assert projection.cursor is not None
    if state is CompletenessState.UNAVAILABLE:
        assert projection.returned_count == 0


def test_projection_completeness_invariants_fail_closed() -> None:
    complete = _projection(_graph(), CompletenessState.COMPLETE)

    with pytest.raises(ContractValidationError, match="complete_projection_count_or_omission_mismatch"):
        replace(complete, total=2)
    with pytest.raises(ContractValidationError, match="unavailable_projection_cannot_return_objects"):
        replace(
            complete,
            status=AuthorityStatus.UNAVAILABLE,
            completeness=Completeness(
                CompletenessState.UNAVAILABLE,
                complete.completeness.contract_version,
                ("unavailable",),
            ),
            omissions=("unavailable",),
        )
    with pytest.raises(ContractValidationError, match="native_source_authority_mismatch"):
        replace(
            complete,
            native_source_identity=UUID("00000000-0000-5000-8000-000000000808"),
        )


def test_projection_can_represent_pre_artifact_terminal_source_decision() -> None:
    graph = _graph()
    authority = graph["authority"]
    assert isinstance(authority, AuthorityExecutionIdentity)
    decision_id = UUID("00000000-0000-5000-8000-000000000909")
    failure_authority = AuthorityExecutionIdentity(
        scope=authority.scope,
        source_kind="processing_failure_decision",
        native_terminal_source_id=decision_id,
        native_terminal_digest=_digest("processing-failure-decision.v1", "failure"),
        chronology_execution_id=authority.chronology_execution_id,
        versions=authority.versions,
    )
    source_scope = replace(
        _projection_scope(graph),
        native_result_id=None,
        authority_execution_id=str(failure_authority.value),
    )
    projection = replace(
        _projection(graph, CompletenessState.UNAVAILABLE),
        scope=source_scope,
        native_source_identity=decision_id,
        native_result_identity=None,
        authority_execution_id=failure_authority,
    )

    assert projection.native_result_identity is None
    assert projection.native_source_identity == decision_id
    assert projection.scope.native_result_id is None


def test_analytical_reference_identity_has_no_display_alias_equality_input() -> None:
    reference = _graph()["reference_id"]
    assert isinstance(reference, AnalyticalReferenceIdentity)

    assert "display_alias" not in {item.name for item in fields(reference)}
    assert "display_alias" not in reference.as_dict()


def _package_fixture(graph: dict[str, object]) -> dict[str, object]:
    authority = graph["authority"]
    assert isinstance(authority, AuthorityExecutionIdentity)
    scope = _projection_scope(graph)
    package_schema = ContractVersion("canonical-authority-package", "1")
    package_id = CanonicalPackageIdentity(authority, package_schema)
    section_schema = ContractVersion("canonical-section", "1")
    section_id = SectionIdentity(package_id, "authority", section_schema, 0)
    section_integrity = _integrity("canonical-section.v1", "section")
    complete = Completeness(
        CompletenessState.COMPLETE, ContractVersion("package-completeness", "1")
    )
    section = SectionDescriptor(
        package_id=package_id,
        scope=scope,
        identity=section_id,
        section_family="authority",
        section_schema=section_schema,
        sequence_number=0,
        encoding_contract=ContractVersion("canonical-json", "1"),
        object_count=1,
        stored_size_bytes=10,
        uncompressed_size_bytes=10,
        integrity=section_integrity,
        completeness=complete,
    )
    index = ObjectIndexDescriptor(
        package_id=package_id,
        scope=scope,
        section_id=section_id,
        object_family="analytical_finding",
        object_identity=graph["finding_id"],
        ordinal=0,
        record_size_bytes=10,
        object_integrity=_integrity("canonical-object.v1", "finding"),
        completeness=complete,
    )
    set_digests = {
        "analytical_finding": unordered_identity_set_digest(
            (graph["finding_id"],), contract="package-finding-set.v1"
        ),
        "evidence_fact": unordered_identity_set_digest(
            (graph["fact_id"],), contract="package-fact-set.v1"
        ),
        "evidence_binding": unordered_identity_set_digest(
            (graph["binding_id"],), contract="package-binding-set.v1"
        ),
    }
    families = tuple(
        ObjectFamilyCountDigestDescriptor(name, 1, 1, digest, digest, complete)
        for name, digest in sorted(set_digests.items())
    )
    section_set_digest = unordered_identity_set_digest(
        (section_id,), contract="package-section-set.v1"
    )
    completeness = PackageCompletenessDescriptor(
        package_id,
        complete,
        1,
        1,
        section_set_digest,
        section_set_digest,
        families,
    )
    integrity = PackageIntegrityDescriptor(
        package_id,
        ContractVersion("package-integrity", "1"),
        _digest("package-manifest.v1", "manifest"),
        _digest("package-payload.v1", "payload"),
        (SectionIntegrityEntry(section_id, section_integrity.digest),),
        (),
    )
    schema_versions = (
        package_schema,
        ContractVersion("canonical-authority-package-metadata", "1"),
        ContractVersion("canonical-authority-section-descriptor", "1"),
        ContractVersion("canonical-authority-object-index", "1"),
        ContractVersion("canonical-authority-package-integrity", "1"),
        ContractVersion("canonical-authority-package-completeness", "1"),
    )
    versions = PackageVersionBundleBinding(*schema_versions, VersionBundle(schema_versions))
    metadata = CanonicalAuthorityPackageMetadata(
        identity=package_id,
        scope=scope,
        native_execution=graph["native_execution"],
        authority_execution_id=authority,
        chronology_reference=graph["chronology"],
        analytical_reference_id=graph["reference_id"],
        terminal_outcome=TerminalOutcome.FINDINGS_PRESENT,
        finding_count=1,
        finding_set_digest=set_digests["analytical_finding"],
        fact_count=1,
        fact_set_digest=set_digests["evidence_fact"],
        binding_count=1,
        binding_set_digest=set_digests["evidence_binding"],
        sections=(section,),
        versions=versions,
        build_mode=PackageBuildMode.SHADOW,
        authority_status=AuthorityStatus.SHADOW,
        integrity=integrity,
        completeness=completeness,
    )
    return locals()


def test_package_metadata_section_object_integrity_and_completeness_are_pure() -> None:
    package = _package_fixture(_graph())
    metadata = package["metadata"]
    index = package["index"]
    section = package["section"]
    assert isinstance(metadata, CanonicalAuthorityPackageMetadata)
    assert isinstance(index, ObjectIndexDescriptor)
    assert isinstance(section, SectionDescriptor)

    assert metadata.section_count == 1
    assert index.validate_section(section) is index
    assert metadata.completeness.require_complete() is metadata.completeness
    assert metadata.canonical_bytes == metadata.canonical_bytes


def test_package_contracts_reject_partial_canonical_section_and_bad_index() -> None:
    package = _package_fixture(_graph())
    section = package["section"]
    index = package["index"]
    assert isinstance(section, SectionDescriptor)
    assert isinstance(index, ObjectIndexDescriptor)

    with pytest.raises(ContractValidationError, match="canonical_authority_must_be_complete"):
        replace(
            section,
            completeness=Completeness(
                CompletenessState.PARTIAL,
                ContractVersion("package-completeness", "1"),
                ("object-omitted",),
            ),
        )
    with pytest.raises(ContractValidationError, match="ordinal_out_of_range"):
        replace(index, ordinal=1).validate_section(section)
    partial = Completeness(
        CompletenessState.PARTIAL,
        ContractVersion("package-completeness", "1"),
        ("bounded",),
    )
    with pytest.raises(ContractValidationError, match="canonical_package_partial_forbidden"):
        replace(package["families"][0], completeness=partial)
    with pytest.raises(ContractValidationError, match="canonical_package_partial_forbidden"):
        replace(package["completeness"], completeness=partial)
    with pytest.raises(ContractValidationError, match="cannot_confer_authority"):
        replace(package["metadata"], authority_status=AuthorityStatus.AUTHORITATIVE)


def test_package_outcome_rejects_inconsistent_native_terminal_state() -> None:
    metadata = _package_fixture(_graph())["metadata"]
    assert isinstance(metadata, CanonicalAuthorityPackageMetadata)

    with pytest.raises(ContractValidationError, match="completed_native_execution"):
        replace(
            metadata,
            native_execution=replace(
                metadata.native_execution, terminal_state="processing_failure"
            ),
        )
