from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_JSX = ROOT / "frontend" / "src" / "App.jsx"
CONFIG_JS = ROOT / "frontend" / "src" / "config.js"


def read_frontend(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_shared_api_helper_forces_credentials_include() -> None:
    source = read_frontend(CONFIG_JS)

    assert 'trim().replace(/\\/+$/, "")' in source
    assert 'credentials: "include"' in source
    assert "return fetch(`${API_BASE_URL}${path}`" in source
    assert "const { accessCode = APP_ACCESS_CODE, headers, ...rest } = options;" in source
    assert "...(headers ?? {})" in source
    assert 'export const ACCESS_CODE_SESSION_KEY = "neraium_access_code";' in source
    assert "window.sessionStorage.getItem(ACCESS_CODE_SESSION_KEY)" in source


def test_upload_and_polling_use_shared_credentialed_api_helper() -> None:
    source = read_frontend(APP_JSX)

    for endpoint in (
        'apiFetch("/api/data/upload"',
        "apiFetch(`/api/data/upload-status/${pollingJobId}`",
        'apiFetch("/api/data/latest-upload"',
        'apiFetch("/api/facility/systems"',
        'apiFetch("/api/intelligence/engine-identity"',
        'apiFetch("/api/health"',
    ):
        assert endpoint in source


def test_multipart_upload_does_not_set_form_data_content_type() -> None:
    source = read_frontend(APP_JSX)
    upload_start = source.index('apiFetch("/api/data/upload"')
    upload_end = source.index("const payload = await readJsonPayload(response);", upload_start)
    upload_block = source[upload_start:upload_end]

    assert 'method: "POST"' in upload_block
    assert "body: formData" in upload_block
    assert "Content-Type" not in upload_block


def test_polling_does_not_enter_error_state_on_single_auth_failure() -> None:
    source = read_frontend(APP_JSX)

    assert "const isAuthDuringPolling = phase === \"poll\" && (error.status === 401 || error.status === 403);" in source
    assert 'state: isAuthDuringPolling || (phase === "poll" && error.retryable) ? "running_sii" : "error"' in source


def test_upload_polling_preserves_returned_job_id() -> None:
    source = read_frontend(APP_JSX)

    assert "const uploadJobIdRef = useRef(null);" in source
    assert "uploadJobIdRef.current = payload.job_id;" in source
    assert "const pollingJobId = jobId || uploadJobIdRef.current;" in source
    assert "apiFetch(`/api/data/upload-status/${pollingJobId}`" in source
    assert 'throw buildUploadRequestError(response, { ...payload, error_type: "upload_session_missing", message: "Upload state unavailable." }, "upload");' in source


def test_object_errors_render_through_normalized_messages() -> None:
    source = read_frontend(APP_JSX)

    assert "function normalizeErrorMessage(error)" in source
    assert "return JSON.stringify(error);" in source
    assert "{normalizeErrorMessage(uploadError)}" in source
    assert "{safeMessage}" in source


def test_https_access_cookie_supports_cross_origin_ecs_api() -> None:
    source = read_frontend(APP_JSX)

    assert 'window.location.protocol === "https:" ? "; SameSite=None" : "; SameSite=Lax"' in source
    assert 'window.location.protocol === "https:" ? "; Secure" : ""' in source


def test_protected_route_unauthorized_copy_is_session_expired() -> None:
    source = read_frontend(APP_JSX)

    assert "Session expired. Refresh workspace." in source
    assert "[object Object]" not in source
    assert "Upload processing interrupted." in source
    assert "Upload state unavailable." in source


def test_upload_failure_console_log_uses_readable_fields() -> None:
    source = read_frontend(APP_JSX)

    assert "telemetry_upload_failure" in source
    assert "`message=${classified.message}`" in source
    assert "`status=${classified.status ?? \"n/a\"}`" in source
    assert "`error_type=${classified.errorType ?? \"n/a\"}`" in source
    assert 'console.warn("telemetry_upload_failure", classified)' not in source
