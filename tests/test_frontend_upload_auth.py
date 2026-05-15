from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_JSX = ROOT / "frontend" / "src" / "App.jsx"
WORKSPACES_CONFIG = ROOT / "frontend" / "src" / "config" / "workspaces.js"
DATA_CONNECTIONS_WORKSPACE = ROOT / "frontend" / "src" / "components" / "DataConnectionsWorkspace.jsx"
EVIDENCE_WORKSPACE = ROOT / "frontend" / "src" / "components" / "EvidenceTrailWorkspace.jsx"
EVIDENCE_API = ROOT / "frontend" / "src" / "services" / "evidenceApi.js"
CONFIG_JS = ROOT / "frontend" / "src" / "config.js"
UPLOAD_FLOW = ROOT / "frontend" / "src" / "viewModels" / "uploadFlow.js"
UPLOAD_STATE = ROOT / "frontend" / "src" / "viewModels" / "uploadState.js"
USE_FACILITY_RUNTIME = ROOT / "frontend" / "src" / "hooks" / "useFacilityRuntime.js"
HEALTH_API = ROOT / "frontend" / "src" / "services" / "api" / "healthApi.js"


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
    assert "return {};" in source
    assert "Authorization: `Bearer ${resolvedAccessCode}`" not in source
    assert 'console.log("ACCESS CODE:"' not in source


def test_upload_and_polling_use_shared_credentialed_api_helper() -> None:
    source = read_upload_surface()
    app_source = read_frontend(APP_JSX)
    evidence_source = read_frontend(EVIDENCE_WORKSPACE)
    evidence_api_source = read_frontend(EVIDENCE_API)

    for endpoint in (
        'apiFetch("/api/data/upload"',
        "apiFetch(`/api/data/upload-status/${pollingJobId}`",
        'apiFetch("/api/data/latest-upload"',
    ):
        assert endpoint in source
    assert 'apiFetch("/api/health"' in read_frontend(HEALTH_API)
    assert 'apiFetch("/api/facility/systems"' in read_frontend(ROOT / "frontend" / "src" / "services" / "api" / "systemApi.js")
    for endpoint in (
        'apiFetch("/api/evidence/latest"',
        'apiFetch("/api/evidence/runs"',
        "apiFetch(`/api/evidence/runs/${runId}`",
        "apiFetch(`/api/evidence/export/${runId}`",
    ):
        assert endpoint in evidence_api_source
    assert "fetchLatestEvidence" in evidence_source
    assert "fetchEvidenceRuns" in evidence_source
    assert "fetchEvidenceRun" in evidence_source
    assert "exportEvidenceRun" in evidence_source


def test_frontend_uses_uploaded_room_summary_for_room_context() -> None:
    source = read_frontend(UPLOAD_STATE)

    assert "function extractRoomSummaryNames(result)" in source
    assert "result?.room_summary?.rooms" in source
    assert "uploadedRooms.length" in source


def test_multipart_upload_does_not_set_form_data_content_type() -> None:
    source = read_frontend(DATA_CONNECTIONS_WORKSPACE)
    upload_start = source.index('apiFetch("/api/data/upload"')
    upload_end = source.index("const payload = await readJsonPayload(response);", upload_start)
    upload_block = source[upload_start:upload_end]

    assert 'method: "POST"' in upload_block
    assert "body: formData" in upload_block
    assert "Content-Type" not in upload_block


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
    assert "uploadJobIdRef.current = payload.job_id;" in source
    assert "const pollingJobId = jobId || uploadJobIdRef.current;" in source
    assert "apiFetch(`/api/data/upload-status/${pollingJobId}`" in source
    assert 'throw buildUploadRequestError(response, { ...payload, error_type: "upload_session_missing", message: "Upload state unavailable." }, "upload");' in source


def test_object_errors_render_through_normalized_messages() -> None:
    source = read_upload_surface()

    assert "function normalizeErrorMessage(error)" in source
    assert "return JSON.stringify(error);" in source
    assert "{normalizeErrorMessage(uploadError)}" in source


def test_protected_route_errors_use_generic_session_copy() -> None:
    source = read_upload_surface()
    app_source = read_frontend(APP_JSX)

    assert "Session expired. Refresh workspace." in source
    assert "await buildProtectedRequestMessage(error)" in read_frontend(USE_FACILITY_RUNTIME)
    assert "function formatAuthDiagnosticMessage(diagnostic)" not in source
    assert "[object Object]" not in source
    assert "Upload processing interrupted." in source
    assert "Upload state unavailable." in source


def test_upload_errors_do_not_preserve_shared_secret_diagnostics() -> None:
    source = read_upload_surface()

    assert "authDiagnostic: payload?.auth_diagnostic ?? payload?.detail?.auth_diagnostic ?? null" not in source
    assert "authDiagnostic: error.authDiagnostic" not in source
    assert "formatAuthDiagnosticMessage(authDiagnostic)" not in source
    assert "`auth_reason=${classified.authDiagnostic?.failure_reason ?? \"n/a\"}`" not in source
    assert "`auth_source=${classified.authDiagnostic?.auth_source ?? \"n/a\"}`" not in source


def test_public_health_check_does_not_clear_protected_route_errors() -> None:
    source = read_frontend(USE_FACILITY_RUNTIME)
    health_start = source.index("await fetchApiHealth({")
    health_end = source.index("setApiStatus({", health_start)
    health_success_block = source[health_start:health_end]

    assert "setBackendError(API_CONFIG_WARNING)" not in health_success_block


def test_upload_failure_console_log_uses_readable_fields() -> None:
    source = read_upload_surface()

    assert "telemetry_upload_failure" not in source


def test_frontend_uses_backend_latest_upload_without_local_cache_override() -> None:
    source = read_frontend(USE_FACILITY_RUNTIME)

    assert "const [latestUploadResult, setLatestUploadResult] = useState(null);" in source
    assert "const loadLatestUploadState = useCallback(async () => {" in source
    assert "setLatestUploadSnapshot(payload.snapshot);" in source
    assert "setLatestUploadResult(payload.latestResult);" in source
    assert "window.localStorage" not in source


def test_frontend_uses_single_data_connections_workspace_for_uploads() -> None:
    source = read_upload_surface()
    workspaces_source = read_frontend(WORKSPACES_CONFIG)

    assert 'label: "Telemetry Intake"' not in source
    assert 'title="Telemetry intake"' not in source
    assert 'label: "Data Connections"' in workspaces_source
    assert 'Upload Telemetry File' in source
    assert 'title="Upload History"' in source
    assert 'title="Change Summary"' in source
    assert 'label: "Evidence Lineage"' in workspaces_source
