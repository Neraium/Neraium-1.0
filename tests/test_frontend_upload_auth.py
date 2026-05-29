from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_JSX = ROOT / "frontend" / "src" / "App.jsx"
WORKSPACES_CONFIG = ROOT / "frontend" / "src" / "config" / "workspaces.js"
DATA_CONNECTIONS_WORKSPACE = ROOT / "frontend" / "src" / "components" / "DataConnectionsWorkspace.jsx"
SYSTEM_BODY_WORKSPACE = ROOT / "frontend" / "src" / "components" / "workspaces" / "SystemBody" / "SystemBodyWorkspace.jsx"
CONFIG_JS = ROOT / "frontend" / "src" / "config.js"
UPLOAD_FLOW = ROOT / "frontend" / "src" / "viewModels" / "uploadFlow.js"
UPLOAD_STATE = ROOT / "frontend" / "src" / "viewModels" / "uploadState.js"
USE_FACILITY_RUNTIME = ROOT / "frontend" / "src" / "hooks" / "useFacilityRuntime.js"
HEALTH_API = ROOT / "frontend" / "src" / "services" / "api" / "healthApi.js"
SYSTEM_API = ROOT / "frontend" / "src" / "services" / "api" / "systemApi.js"


def read_frontend(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_upload_surface() -> str:
    return "\n".join(
        [
            read_frontend(APP_JSX),
            read_frontend(DATA_CONNECTIONS_WORKSPACE),
            read_frontend(UPLOAD_FLOW),
            read_frontend(UPLOAD_STATE),
        ]
    )


def test_shared_api_helper_forces_credentials_include() -> None:
    source = read_frontend(CONFIG_JS)

    assert 'trim().replace(/\\/+$/, "")' in source
    assert 'credentials: "include"' in source
    assert "const response = await fetch(buildUrl(apiBaseUrl, path), {" in source
    assert "const { accessCode, headers, timeoutMs, ...rest } = options;" in source
    assert "...(headers ?? {})" in source
    assert "Authorization: `Bearer ${resolvedAccessCode}`" not in source
    assert 'console.log("ACCESS CODE:"' not in source


def test_upload_and_polling_use_shared_api_helper() -> None:
    source = read_upload_surface()
    system_api_source = read_frontend(SYSTEM_API)

    assert "apiFetch(`/api/data/upload-status/${pollingJobId}`" in source
    assert 'apiFetch("/api/data/latest-upload?include_persisted=1"' in source
    assert 'apiFetch("/api/health"' in read_frontend(HEALTH_API)
    assert 'apiFetch("/api/ready"' in read_frontend(HEALTH_API)
    assert "apiFetch(`/api/facility/systems?include_persisted=1${domainQuery}`" in system_api_source
    assert "const LATEST_UPLOAD_DEDUPE_TTL_MS = 4000;" in read_frontend(ROOT / "frontend" / "src" / "services" / "api" / "uploadApi.js")
    assert "const FACILITY_SYSTEMS_DEDUPE_TTL_MS = 4000;" in system_api_source


def test_frontend_polling_uses_bounded_backoff_under_failures() -> None:
    source = read_frontend(DATA_CONNECTIONS_WORKSPACE)
    assert "const cooldownMs = Math.min(120000, 20000 + statusEndpointFailureCountRef.current * 10000);" in source
    assert "baseDelay = Math.min(6000 + failureCount * 12000, 120000);" in source


def test_frontend_uses_uploaded_room_summary_for_room_context() -> None:
    source = read_frontend(UPLOAD_STATE)

    assert "function extractRoomSummaryNames(result)" in source
    assert "result?.room_summary?.rooms" in source
    assert "uploadedRooms.length" in source


def test_polling_does_not_enter_error_state_on_single_auth_failure() -> None:
    source = read_frontend(UPLOAD_FLOW)

    assert "const isAuthDuringPolling = phase === \"poll\" && (error.status === 401 || error.status === 403);" in source
    assert 'state: isAuthDuringPolling || isMissingStatusDuringPoll || (phase === "poll" && error.retryable) ? "running_sii" : "error"' in source


def test_polling_retries_missing_upload_status() -> None:
    source = read_upload_surface()

    assert 'response.status === 404 && errorType === "upload_session_missing"' in source
    assert "pollFailureCountRef.current < 30" in source
    assert "Waiting for upload status to become available." in source


def test_upload_polling_preserves_returned_job_id() -> None:
    source = read_frontend(DATA_CONNECTIONS_WORKSPACE)

    assert "const uploadJobIdRef = useRef(null);" in source
    assert "uploadJobIdRef.current = payload.job_id ?? pollingJobId;" in source
    assert "const pollingJobId = jobId || uploadJobIdRef.current;" in source
    assert "apiFetch(`/api/data/upload-status/${pollingJobId}`" in source
    assert 'throw buildUploadRequestError({ status }, { ...payload, error_type: "upload_session_missing", message: "Upload state unavailable." }, "upload");' in source


def test_object_errors_render_through_normalized_messages() -> None:
    source = read_upload_surface()
    contract_source = read_frontend(ROOT / "frontend" / "src" / "viewModels" / "uploadContract.js")

    assert "function normalizeErrorMessage(error)" in source
    assert "function normalizeErrorMessage(error)" in contract_source
    assert "return JSON.stringify(error);" in contract_source


def test_frontend_upload_progress_uses_propagation_fields_with_fallback() -> None:
    source = read_frontend(DATA_CONNECTIONS_WORKSPACE)
    panel = read_frontend(ROOT / "frontend" / "src" / "components" / "setup" / "IntakeFlowPanel.jsx")

    assert "uploadJob?.propagation_progress" in source
    assert "propagationPercent" in source
    assert "[uploadTransferPercent, propagationPercent, backendPercent, statusFallbackPercent]" in source
    assert "propagationLabel" in source
    assert "propagationLabel || uploadJob?.progress_label || latestMessage" in panel


def test_mobile_upload_limit_and_guidance_are_operational_grade() -> None:
    source = read_frontend(DATA_CONNECTIONS_WORKSPACE)

    assert "const MAX_UPLOAD_BYTES = 250 * 1024 * 1024;" in source
    assert "const LARGE_OPERATIONAL_UPLOAD_BYTES = 100 * 1024 * 1024;" in source
    assert "Large telemetry export detected" in source
    assert "Telemetry export validated." in source
    assert "High-volume export above" in source
    assert "25 MB mobile intake limit" not in source


def test_protected_route_errors_use_generic_session_copy() -> None:
    source = read_upload_surface()

    assert "Session expired. Refresh workspace." in source
    assert "Upload processing interrupted." in source
    assert "Upload state unavailable." in source
    assert "[object Object]" not in source


def test_upload_errors_do_not_preserve_shared_secret_diagnostics() -> None:
    source = read_upload_surface()

    assert "authDiagnostic: payload?.auth_diagnostic ?? payload?.detail?.auth_diagnostic ?? null" not in source
    assert "formatAuthDiagnosticMessage(authDiagnostic)" not in source


def test_public_health_check_does_not_clear_protected_route_errors() -> None:
    source = read_frontend(USE_FACILITY_RUNTIME)
    health_start = source.index("await fetchApiHealth({")
    health_end = source.index("setApiStatus({", health_start)
    health_success_block = source[health_start:health_end]

    assert "setBackendError(API_CONFIG_WARNING)" not in health_success_block


def test_frontend_uses_backend_latest_upload_without_local_cache_override() -> None:
    source = read_frontend(USE_FACILITY_RUNTIME)

    assert "const [latestUploadResult, setLatestUploadResult] = useState(null);" in source
    assert "const loadLatestUploadState = useCallback(async ({ includePersisted } = {}) => {" in source
    assert "window.localStorage" not in source


def test_system_body_uses_backend_system_interpretation_when_present() -> None:
    source = read_frontend(SYSTEM_BODY_WORKSPACE)

    assert "const backendSystemInterpretation = latestUploadSnapshot?.system_interpretation" in source
    assert "const mappedBackendInterpretation = mapBackendSystemInterpretation(backendSystemInterpretation);" in source
    assert "if (mappedBackendInterpretation) {" in source
    assert "return mappedBackendInterpretation;" in source


def test_system_body_fallback_is_neutral_without_semantic_derivation() -> None:
    source = read_frontend(SYSTEM_BODY_WORKSPACE)

    assert '"No Active Session"' in source
    assert '"Awaiting Interpretation"' in source
    assert '"Processing Upload"' in source
    assert '"Interpretation Unavailable"' in source

    assert "compoundSignals" not in source
    assert "normalizeSeverity(" not in source
    assert "formatIndex(" not in source
    assert "relationshipChanges.length > 0" not in source
    assert "dominantPaths.length > 0" not in source


def test_system_body_displays_backend_interpretation_fields_in_mapper() -> None:
    source = read_frontend(SYSTEM_BODY_WORKSPACE)

    assert "facility_state: String(value.facility_state_label" in source
    assert "confidence: String(value.confidence" in source
    assert "primary_driver: String(value.primary_driver" in source
    assert "text: String(backendSummary.text || fallbackSummary || EMPTY_VALUE)" in source
    assert "divergence_severity: String(divergence.severity" in source


def test_frontend_uses_single_data_connections_workspace_for_uploads() -> None:
    source = read_upload_surface()
    workspaces_source = read_frontend(WORKSPACES_CONFIG)

    assert 'label: "Telemetry Setup"' in workspaces_source
    assert 'id: "data-connections"' in workspaces_source
    assert "DataConnectionsWorkspace" in source
    assert "HistorianSetupWorkspace" not in source


def test_upload_normalization_uses_upload_contract_with_compat_exports() -> None:
    contract_source = read_frontend(ROOT / "frontend" / "src" / "viewModels" / "uploadContract.js")
    flow_source = read_frontend(UPLOAD_FLOW)
    state_source = read_frontend(UPLOAD_STATE)

    assert "export function normalizeUploadStatus(status)" in contract_source
    assert "export function normalizeErrorMessage(error)" in contract_source
    assert "export function normalizeUploadJob(payload = {})" in contract_source
    assert "propagation_stage" in contract_source
    assert "propagation_progress" in contract_source
    assert "propagation_label" in contract_source

    assert "normalizeUploadStatus as normalizeUploadContractStatus" in flow_source
    assert "normalizeErrorMessage as normalizeUploadContractErrorMessage" in flow_source
    assert "export function normalizeUploadStatus(status)" in flow_source
    assert "return normalizeUploadContractStatus(status);" in flow_source
    assert "export function normalizeErrorMessage(error)" in flow_source
    assert "return normalizeUploadContractErrorMessage(error);" in flow_source

    assert "normalizeUploadStatus as normalizeUploadContractStatus" in state_source
    assert "normalizeErrorMessage as normalizeUploadContractErrorMessage" in state_source
    assert "function normalizeUploadStatus(status)" in state_source
    assert "return normalizeUploadContractStatus(status);" in state_source


def test_frontend_displays_queued_worker_visibility_messages() -> None:
    source = read_frontend(ROOT / "frontend" / "src" / "components" / "DataConnectionsWorkspace.jsx")
    panel = read_frontend(ROOT / "frontend" / "src" / "components" / "setup" / "IntakeFlowPanel.jsx")

    assert "Worker starting..." in source
    assert "Worker active • last update" in source
    assert "Still queued • waiting for worker" in source
    assert "Possible stall • no worker update yet" in source
    assert "queuedWorkerDetail" in panel
