from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.contracts import ContractModel, EmailAddress, Identifier, OptionalNote, SecretText, ShortText, validate_http_url, validate_utc_timestamp


class JobProgressOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    stage: str
    label: str
    status: Literal["pending", "queued", "processing", "waiting", "retrying", "completed", "failed", "cancelled"]
    completed_units: int | None = Field(default=None, ge=0)
    total_units: int | None = Field(default=None, ge=0)
    percent_complete: int | None = Field(default=None, ge=0, le=100)
    unit_type: str | None = None
    message: str | None = None
    started_at: str | None = None
    updated_at: str | None = None
    completed_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("started_at", "updated_at", "completed_at", mode="before")
    @classmethod
    def validate_timestamps(cls, value: str | None) -> str | None:
        return validate_utc_timestamp(value)


class JobProgressStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    status: Literal["pending", "queued", "processing", "waiting", "retrying", "completed", "failed", "cancelled"]
    completed_work_units: int = Field(ge=0)
    total_work_units: int = Field(ge=0)
    percent_complete: int = Field(ge=0, le=100)


class JobProgress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["job-progress.v1"]
    job_id: str
    workflow: str
    status: Literal["queued", "processing", "waiting", "retrying", "completed", "failed", "cancelled"]
    stage: str | None = None
    substage: str | None = None
    completed_units: int | None = Field(default=None, ge=0)
    total_units: int | None = Field(default=None, ge=0)
    percent_complete: int | None = Field(default=None, ge=0, le=100)
    unit_type: str | None = None
    message: str
    started_at: str
    updated_at: str
    elapsed_seconds: int = Field(ge=0)
    last_worker_heartbeat_at: str | None = None
    seconds_since_worker_heartbeat: int | None = Field(default=None, ge=0)
    seconds_since_update: int = Field(ge=0)
    stalled: bool
    retryable: bool | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    workflow_steps: list[JobProgressStep] = Field(default_factory=list)
    operations: list[JobProgressOperation] = Field(default_factory=list)
    overall_percent_complete: int = Field(ge=0, le=100)
    overall_basis: Literal["equal_completed_declared_substages"]
    visibility_message: str | None = None

    @field_validator("started_at", "updated_at", "last_worker_heartbeat_at", mode="before")
    @classmethod
    def validate_timestamps(cls, value: str | None) -> str | None:
        return validate_utc_timestamp(value)


class UploadAcceptedResponse(BaseModel):
    job_id: str
    dataset_id: str | None = None
    analysis_state: str = "analysis_queued"
    status: str
    progress: int
    processing_state: str
    error_type: str | None = None
    filename: str
    message: str
    status_url: str
    result_url: str | None = None
    file_size_bytes: int
    stage: str | None = None
    percent: int | None = None
    bytes_processed: int = 0
    rows_processed: int = 0
    result_available: bool = False
    sii_completed: bool = False
    workflow: Literal[
        "create_baseline",
        "analyze_new_data",
        "extend_baseline",
        "legacy_analysis",
        "historical_review",
    ] = "legacy_analysis"
    baseline_result_url: str | None = None
    job_progress: JobProgress | None = None



class UploadStatusResponse(BaseModel): 
    model_config = ConfigDict(extra="allow")

    job_id: str | None
    dataset_id: str | None = None
    analysis_state: str = "no_dataset"
    status: str
    progress: int
    processing_state: str
    progress_label: str | None = None
    stage: str | None = None
    percent: int | None = None
    message: str
    error_type: str | None = None
    filename: str | None = None
    file_size_bytes: int = 0
    bytes_processed: int = 0
    rows_processed: int = 0
    columns_detected: int = 0
    chunk_count: int = 0
    memory_estimate_bytes: int = 0
    processing_duration_seconds: float | None = None
    engine_runtime_seconds: float | None = None
    runner_used: bool = False
    runner_module: str | None = None
    core_engine: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    result_available: bool = False
    first_usable_available: bool = False
    sii_completed: bool = False
    replay_ready: bool = False
    replay_frame_count: int = 0
    sii_completion_artifacts: dict[str, bool] = Field(default_factory=dict)
    timings: dict[str, Any] = Field(default_factory=dict) 
    result_summary: dict[str, Any] | None = None 
    ingest_request_id: str | None = None
    request_id: str | None = None
    workflow: Literal[
        "create_baseline",
        "analyze_new_data",
        "extend_baseline",
        "legacy_analysis",
        "historical_review",
    ] = "legacy_analysis"
    workflow_state: str | None = None
    baseline_candidate_created: bool = False
    baseline_activation_state: str | None = None
    baselineId: str | None = None
    workspacePath: str | None = None
    createdAt: str | None = None
    job_progress: JobProgress | None = None


class BaselineCreationResponse(BaseModel):
    status: Literal["completed"]
    datasetId: str
    jobId: str
    baselineId: str
    workspacePath: str
    createdAt: str
    portfolioId: str | None = None
    systemId: str | None = None


class BaselineSuitabilityResponse(BaseModel):
    contract_version: Literal["baseline-suitability.v1"]
    decision: Literal["suitable", "conditionally_suitable", "unsuitable"]
    score: int = Field(ge=0, le=100)
    eligible_for_activation: bool
    dimensions: dict[str, int | float] = Field(default_factory=dict)
    blocking_reasons: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class BehavioralModelResponse(BaseModel):
    contract_version: Literal["behavioral-digital-model.v1"]
    model_id: str
    baseline_id: str | None = None
    baseline_candidate_id: str | None = None
    version: int = Field(ge=1)
    status: Literal["awaiting_approval", "active", "unsuitable", "superseded"]
    workflow: Literal["create_baseline", "extend_baseline"]
    created_at: str
    source: dict[str, Any]
    lineage: dict[str, Any]
    telemetry_schema: dict[str, Any]
    timestamp_quality: dict[str, Any]
    data_quality: dict[str, Any]
    sensor_health: dict[str, Any]
    operating_modes: list[dict[str, Any]]
    signal_characteristics: dict[str, Any]
    relationship_graph: dict[str, Any]
    expected_behavior_models: list[dict[str, Any]]
    suitability: BaselineSuitabilityResponse
    activation: dict[str, Any]


class BaselineConstructionResultResponse(BaseModel):
    contract_version: Literal["baseline-suitability.v1"]
    job_id: str
    upload_id: str
    dataset_id: str
    baseline_candidate_id: str
    established_baseline_id: str
    portfolio_id: str
    system_id: str
    dataset_scope: dict[str, Any]
    workflow: Literal["create_baseline", "extend_baseline"]
    status: Literal["COMPLETE"]
    processing_state: Literal["complete"]
    filename: str
    completed_at: str
    candidate_model: BehavioralModelResponse
    baseline_suitability: BaselineSuitabilityResponse
    activation: dict[str, Any]
    processing_trace: dict[str, Any]


class BehavioralModelApprovalRequest(ContractModel):
    note: OptionalNote | None = None


class LatestUploadResponse(BaseModel):
    status: str
    source: str
    message: str
    last_filename: str | None = None
    rows_processed: int = 0
    columns_detected: int = 0
    last_processed_at: str | None = None
    runner_module: str | None = None
    core_engine: str | None = None
    state_available: bool = False
    connection_status: str
    result_source: str | None = None
    history: list[dict[str, Any]] = Field(default_factory=list)
    latest_result: dict[str, Any] | None = None
    sii_completed: bool = False
    sii_completion_artifacts: dict[str, bool] = Field(default_factory=dict)
    runner_used: bool | None = None
    chunk_count: int | None = None
    memory_estimate_bytes: int | None = None
    engine_runtime_seconds: float | None = None
    baseline_source: str | None = None
    baseline_status: str | None = None
    baseline_samples_collected: int = 0
    baseline_samples_required: int = 0
    last_baseline_update: str | None = None
    adaptive_learning: dict[str, Any] = Field(default_factory=dict)


class EvidenceRunResponse(BaseModel):
    run_id: str
    job_id: str | None = None
    upload_id: str | None = None
    source_type: str
    source_name: str | None = None
    source_url: str | None = None
    filename: str | None = None
    created_at: str
    completed_at: str | None = None
    status: str
    rows_received: int = 0
    rows_accepted: int = 0
    rows_rejected: int = 0
    sensors_detected: int = 0
    system_id: str | None = None
    room: str | None = None
    operating_state: str | None = None
    neraium_score: int | None = None
    drift_status: str | None = None
    primary_drivers: list[str] = Field(default_factory=list)
    evidence_summary: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    input_hash: str | None = None
    result_hash: str | None = None
    evidence_hash: str | None = None
    organization_id: str | None = None
    portfolio_id: str | None = None
    site_id: str | None = None
    dataset_id: str | None = None
    dataset_scope: dict[str, Any] | None = None
    baseline_id: str | None = None
    baseline_dataset_id: str | None = None
    baseline_version: int | str | None = None
    baseline_hash: str | None = None
    engine_version: str | None = None
    build_commit: str | None = None
    configuration_hash: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    initiated_by: str | None = None
    scenario: str | None = None
    tick: int | None = None
    adaptive_site_key: str | None = None
    structural_archetypes: list[str] = Field(default_factory=list)
    latest_feedback_category: str | None = None
    historical_fact: str | None = None
    operator_feedback_history: list[dict[str, Any]] = Field(default_factory=list)
    finding_status_history: list[dict[str, Any]] = Field(default_factory=list)
    finding_owner: str | None = None
    finding_assignee: str | None = None
    work_order_reference: str | None = None
    validation_outcome: str | None = None
    validation_status: str | None = None
    validation_event_history: list[dict[str, Any]] = Field(default_factory=list)
    before_after_intervention: dict[str, Any] = Field(default_factory=dict)
    observation_type: str | None = None
    observation_status: str | None = None
    variables: list[str] = Field(default_factory=list)
    drift_metrics: dict[str, Any] = Field(default_factory=dict)
    data_conditions: list[str] = Field(default_factory=list)
    evidence_windows: list[dict[str, Any]] = Field(default_factory=list)
    timestamps: dict[str, Any] = Field(default_factory=dict)
    traceability: dict[str, Any] = Field(default_factory=dict)
    confidence_score: int | float | None = None
    regime_label: str | None = None
    structural_state: str | None = None
    deformation_started_at: str | None = None
    confidence_tier: str | None = None
    governance_boundary: dict[str, Any] = Field(default_factory=dict)
    engineering_priors_used: list[dict[str, Any] | str] = Field(default_factory=list)
    audit_tags: list[dict[str, Any]] = Field(default_factory=list)
    condition_id: str | None = None
    finding_title: str | None = None
    system_name: str | None = None
    subsystem_name: str | None = None
    potential_impact: str | None = None
    condition: dict[str, Any] = Field(default_factory=dict)
    finding_identity_snapshot: list[dict[str, Any]] = Field(default_factory=list)


class OperatorFeedbackRequest(ContractModel):
    category: Literal[
        "confirmed_issue", "known_operational_change", "sensor_or_data_problem",
        "environmental_cause", "nothing_meaningful", "useful_warning",
        "expected_behavior", "false_positive", "maintenance_event", "ignore",
    ]
    note: OptionalNote | None = None
    outcome: Annotated[str, StringConstraints(max_length=500)] | None = None
    action_taken: Annotated[str, StringConstraints(max_length=2000)] | None = None
    intervention_at: str | None = None
    followup_at: str | None = None

    @field_validator("intervention_at", "followup_at")
    @classmethod
    def timestamps_are_utc(cls, value: str | None) -> str | None:
        return validate_utc_timestamp(value)


class FindingStatusRequest(ContractModel):
    state: Literal["open", "acknowledged", "investigating", "monitoring", "resolved", "dismissed"]
    note: OptionalNote | None = None
    owner: ShortText | None = None
    assignee: ShortText | None = None
    work_order_reference: Annotated[str, StringConstraints(max_length=200)] | None = None


class FindingAssignment(ContractModel):
    target_type: Literal["person", "team"]
    label: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    external_ref: Annotated[str, StringConstraints(min_length=1, max_length=200)] | None = None


class FindingWorkflowUpdateRequest(ContractModel):
    expected_version: int = Field(ge=0)
    idempotency_key: Annotated[str, StringConstraints(min_length=1, max_length=200)] | None = None
    status: Literal[
        "open", "acknowledged", "investigating", "waiting", "escalated",
        "awaiting_review", "monitoring", "resolved", "dismissed",
    ] | None = None
    user_priority: Literal["low", "medium", "high", "critical"] | None = None
    assignment: FindingAssignment | None = None
    due_at: str | None = None
    manager_note: OptionalNote | None = None
    work_order_reference: Annotated[str, StringConstraints(max_length=200)] | None = None
    external_reference: Annotated[str, StringConstraints(max_length=500)] | None = None
    validation_outcome: Annotated[str, StringConstraints(max_length=200)] | None = None
    validation_note: OptionalNote | None = None

    @field_validator("due_at")
    @classmethod
    def due_at_is_utc(cls, value: str | None) -> str | None:
        return validate_utc_timestamp(value)


class FindingFeedbackRequest(OperatorFeedbackRequest):
    expected_version: int = Field(ge=0)
    idempotency_key: Annotated[str, StringConstraints(min_length=1, max_length=200)] | None = None


class FindingFieldReportRequest(ContractModel):
    expected_version: int = Field(ge=0)
    idempotency_key: Annotated[str, StringConstraints(min_length=1, max_length=200)] | None = None
    note: OptionalNote | None = None
    inspected: Annotated[str, StringConstraints(max_length=2000)] | None = None
    found: Annotated[str, StringConstraints(max_length=2000)] | None = None
    action_taken: Annotated[str, StringConstraints(max_length=2000)] | None = None
    problem_found: Literal["yes", "no", "uncertain"]
    needs_escalation: bool = False
    investigation_complete: bool = False


class FindingResolutionRequest(ContractModel):
    expected_version: int = Field(ge=0)
    idempotency_key: Annotated[str, StringConstraints(min_length=1, max_length=200)] | None = None
    outcome: Literal[
        "issue_found", "no_issue_found", "operational_change", "sensor_issue",
        "maintenance_performed",
    ]
    note: OptionalNote | None = None


class FindingSourceResponse(BaseModel):
    kind: Literal["evidence_run", "live_finding"]
    id: str
    finding_key: str
    run_id: str | None = None


class FindingWorkflowResponse(BaseModel):
    version: int
    status: Literal[
        "open", "acknowledged", "investigating", "waiting", "escalated",
        "awaiting_review", "monitoring", "resolved", "dismissed",
    ]
    recommended_priority: Literal["low", "medium", "high", "critical"] | None = None
    user_priority: Literal["low", "medium", "high", "critical"] | None = None
    effective_priority: Literal["low", "medium", "high", "critical"] | None = None
    assignment: FindingAssignment | None = None
    assigned_by: str | None = None
    assignment_history: list[dict[str, Any]] = Field(default_factory=list)
    due_at: str | None = None
    manager_note: str | None = None
    work_order_reference: str | None = None
    external_reference: str | None = None
    validation_outcome: str | None = None
    validation_note: str | None = None
    latest_feedback: dict[str, Any] | None = None
    latest_field_report: dict[str, Any] | None = None
    field_reports: list[dict[str, Any]] = Field(default_factory=list)
    resolution: dict[str, Any] | None = None
    updated_at: str | None = None
    updated_by: str | None = None


class FindingActivitySummaryResponse(BaseModel):
    count: int
    latest_event_at: str | None = None
    url: str


class FindingCaseResponse(BaseModel):
    finding_id: str
    source: FindingSourceResponse
    evidence: dict[str, Any]
    workflow: FindingWorkflowResponse
    activity: FindingActivitySummaryResponse
    created_at: str


class FindingCasesListResponse(BaseModel):
    findings: list[FindingCaseResponse] = Field(default_factory=list)
    limit: int = 50
    offset: int = 0
    has_more: bool = False
    next_offset: int | None = None


class FindingActivityResponse(BaseModel):
    finding_id: str
    events: list[dict[str, Any]] = Field(default_factory=list)
    activity: list[dict[str, Any]] = Field(default_factory=list)
    version: int


class FindingWorkflowMemberResponse(BaseModel):
    member_id: str
    display_name: str
    role: Literal["viewer", "operator", "admin"]
    is_active: bool = True


class FindingWorkflowMembersListResponse(BaseModel):
    members: list[FindingWorkflowMemberResponse] = Field(default_factory=list)


class FacilitySystemContext(ContractModel):
    system_id: Identifier
    name: ShortText
    system_type: ShortText
    parent_system_id: Identifier | None = None
    equipment_ids: list[Identifier] = Field(default_factory=list, max_length=200)


class FacilityEquipmentContext(ContractModel):
    equipment_id: Identifier
    name: ShortText
    system_id: Identifier
    equipment_type: ShortText | None = None


class FacilitySignalMapping(ContractModel):
    raw_tag: Annotated[str, StringConstraints(min_length=1, max_length=256)]
    normalized_name: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    system_id: Identifier
    equipment_id: Identifier | None = None
    subsystem: ShortText | None = None
    unit: Annotated[str, StringConstraints(max_length=32)] = ""
    sample_rate_seconds: float | None = Field(default=None, gt=0, le=86400)
    alias: ShortText | None = None


class FacilityContextRequest(ContractModel):
    site_id: Identifier
    site_name: ShortText
    timezone: Annotated[str, StringConstraints(min_length=1, max_length=64)] = "UTC"
    systems: list[FacilitySystemContext] = Field(default_factory=list, max_length=200)
    equipment: list[FacilityEquipmentContext] = Field(default_factory=list, max_length=1000)
    signal_mappings: list[FacilitySignalMapping] = Field(default_factory=list, max_length=2000)


class EvidenceRunsListResponse(BaseModel):
    runs: list[EvidenceRunResponse] = Field(default_factory=list)
    limit: int = 50
    offset: int = 0
    has_more: bool = False
    next_offset: int | None = None


class LatestEvidenceResponse(BaseModel):
    status: str
    message: str | None = None
    run: EvidenceRunResponse | None = None


class AuthUserResponse(BaseModel):
    email: str
    name: str
    role: str
    created_at: str | None = None
    last_login_at: str | None = None
    is_active: bool = True
    deactivated_at: str | None = None
    bootstrap_managed: bool = False


class AuthUsersListResponse(BaseModel):
    users: list[AuthUserResponse] = Field(default_factory=list)


class AuthSessionResponse(BaseModel):
    session_id: str
    email: str
    created_at: str | None = None
    expires_at: str | None = None
    last_seen_at: str | None = None
    revoked_at: str | None = None


class AuthSessionsListResponse(BaseModel):
    sessions: list[AuthSessionResponse] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)


class AuthUserCreateRequest(ContractModel):
    email: EmailAddress
    password: Annotated[str, StringConstraints(min_length=8, max_length=1024)]
    name: ShortText | None = None
    role: Literal["viewer", "operator", "admin"] = "operator"


class WorkspaceSummaryResponse(BaseModel):
    workspace_id: str
    display_name: str
    kind: Literal["personal", "facility"]
    is_active: bool = True


class WorkspacesListResponse(BaseModel):
    workspaces: list[WorkspaceSummaryResponse] = Field(default_factory=list)
    default_workspace_id: str = "default"


class WorkspaceMemberResponse(BaseModel):
    member_id: str
    display_name: str
    role: Literal["viewer", "operator", "admin"]
    is_active: bool = True


class WorkspaceMembersListResponse(BaseModel):
    workspace_id: str
    members: list[WorkspaceMemberResponse] = Field(default_factory=list)


class WorkspaceCreateRequest(ContractModel):
    display_name: ShortText
    adopt_current_scope: bool = True


class WorkspaceMemberAddRequest(ContractModel):
    email: EmailAddress


class ObservabilitySummaryResponse(BaseModel):
    queue: dict[str, int]
    evidence_runs: dict[str, Any]
    audit: dict[str, Any]
    auth: dict[str, Any]
    alerts: list[dict[str, Any]]


class DataConnectionResponse(BaseModel):
    connection_id: str
    name: str
    url: str
    source_type: str
    facility_id: str | None = None
    room_id: str | None = None
    polling_enabled: bool = False
    polling_interval_seconds: int = 5
    last_poll_at: str | None = None
    last_success_at: str | None = None
    status: str
    error_message: str = ""
    readings_received: int = 0
    readings_accepted: int = 0
    readings_rejected: int = 0
    sensors_detected: int = 0
    current_scenario: str | None = None
    current_tick: int | None = None
    latest_telemetry_timestamp: str | None = None
    last_ingestion_source: str | None = None
    baseline_source: str | None = None
    baseline_status: str = "none"
    baseline_samples_collected: int = 0
    baseline_samples_required: int = 0
    last_baseline_update: str | None = None
    baseline_error_message: str = ""
    masked_configuration: dict[str, Any] = Field(default_factory=dict)


class DataConnectionsListResponse(BaseModel):
    connections: list[DataConnectionResponse] = Field(default_factory=list)


class DataConnectionUpsertRequest(ContractModel):
    connection_id: Identifier | None = None
    name: ShortText
    url: str
    source_type: Literal["external_rest_api"] = "external_rest_api"
    facility_id: Identifier | None = None
    room_id: Identifier | None = None
    polling_enabled: bool = False
    polling_interval_seconds: int = Field(default=5, ge=1, le=86_400)

    @field_validator("url")
    @classmethod
    def url_is_safe_http(cls, value: str) -> str:
        return validate_http_url(value)


class DataConnectionActionResponse(BaseModel):
    connection: DataConnectionResponse
    message: str
    normalized_preview: list[dict[str, Any]] = Field(default_factory=list)
    latest_result: dict[str, Any] | None = None
    meaningful_change: bool | None = None


class DataConnectionsBulkActionResponse(BaseModel):
    connections: list[DataConnectionResponse] = Field(default_factory=list)
    message: str


TelemetrySourceTag = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=256),
]
TelemetryUnit = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=64),
]


class TelemetryReadingRequest(ContractModel):
    # Timestamp validation happens in the ingestion service so malformed or
    # missing timestamps can be durably quarantined instead of rejecting the
    # entire HTTP batch before it is recorded.
    timestamp: Any | None = None
    signals: dict[TelemetrySourceTag, Any] = Field(min_length=1)


class TelemetryIngestionRequest(ContractModel):
    batch_id: Identifier | None = None
    system_id: Identifier
    source: Identifier
    readings: list[TelemetryReadingRequest] = Field(min_length=1)


class TelemetryIngestionResponse(BaseModel):
    batch_id: str
    accepted_reading_count: int
    rejected_reading_count: int
    accepted_signal_value_count: int
    rejected_signal_value_count: int
    warnings: list[str] = Field(default_factory=list)
    processing_timestamp: str


class TelemetrySignalMappingCreateRequest(ContractModel):
    system_id: Identifier
    source_tag: TelemetrySourceTag
    canonical_signal: Identifier
    unit: TelemetryUnit | None = None
    enabled: bool = True


class TelemetrySignalMappingUpdateRequest(ContractModel):
    canonical_signal: Identifier | None = None
    unit: TelemetryUnit | None = None
    enabled: bool | None = None


class TelemetrySignalMappingResponse(BaseModel):
    mapping_id: str
    system_id: str
    source_tag: str
    canonical_signal: str
    unit: str | None = None
    enabled: bool
    created_at: str
    updated_at: str


class TelemetrySignalMappingsListResponse(BaseModel):
    mappings: list[TelemetrySignalMappingResponse] = Field(default_factory=list)


class TelemetryIngestionHealthResponse(BaseModel):
    system_id: str
    source: str
    last_successful_ingestion_at: str | None = None
    last_telemetry_timestamp: str | None = None
    accepted_count: int = 0
    rejected_count: int = 0
    latest_error_or_warning: str | None = None
    status: Literal["healthy", "delayed", "error", "never_received"]
    updated_at: str | None = None


class TelemetryIngestionHealthListResponse(BaseModel):
    health: list[TelemetryIngestionHealthResponse] = Field(default_factory=list)


class LiveAnalysisConfigurationCreateRequest(ContractModel):
    system_id: Identifier
    enabled: bool = False
    approved_baseline_id: Identifier | None = None
    analysis_interval_seconds: int = Field(default=300, ge=30, le=86_400)
    comparison_window_minutes: int = Field(default=60, ge=1, le=10_080)
    minimum_coverage_percent: float = Field(default=80.0, ge=0, le=100)
    allowed_lateness_minutes: int = Field(default=5, ge=0, le=1_440)


class LiveAnalysisConfigurationUpdateRequest(ContractModel):
    approved_baseline_id: Identifier | None = None
    analysis_interval_seconds: int | None = Field(default=None, ge=30, le=86_400)
    comparison_window_minutes: int | None = Field(default=None, ge=1, le=10_080)
    minimum_coverage_percent: float | None = Field(default=None, ge=0, le=100)
    allowed_lateness_minutes: int | None = Field(default=None, ge=0, le=1_440)


class LiveAnalysisConfigurationResponse(BaseModel):
    system_id: str
    enabled: bool
    approved_baseline_id: str | None = None
    analysis_interval_seconds: int
    comparison_window_minutes: int
    minimum_coverage_percent: float
    allowed_lateness_minutes: int
    last_analysis_started_at: str | None = None
    last_analysis_completed_at: str | None = None
    next_analysis_at: str | None = None
    current_status: str
    latest_error: str | None = None
    created_at: str
    updated_at: str


class LiveAnalysisConfigurationsListResponse(BaseModel):
    configurations: list[LiveAnalysisConfigurationResponse] = Field(default_factory=list)


class LiveAnalysisRunResponse(BaseModel):
    run_id: str
    system_id: str
    baseline_reference: str
    window_start: str
    window_end: str
    status: Literal["pending", "running", "completed", "skipped", "failed"]
    started_at: str | None = None
    completed_at: str | None = None
    rows_analyzed: int
    signals_analyzed: int
    coverage: float
    skipped_reason: str | None = None
    error_summary: str | None = None
    analytics_result_reference: str | None = None
    created_findings_count: int
    updated_findings_count: int
    resolved_findings_count: int
    created_at: str


class LiveAnalysisRunsListResponse(BaseModel):
    runs: list[LiveAnalysisRunResponse] = Field(default_factory=list)


class LiveFindingResponse(BaseModel):
    finding_id: str
    deduplication_key: str
    system_id: str
    relationship_identity: str
    finding_classification: dict[str, Any]
    first_detected_at: str
    last_observed_at: str
    opened_at: str | None = None
    resolved_at: str | None = None
    current_state: Literal["observing", "open", "resolved"]
    persistence_state: dict[str, Any]
    severity_score: float | None = None
    latest_evidence: dict[str, Any]
    source_live_analysis_run_id: str
    baseline_reference: str
    created_at: str
    updated_at: str


class LiveFindingsListResponse(BaseModel):
    findings: list[LiveFindingResponse] = Field(default_factory=list)


class LiveAnalysisHealthResponse(BaseModel):
    system_id: str
    last_attempted_run_at: str | None = None
    last_completed_run_at: str | None = None
    last_successful_run_at: str | None = None
    current_status: Literal[
        "healthy",
        "waiting_for_data",
        "missing_baseline",
        "delayed",
        "running",
        "error",
        "disabled",
        "never_run",
    ]
    current_window_coverage: float
    latest_skipped_reason: str | None = None
    consecutive_failures: int
    latest_error: str | None = None
    next_scheduled_run: str | None = None
    updated_at: str | None = None


class LiveAnalysisHealthListResponse(BaseModel):
    health: list[LiveAnalysisHealthResponse] = Field(default_factory=list)
