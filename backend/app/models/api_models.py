from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints, field_validator

from app.contracts import ContractModel, EmailAddress, Identifier, OptionalNote, SecretText, ShortText, validate_http_url, validate_utc_timestamp


class UploadAcceptedResponse(BaseModel):
    job_id: str
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



class UploadStatusResponse(BaseModel): 
    job_id: str | None
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
    initiated_by: str | None = None
    scenario: str | None = None
    tick: int | None = None
    adaptive_site_key: str | None = None
    structural_archetypes: list[str] = Field(default_factory=list)
    latest_feedback_category: str | None = None
    historical_fact: str | None = None
    operator_feedback_history: list[dict[str, Any]] = Field(default_factory=list)
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
