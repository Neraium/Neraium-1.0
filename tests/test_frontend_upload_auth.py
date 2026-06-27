from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_JSX = ROOT / "frontend" / "src" / "App.jsx"
WORKSPACES_CONFIG = ROOT / "frontend" / "src" / "config" / "workspaces.js"
DATA_CONNECTIONS_WORKSPACE = ROOT / "frontend" / "src" / "components" / "DataConnectionsWorkspace.jsx"
ONBOARDING_WORKSPACE = ROOT / "frontend" / "src" / "components" / "OnboardingWorkspace.jsx"
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
    assert "VITE_NERAIUM_API_TOKEN" not in source
    assert 'console.log("ACCESS CODE:"' not in source


def test_upload_and_polling_use_shared_api_helper() -> None:
    source = read_upload_surface()
    system_api_source = read_frontend(SYSTEM_API)

    assert "let pollingPath = normalizeUploadStatusPath(statusUrl, requestedJobId) ?? `/api/data/upload-status/${requestedJobId}`;" in source
    assert "const response = await apiFetch(requestPath, { accessCode });" in source
    assert 'apiFetch("/api/data/latest-upload?include_persisted=1"' in source
    assert 'apiFetch("/api/health"' in read_frontend(HEALTH_API)
    assert 'apiFetch("/api/ready"' in read_frontend(HEALTH_API)
    assert "apiFetch(`/api/facility/systems?include_persisted=1${domainQuery}`" in system_api_source
    assert "const LATEST_UPLOAD_DEDUPE_TTL_MS = 4000;" in read_frontend(ROOT / "frontend" / "src" / "services" / "api" / "uploadApi.js")
    assert "const FACILITY_SYSTEMS_DEDUPE_TTL_MS = 4000;" in system_api_source


def test_frontend_polling_uses_bounded_backoff_under_failures() -> None:
    source = read_frontend(DATA_CONNECTIONS_WORKSPACE)
    assert "const cooldownMs = Math.min(120000, 20000 + statusEndpointFailureCountRef.current * 10000);" in source
    assert "statusEndpointFailureCountRef.current > MAX_STATUS_POLL_FAILURES" in source
    assert "Math.min(30000, baseDelay * (1.5 ** failureCount))" in source
    assert "Math.min(Math.max(backoff, 1000), 45000)" in source


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

    assert "response.status === 404 || response.status >= 500" in source
    assert "statusEndpointFailureCountRef.current += 1;" in source
    assert "statusEndpointFailureCountRef.current > MAX_STATUS_POLL_FAILURES" in source
    assert "Upload status remained unavailable after repeated retries." in source


def test_upload_polling_preserves_returned_job_id() -> None:
    source = read_frontend(DATA_CONNECTIONS_WORKSPACE)

    assert "const uploadJobIdRef = useRef(null);" in source
    assert "const requestedJobId = String(jobId ?? \"\").trim();" in source
    assert "uploadJobIdRef.current = requestedJobId;" in source
    assert "uploadJobIdRef.current = payload.job_id ?? requestedJobId;" in source
    assert "normalizeUploadStatusPath(statusUrl, requestedJobId) ?? `/api/data/upload-status/${requestedJobId}`" in source


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
    assert "const primaryProgressText = String(uploadJob?.progress_label || latestMessage || \"\").trim();" in panel
    assert "const secondaryProgressText = String(propagationLabel || uploadStateMessage(uploadState) || \"\").trim();" in panel


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

    assert '"No data yet"' in source
    assert '"Processing data"' in source
    assert '"Interpretation Unavailable"' in source
    assert '"Upload data to begin."' in source

    assert "compoundSignals" not in source
    assert "normalizeSeverity(" not in source
    assert "formatIndex(" not in source
    assert "relationshipChanges.length > 0" not in source
    assert "dominantPaths.length > 0" not in source


def test_system_body_displays_backend_interpretation_fields_in_mapper() -> None:
    source = read_frontend(SYSTEM_BODY_WORKSPACE)

    assert "structuralState: normalizeStructuralLabel(value.facility_state_label" in source
    assert "confidence: String(value.confidence" in source
    assert "primaryDriver: String(value.primary_driver" in source
    assert "text: simplifyOperatorSummary(backendSummary.text || fallbackSummary || EMPTY_VALUE)" in source
    assert "divergence_severity: String(divergence.severity" in source
    assert "findingEvidenceChains: Array.isArray(value.finding_evidence_chains)" in source
    assert 'aria-label="Supporting evidence"' in source
    assert 'Supporting Evidence' in source


def test_frontend_uses_single_data_connections_workspace_for_uploads() -> None:
    source = read_upload_surface()
    workspaces_source = read_frontend(WORKSPACES_CONFIG)

    assert 'label: "Upload Data"' in workspaces_source
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


def test_queued_worker_status_is_folded_into_single_upload_line() -> None:
    source = read_frontend(ROOT / "frontend" / "src" / "components" / "DataConnectionsWorkspace.jsx")
    panel = read_frontend(ROOT / "frontend" / "src" / "components" / "setup" / "IntakeFlowPanel.jsx")

    assert "workerState === \"starting\"" in source
    assert "Worker starting..." in source
    assert "queuedWorkerDetail ? <span className=\"metadata-text\">{queuedWorkerDetail}</span> : null" not in panel
    assert "customerUploadMessage" in panel
    assert "uploadTransfer?.label" in panel


def test_onboarding_storage_redacts_api_token() -> None:
    source = read_frontend(ONBOARDING_WORKSPACE)

    assert "function storageSafeFlow(flow)" in source
    assert 'token: "",' in source
    assert "localStorage.setItem(STORAGE_KEY, JSON.stringify(storageSafeFlow(flow)))" in source
    assert "localStorage.setItem(STORAGE_KEY, JSON.stringify(flow))" not in source
    assert "return { ...defaultState(), ...parsed, api: { ...defaultState().api, ...(parsed?.api || {}) } };" not in source


def test_upload_request_targets_real_api_ingestion_route() -> None:
    source = read_frontend(ROOT / "frontend" / "src" / "services" / "api" / "uploadApi.js")

    assert "buildApiCandidateUrls(\"/api/data/upload\", { method: \"POST\", allowSameOriginFallback: false })" in source


def test_upload_attempt_reports_nonzero_connecting_progress() -> None:
    source = read_frontend(ROOT / "frontend" / "src" / "services" / "api" / "uploadApi.js")

    assert "xhr.open(\"POST\", uploadUrls[index], true);" in source
    assert "percent: file.size > 0 ? 1 : 0" in source
    assert "Connecting to telemetry ingestion." in source


def test_frontend_surfaces_backend_runtime_diagnostics() -> None:
    runtime_source = read_frontend(USE_FACILITY_RUNTIME)
    router_source = read_frontend(ROOT / "frontend" / "src" / "components" / "AppWorkspaceRouter.jsx")
    technical_source = read_frontend(ROOT / "frontend" / "src" / "components" / "HelpChangelogWorkspace.jsx")

    assert "const diagnostics = healthPayload?.ready?.diagnostics ?? healthPayload?.diagnostics ?? null;" in runtime_source
    assert "diagnostics," in runtime_source
    assert "apiStatus={apiStatus}" in router_source
    assert "Production diagnostics" in technical_source
    assert 'data-testid="production-diagnostics"' in technical_source
    assert "Deployment warnings" in technical_source
    assert "latest_upload_error_type" in technical_source


def test_retry_analysis_targets_current_uploaded_job() -> None:
    upload_api_source = read_frontend(ROOT / "frontend" / "src" / "services" / "api" / "uploadApi.js")
    workspace_source = read_frontend(DATA_CONNECTIONS_WORKSPACE)
    panel_source = read_frontend(ROOT / "frontend" / "src" / "components" / "setup" / "IntakeFlowPanel.jsx")

    assert "export async function retryUploadAnalysisJob" in upload_api_source
    assert "/api/data/upload/${encodeURIComponent(cleanJobId)}/retry" in upload_api_source
    assert "retryUploadAnalysisJob({ jobId: currentJobId, apiFetch, accessCode })" in workspace_source
    assert "await handleUpload();" in workspace_source
    assert "File selected. Upload is required before analysis." in panel_source
    assert "Upload and Analyze" in panel_source
    assert "onClick={() => onRetryFailedUploads?.()}" in panel_source
