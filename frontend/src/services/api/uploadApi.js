import {
  API_BASE_URL,
  API_ROUTE_MODE,
  CONFIGURED_API_BASE_URL,
  buildAccessHeaders,
  buildApiDebugState,
  buildApiUrl,
} from "../../config";
import * as uploadStateView from "../../viewModels/uploadState";
import { getCurrentWorkspaceId } from "../datasetSessionCache";
import { normalizeUploadJob } from "../../viewModels/uploadContract";
import { analysisBelongsToBaseline } from "../../viewModels/baselineSelection";
import {
  SERVICE_UNAVAILABLE_RETRY_MESSAGE,
  buildUploadRequestError,
  buildUploadServiceUnavailablePayload,
  isTransientUploadServiceStatus,
  readJsonPayload,
} from "../../viewModels/uploadFlow";

const LATEST_UPLOAD_DEDUPE_TTL_MS = 4000;
const LATEST_UPLOAD_MAX_RETRIES = 2;

function latestUploadRetryDelayMs(attempt) {
  return [500, 1200][attempt] ?? 1200;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isTransientLatestUploadError(error) {
  const status = Number(error?.status ?? error?.responseStatus ?? 0);
  return error?.name === "ApiTimeoutError"
    || error?.name === "ApiNetworkError"
    || status === 408
    || status === 429
    || (status >= 500 && status <= 504);
}
const latestUploadInflight = new Map();
const latestUploadCache = new Map();
const latestUploadRequestVersion = new Map();

export function clearLatestUploadStateCache({ scopeKey = null, portfolioId = null } = {}) {
  const encodedScope = scopeKey ? encodeURIComponent(scopeKey) : null;
  const encodedPortfolio = portfolioId ? encodeURIComponent(portfolioId) : null;
  const matches = (key) => {
    const parts = String(key).split(":");
    return (!encodedScope || parts[1] === encodedScope) && (!encodedPortfolio || parts[2] === encodedPortfolio);
  };
  for (const [key, entry] of latestUploadInflight.entries()) {
    if (matches(key)) {
      entry.controller?.abort();
      latestUploadInflight.delete(key);
      latestUploadRequestVersion.set(key, (latestUploadRequestVersion.get(key) ?? 0) + 1);
    }
  }
  for (const key of latestUploadCache.keys()) {
    if (matches(key)) latestUploadCache.delete(key);
  }
}

export async function fetchLatestUploadState({ apiFetch, accessCode, scopeKey = "anonymous", includePersisted = false, forceRefresh = false, exactAnalysisIdentity = null } = {}) {
  const portfolioId = String(exactAnalysisIdentity?.portfolioId || getCurrentWorkspaceId());
  const systemId = String(exactAnalysisIdentity?.systemId || portfolioId);
  const baselineId = String(exactAnalysisIdentity?.baselineId || "");
  const analysisRunId = String(exactAnalysisIdentity?.analysisRunId || "");
  const exactAnalysis = Boolean(baselineId && analysisRunId);
  const key = exactAnalysis
    ? `analysis:${encodeURIComponent(scopeKey)}:${encodeURIComponent(portfolioId)}:${encodeURIComponent(systemId)}:${encodeURIComponent(baselineId)}:${encodeURIComponent(analysisRunId)}:${encodeURIComponent(analysisRunId)}`
    : `latest:${encodeURIComponent(scopeKey)}:${encodeURIComponent(portfolioId)}:${includePersisted ? 1 : 0}`;
  const now = Date.now();
  if (forceRefresh) clearLatestUploadStateCache({ scopeKey, portfolioId });
  else {
    const cached = latestUploadCache.get(key);
    if (cached && cached.expiresAt > now) return cached.value;
    const inFlight = latestUploadInflight.get(key);
    if (inFlight) return inFlight.promise;
  }

  const requestVersion = (latestUploadRequestVersion.get(key) ?? 0) + 1;
  latestUploadRequestVersion.set(key, requestVersion);
  const controller = new AbortController();
  const request = (async () => {
    const path = exactAnalysis
      ? `/api/data/portfolios/${encodeURIComponent(portfolioId)}/systems/${encodeURIComponent(systemId)}/baselines/${encodeURIComponent(baselineId)}/analyses/${encodeURIComponent(analysisRunId)}`
      : `/api/data/latest-upload?include_persisted=${includePersisted ? 1 : 0}`;
    let lastError = null;

    for (let attempt = 0; attempt <= LATEST_UPLOAD_MAX_RETRIES; attempt += 1) {
      try {
        const response = await apiFetch(path, {
          accessCode,
          signal: controller.signal,
          headers: { "X-Neraium-Workspace-Id": portfolioId },
        });
        const responsePayload = await readJsonPayload(response, { route: path, phase: "result" });
        if (!response.ok) {
          const requestError = buildUploadRequestError(response, responsePayload, "result");
          throw Object.assign(new Error(requestError.detail || "Analysis results could not be loaded. Refresh and retry."), requestError);
        }

        if (exactAnalysis && !analysisBelongsToBaseline(responsePayload, { ...exactAnalysisIdentity, portfolioId, systemId, baselineId, analysisRunId })) {
          throw Object.assign(new Error("The requested analysis does not belong to this baseline."), {
            name: "UploadRequestError",
            errorType: "analysis_ownership_mismatch",
            status: 404,
            retryable: false,
          });
        }
        const rawPayload = exactAnalysis ? {
          status: responsePayload?.status ?? "COMPLETE",
          processing_state: responsePayload?.processing_state ?? "complete",
          session_state: "exact_analysis",
          latest_result: responsePayload,
          current_upload: {
            job_id: responsePayload?.job_id,
            upload_id: responsePayload?.upload_id,
            dataset_id: responsePayload?.dataset_id,
            status: responsePayload?.status ?? "COMPLETE",
            result: responsePayload,
          },
          history: [],
        } : responsePayload;
        const normalizedSnapshot = uploadStateView.normalizeLatestUploadPayload(rawPayload);
        const latestResult = uploadStateView.resolveCurrentUploadResult(normalizedSnapshot);
        const normalizedLatestResult = uploadStateView.hasFullUploadResult(latestResult) ? latestResult : null;
        const value = { snapshot: normalizedSnapshot, latestResult: normalizedLatestResult };
        if (latestUploadRequestVersion.get(key) === requestVersion && (exactAnalysis || getCurrentWorkspaceId() === portfolioId)) {
          latestUploadCache.set(key, { expiresAt: Date.now() + LATEST_UPLOAD_DEDUPE_TTL_MS, value });
        }
        return value;
      } catch (error) {
        lastError = error;
        if (error?.name === "AbortError" || attempt >= LATEST_UPLOAD_MAX_RETRIES || !isTransientLatestUploadError(error)) break;
        console.info("[neraium] latest telemetry retry scheduled", { attempt: attempt + 1, status: error?.status ?? null });
        await sleep(latestUploadRetryDelayMs(attempt));
      }
    }

    throw lastError;
  })();

  latestUploadInflight.set(key, { promise: request, controller, requestVersion });
  try {
    return await request;
  } finally {
    if (latestUploadInflight.get(key)?.requestVersion === requestVersion) latestUploadInflight.delete(key);
  }
}

export async function resetDemoSession({ apiFetch, accessCode }) {
  const response = await apiFetch("/api/data/reset", {
    method: "POST",
    accessCode,
  });
  if (!response.ok) {
    throw new Error("Analysis status could not be loaded. Refresh and retry.");
  }
  return response.json();
}

function xhrHeader(xhr, key) {
  try {
    return xhr.getResponseHeader?.(key) || "";
  } catch {
    return "";
  }
}

function readJsonResponse(xhr, { route = "", phase = "" } = {}) {
  const rawBody = String(xhr.responseText || "");
  const contentType = xhrHeader(xhr, "content-type");
  const requestId = xhrHeader(xhr, "x-request-id");
  const diagnostic_timestamp = new Date().toISOString();
  if (!rawBody) return { request_id: requestId || null, diagnostic_timestamp };
  try {
    const payload = JSON.parse(rawBody);
    return {
      ...payload,
      request_id: payload?.request_id ?? requestId ?? null,
      diagnostic_timestamp: payload?.diagnostic_timestamp ?? diagnostic_timestamp,
      response_status: Number(xhr.status || 0) || payload?.response_status || null,
    };
  } catch {
    return buildUploadServiceUnavailablePayload({
      status: xhr.status,
      rawBody,
      route,
      phase,
      contentType,
      requestId,
    });
  }
}

function buildUploadXhrError(xhr, payload, uploadUrl, phase) {
  const requestError = buildUploadRequestError({ status: xhr.status, url: uploadUrl }, payload, phase);
  const error = new Error(requestError.detail || "The dataset could not be imported. Check the file and retry.");
  return Object.assign(error, requestError, {
    responseText: requestError.rawResponseBody || xhr.responseText || "",
    uploadUrl,
  });
}

function uploadRetryDelayMs(retryCount) {
  return [600, 1200, 2200][retryCount] ?? 2200;
}

function logUploadFailureDiagnostics(label, details) {
  if (!import.meta.env.DEV) return;
  console.warn(`[neraium] ${label}`, {
    url: details?.url ?? null,
    phase: details?.phase ?? null,
    status: details?.status ?? null,
    attempt: details?.attempt ?? null,
    errorType: details?.errorType ?? null,
  });
}

function getUploadResponseTimeoutMs(fileSizeBytes, baseTimeoutMs) {
  const size = Number(fileSizeBytes) || 0;
  const base = Number(baseTimeoutMs) || 0;
  const mobileMinimumMs = 90 * 1000;
  const largeFileMinimumMs = size >= 1024 * 1024 * 1024 ? 30 * 60 * 1000 : size >= 25 * 1024 * 1024 ? 3 * 60 * 1000 : mobileMinimumMs;
  return Math.min(Math.max(base || largeFileMinimumMs, largeFileMinimumMs), 30 * 60 * 1000);
}

function uploadTelemetryFileDirectWithProgress({ file, workflow = "legacy_analysis", approvalRequired, baselineIdentity, timeoutMs = 4 * 60 * 60 * 1000, onProgress, onDebug, onTiming, requestStartedAt, accessCode } = {}) {
  return new Promise((resolve, reject) => {
    if (!file) {
      reject(new Error("Choose a CSV or JSON telemetry file to upload."));
      return;
    }

    const startedAt = Date.now();
    const interactionStartedAt = Number.isFinite(Number(requestStartedAt)) ? Number(requestStartedAt) : startedAt;
    const uploadUrl = buildApiUrl("/api/data/upload");
    const emitTiming = (event, values = {}) => {
      const timing = { event, at: new Date().toISOString(), ...values };
      console.info("[neraium] upload timing", timing);
      onTiming?.(timing);
    };
    const debugState = buildApiDebugState("/api/data/upload");
    console.info("[neraium] upload endpoint", {
      uploadUrl,
      apiBaseConfig: CONFIGURED_API_BASE_URL || "",
      runtimeApiBaseUrl: API_BASE_URL || "",
      routeMode: API_ROUTE_MODE,
    });
    onDebug?.({
      uploadUrl,
      apiBaseConfig: CONFIGURED_API_BASE_URL || "",
      runtimeApiBaseUrl: API_BASE_URL || "",
      routeMode: API_ROUTE_MODE,
      responseStatus: null,
      responseBodyOrError: "",
    });

    onProgress?.({
      stage: "upload_started",
      loaded: 0,
      total: file.size,
      percent: 0,
      speedBytesPerSecond: 0,
      message: "Upload started.",
    });

    const MAX_SAME_URL_RETRIES = 2;
    const RESPONSE_GRACE_TIMEOUT_MS = getUploadResponseTimeoutMs(file.size, timeoutMs);
    const scheduleTimer = typeof window !== "undefined" ? window.setTimeout.bind(window) : setTimeout;
    const cancelTimer = typeof window !== "undefined" ? window.clearTimeout.bind(window) : clearTimeout;

    const uploadAttempt = (retryCount = 0) => {
      const xhr = new XMLHttpRequest();
      const formData = new FormData();
      let responseGraceTimer = null;
      let responseSettled = false;
      let attemptLoaded = 0;
      let transferCompletedAt = null;
      let requestDispatchedAt = startedAt;
      const clearResponseGraceTimer = () => {
        if (responseGraceTimer) {
          cancelTimer(responseGraceTimer);
          responseGraceTimer = null;
        }
      };
      formData.append("file", file);
      formData.append("workflow", String(workflow || "legacy_analysis"));
      if (typeof approvalRequired === "boolean") {
        formData.append("approval_required", approvalRequired ? "true" : "false");
      }
      if (workflow === "analyze_new_data" && baselineIdentity?.baselineId) {
        formData.append("baseline_id", String(baselineIdentity.baselineId));
        formData.append("portfolio_id", String(baselineIdentity.portfolioId || ""));
        formData.append("system_id", String(baselineIdentity.systemId || baselineIdentity.portfolioId || ""));
      }
      xhr.open("POST", uploadUrl, true);
      xhr.withCredentials = true;
      xhr.timeout = timeoutMs;

      Object.entries(buildAccessHeaders(accessCode)).forEach(([key, value]) => {
        xhr.setRequestHeader(key, value);
      });

      onProgress?.({
        stage: "uploading",
        loaded: 0,
        total: file.size,
        percent: file.size > 0 ? 1 : 0,
        speedBytesPerSecond: 0,
        message: "Connecting to telemetry ingestion.",
      });

      xhr.upload.onloadstart = () => {
        onProgress?.({
          stage: "uploading",
          loaded: 0,
          total: file.size,
          percent: file.size > 0 ? 1 : 0,
          speedBytesPerSecond: 0,
          message: "Connecting to telemetry ingestion.",
        });
      };

      xhr.upload.onprogress = (event) => {
        const loaded = event.loaded ?? 0;
        attemptLoaded = Math.max(attemptLoaded, loaded);
        const total = event.lengthComputable ? event.total : file.size;
        const elapsedSeconds = Math.max((Date.now() - startedAt) / 1000, 0.001);
        const percent = total > 0 ? Math.min(100, Math.round((loaded / total) * 100)) : null;
        onProgress?.({
          stage: percent === 100 ? "upload_transferred" : "uploading",
          loaded,
          total,
          percent,
          speedBytesPerSecond: loaded / elapsedSeconds,
          message: percent === 100 ? "Upload transferred. Waiting for server confirmation." : "Uploading telemetry export.",
        });
        if (!responseSettled && total > 0 && loaded >= total && !responseGraceTimer) {
          responseGraceTimer = scheduleTimer(() => {
            if (responseSettled || xhr.readyState === 4) return;
            try {
              xhr.abort();
            } catch {
              // no-op
            }
            const error = new Error("Upload transferred, but the server did not confirm the job before the response timeout.");
            error.name = "ApiTimeoutError";
            error.timeoutMs = RESPONSE_GRACE_TIMEOUT_MS;
            error.error_type = "upload_response_timeout";
            error.status = xhr.status;
            reject(error);
          }, RESPONSE_GRACE_TIMEOUT_MS);
        }
      };

      xhr.upload.onload = () => {
        attemptLoaded = Math.max(attemptLoaded, file.size || 0);
        transferCompletedAt = Date.now();
        emitTiming("upload_transfer_complete", {
          attempt: retryCount + 1,
          upload_transfer_ms: Math.max(0, transferCompletedAt - startedAt),
          file_size_bytes: file.size,
        });
      };

      xhr.onload = () => {
        responseSettled = true;
        clearResponseGraceTimer();
        const responseReceivedAt = Date.now();
        const payload = normalizeUploadJob(readJsonResponse(xhr, { route: uploadUrl, phase: "upload" }));
        const response = { ok: xhr.status >= 200 && xhr.status < 300, status: xhr.status, payload };
        emitTiming("upload_response_received", {
          attempt: retryCount + 1,
          frontend_request_dispatch_ms: Math.max(0, requestDispatchedAt - interactionStartedAt),
          upload_transfer_ms: transferCompletedAt ? Math.max(0, transferCompletedAt - startedAt) : null,
          backend_confirmation_ms: transferCompletedAt ? Math.max(0, responseReceivedAt - transferCompletedAt) : null,
          upload_request_total_ms: Math.max(0, responseReceivedAt - interactionStartedAt),
          backend_timings: payload?.timings ?? null,
          status: xhr.status,
        });
        onDebug?.({
          ...debugState,
          responseStatus: xhr.status,
          responseBodyOrError: xhr.responseText || JSON.stringify(payload || {}),
        });
        if (response.ok) {
          onProgress?.({
            stage: "accepted",
            loaded: file.size,
            total: file.size,
            percent: 100,
            speedBytesPerSecond: file.size / Math.max((Date.now() - startedAt) / 1000, 0.001),
            message: payload?.message ?? "File accepted.",
          });
          resolve(response);
          return;
        }
        const errorType = payload?.error_type ?? payload?.detail?.error_type ?? null;
        logUploadFailureDiagnostics("upload HTTP error", {
          url: uploadUrl,
          phase: "upload",
          attempt: retryCount + 1,
          status: xhr.status,
          errorType,
        });
        if (isTransientUploadServiceStatus(xhr.status) && retryCount < MAX_SAME_URL_RETRIES && attemptLoaded === 0) {
          onProgress?.({
            stage: "upload_retrying",
            loaded: file.size,
            total: file.size,
            percent: 100,
            speedBytesPerSecond: 0,
            message: SERVICE_UNAVAILABLE_RETRY_MESSAGE,
          });
          scheduleTimer(() => uploadAttempt(retryCount + 1), uploadRetryDelayMs(retryCount));
          return;
        }
        const uploadError = buildUploadXhrError(xhr, payload, uploadUrl, "upload");
        uploadError.transferSucceeded = uploadError.transferSucceeded === true || (file.size > 0 && attemptLoaded >= file.size);
        uploadError.failedStage = uploadError.failedStage || (uploadError.transferSucceeded ? "dataset_creation" : "upload_transfer");
        reject(uploadError);
      };

      xhr.onerror = () => {
        responseSettled = true;
        clearResponseGraceTimer();
        onDebug?.({
          ...debugState,
          responseStatus: xhr.status || null,
          responseBodyOrError: xhr.responseText || `Network error while calling ${uploadUrl}`,
        });
        logUploadFailureDiagnostics("upload network error", {
          url: uploadUrl,
          phase: "upload",
          attempt: retryCount + 1,
          status: xhr.status || null,
          errorType: "network",
        });

        if (retryCount < MAX_SAME_URL_RETRIES && attemptLoaded === 0) {
          onProgress?.({
            stage: "upload_retrying",
            loaded: file.size,
            total: file.size,
            percent: file.size > 0 ? 100 : 0,
            speedBytesPerSecond: 0,
            message: SERVICE_UNAVAILABLE_RETRY_MESSAGE,
          });
          scheduleTimer(() => uploadAttempt(retryCount + 1), uploadRetryDelayMs(retryCount));
          return;
        }

        const error = new Error(
          `Upload connection failed before server acceptance could be confirmed. Failed URL: ${uploadUrl}`
        );
        error.name = "ApiNetworkError";
        error.apiBaseUrl = uploadUrl;
        error.attempt = retryCount + 1;
        error.status = xhr.status;
        error.responseText = xhr.responseText;
        error.uploadUrl = uploadUrl;
        error.transferSucceeded = file.size > 0 && attemptLoaded >= file.size;
        error.failedStage = error.transferSucceeded ? "dataset_creation" : "upload_transfer";
        reject(error);
      };

      xhr.ontimeout = () => {
        responseSettled = true;
        clearResponseGraceTimer();
        onDebug?.({
          ...debugState,
          responseStatus: xhr.status || 408,
          responseBodyOrError: xhr.responseText || `Timeout while calling ${uploadUrl}`,
        });
        logUploadFailureDiagnostics("upload timeout", {
          url: uploadUrl,
          phase: "upload",
          attempt: retryCount + 1,
          status: xhr.status || 408,
          errorType: "timeout",
        });

        if (retryCount < MAX_SAME_URL_RETRIES && attemptLoaded === 0) {
          onProgress?.({
            stage: "upload_retrying",
            loaded: file.size,
            total: file.size,
            percent: file.size > 0 ? 100 : 0,
            speedBytesPerSecond: 0,
            message: SERVICE_UNAVAILABLE_RETRY_MESSAGE,
          });
          scheduleTimer(() => uploadAttempt(retryCount + 1), uploadRetryDelayMs(retryCount));
          return;
        }

        const error = new Error(
          `Upload request timed out before server acceptance could be confirmed. Failed URL: ${uploadUrl}`
        );
        error.name = "ApiTimeoutError";
        error.timeoutMs = timeoutMs;
        error.status = xhr.status;
        error.responseText = xhr.responseText;
        error.uploadUrl = uploadUrl;
        error.transferSucceeded = file.size > 0 && attemptLoaded >= file.size;
        error.failedStage = error.transferSucceeded ? "dataset_creation" : "upload_transfer";
        reject(error);
      };

      xhr.onabort = () => {
        clearResponseGraceTimer();
      };

      requestDispatchedAt = Date.now();
      emitTiming("frontend_request_dispatched", {
        attempt: retryCount + 1,
        frontend_request_dispatch_ms: Math.max(0, requestDispatchedAt - interactionStartedAt),
      });
      xhr.send(formData);
    };

    uploadAttempt(0);
  });
}


export const DIRECT_UPLOAD_MAX_BYTES = 250 * 1024 * 1024;
export const LARGE_UPLOAD_MAX_BYTES = 512 * 1024 * 1024;

const completedLargeTransfers = new WeakMap();

function largeUploadRequestError(response, payload, phase, fallback) {
  const requestError = buildUploadRequestError(response, payload, phase);
  return Object.assign(new Error(requestError.detail || fallback), requestError);
}

async function requestLargeUploadSession({ file, workflow = "legacy_analysis", approvalRequired, baselineIdentity, apiFetch, accessCode }) {
  const path = "/api/data/upload-session";
  let response;
  try {
    response = await apiFetch(path, {
      method: "POST",
      accessCode,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        filename: file.name,
        size_bytes: file.size,
        content_type: file.type || "text/csv",
        workflow: String(workflow || "legacy_analysis"),
        ...(typeof approvalRequired === "boolean" ? { approval_required: approvalRequired } : {}),
        ...(workflow === "analyze_new_data" && baselineIdentity?.baselineId ? {
          baseline_id: String(baselineIdentity.baselineId),
          portfolio_id: String(baselineIdentity.portfolioId || ""),
          system_id: String(baselineIdentity.systemId || baselineIdentity.portfolioId || ""),
        } : {}),
      }),
    });
  } catch (error) {
    error.phase = error.phase || "upload_session";
    throw error;
  }
  const payload = await readJsonPayload(response, { route: path, phase: "upload_session" });
  if (!response.ok) {
    throw largeUploadRequestError(response, payload, "upload_session", "The upload session could not be created. Retry the import.");
  }
  const sessionId = String(payload?.upload_session_id || "").trim();
  const uploadUrl = String(payload?.upload_url || "").trim();
  if (!sessionId || !uploadUrl) {
    throw Object.assign(new Error("The upload session could not be created. Retry the import."), {
      name: "UploadRequestError",
      phase: "upload_session",
      errorType: "dataset_record_creation_failed",
      detail: "The upload session could not be created. Retry the import.",
      failedStage: "dataset_creation",
      retryable: true,
    });
  }
  console.info("[neraium] upload session created", { uploadSessionId: sessionId, filename: file.name, size: file.size });
  return { ...payload, upload_session_id: sessionId, upload_url: uploadUrl };
}

function putFileToObjectStorage({ file, session, timeoutMs, onProgress }) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const startedAt = Date.now();
    xhr.open("PUT", session.upload_url, true);
    xhr.withCredentials = false;
    xhr.timeout = timeoutMs;
    Object.entries(session.upload_headers || {}).forEach(([key, value]) => {
      if (String(value || "")) xhr.setRequestHeader(key, String(value));
    });

    const reportProgress = (event) => {
      const loaded = Number(event?.loaded || 0);
      const total = event?.lengthComputable ? Number(event.total || file.size) : file.size;
      const elapsedSeconds = Math.max((Date.now() - startedAt) / 1000, 0.001);
      const percent = total > 0 ? Math.max(1, Math.min(100, Math.round((loaded / total) * 100))) : null;
      onProgress?.({
        stage: percent === 100 ? "upload_transferred" : "uploading",
        loaded,
        total,
        percent,
        speedBytesPerSecond: loaded / elapsedSeconds,
        message: percent === 100 ? "File transferred successfully." : "Uploading dataset.",
        transport: "presigned_s3_put",
      });
    };

    xhr.upload.onloadstart = () => reportProgress({ loaded: 0, total: file.size, lengthComputable: true });
    xhr.upload.onprogress = reportProgress;
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        reportProgress({ loaded: file.size, total: file.size, lengthComputable: true });
        resolve({ etag: xhrHeader(xhr, "etag") });
        return;
      }
      reject(Object.assign(new Error("The file could not be saved to secure storage."), {
        name: "UploadRequestError",
        status: xhr.status || null,
        phase: "upload",
        errorType: "file_storage_failed",
        detail: "The file could not be saved to secure storage.",
        failedStage: "file_storage",
        retryable: true,
      }));
    };
    xhr.onerror = () => reject(Object.assign(new Error("The file transfer failed. Check the connection and try again."), {
      name: "ApiNetworkError",
      phase: "upload",
      errorType: "network",
      status: xhr.status || null,
      failedStage: "upload_transfer",
      transferSucceeded: false,
    }));
    xhr.ontimeout = () => reject(Object.assign(new Error("The file transfer timed out. Check the connection and try again."), {
      name: "ApiTimeoutError",
      phase: "upload",
      errorType: "timeout",
      status: xhr.status || 408,
      timeoutMs,
      failedStage: "upload_transfer",
      transferSucceeded: false,
    }));
    xhr.onabort = () => reject(Object.assign(new Error("Upload was interrupted. Try again."), {
      name: "ApiNetworkError",
      phase: "upload",
      errorType: "aborted",
      status: xhr.status || null,
    }));

    console.info("[neraium] object storage upload started", {
      uploadSessionId: session.upload_session_id,
      filename: file.name,
      size: file.size,
    });
    xhr.send(file);
  });
}

async function completeLargeUploadSession({ session, etag, file, apiFetch, accessCode, onProgress }) {
  const path = `/api/data/upload-session/${encodeURIComponent(session.upload_session_id)}/complete`;
  onProgress?.({
    stage: "validating",
    loaded: file.size,
    total: file.size,
    percent: 100,
    speedBytesPerSecond: 0,
    message: "Transfer complete. Creating dataset record.",
    transport: "presigned_s3_put",
  });
  let response;
  try {
    response = await apiFetch(path, {
      method: "POST",
      accessCode,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ etag: String(etag || "").replace(/^"|"$/g, "") || null }),
    });
  } catch (error) {
    error.phase = error.phase || "job_creation";
    error.uploadSessionId = error.uploadSessionId || session.upload_session_id;
    error.jobId = error.jobId || session.upload_session_id;
    error.failedStage = error.failedStage || "dataset_creation";
    error.transferSucceeded = true;
    error.fileStored = true;
    error.retryable = error.retryable !== false;
    error.retryUrl = error.retryUrl || path;
    throw error;
  }
  const payload = await readJsonPayload(response, { route: path, phase: "job_creation" });
  if (!response.ok) {
    const fallback = response.status >= 500
      ? "The file was transferred successfully, but Neraium could not begin processing it."
      : "The stored file could not be verified.";
    throw Object.assign(
      largeUploadRequestError(response, payload, "job_creation", fallback),
      {
        uploadSessionId: payload?.upload_session_id || session.upload_session_id,
        jobId: payload?.job_id || session.upload_session_id,
        failedStage: payload?.failed_stage || "dataset_creation",
        transferSucceeded: true,
        fileStored: payload?.file_stored !== false,
        retryable: payload?.retryable !== false,
        retryUrl: payload?.retry_url || path,
      },
    );
  }
  const normalized = normalizeUploadJob(payload);
  if (!normalized?.job_id) {
    throw Object.assign(new Error("The file was transferred successfully, but Neraium could not begin processing it."), {
      name: "UploadRequestError",
      phase: "job_creation",
      errorType: "dataset_record_creation_failed",
      detail: "The file was transferred successfully, but Neraium could not begin processing it.",
      uploadSessionId: session.upload_session_id,
      jobId: session.upload_session_id,
      failedStage: "dataset_creation",
      transferSucceeded: true,
      fileStored: true,
      retryable: true,
      retryUrl: path,
    });
  }
  console.info("[neraium] analysis job created", {
    uploadSessionId: session.upload_session_id,
    jobId: normalized.job_id,
    filename: file.name,
    size: file.size,
  });
  return { ok: true, status: response.status, payload: normalized };
}

async function uploadLargeTelemetryFileWithProgress({ file, workflow = "legacy_analysis", approvalRequired, baselineIdentity, timeoutMs = 4 * 60 * 60 * 1000, onProgress, onDebug, accessCode, apiFetch }) {
  if (typeof apiFetch !== "function") {
    throw new Error("The upload session could not be created. Retry the import.");
  }
  onProgress?.({
    stage: "upload_started",
    loaded: 0,
    total: file.size,
    percent: 0,
    speedBytesPerSecond: 0,
    message: "Uploading dataset",
    transport: "presigned_s3_put",
  });
  onDebug?.({
    ...buildApiDebugState("/api/data/upload-session"),
    uploadUrl: buildApiUrl("/api/data/upload-session"),
    responseStatus: null,
    responseBodyOrError: "",
  });
  const baselineKey = workflow === "analyze_new_data"
    ? [baselineIdentity?.portfolioId, baselineIdentity?.systemId, baselineIdentity?.baselineId].map((value) => encodeURIComponent(String(value || ""))).join(":")
    : "";
  let completedTransfer = completedLargeTransfers.get(file);
  if (completedTransfer && completedTransfer.baselineKey !== baselineKey) {
    completedLargeTransfers.delete(file);
    completedTransfer = null;
  }
  if (!completedTransfer) {
    const session = await requestLargeUploadSession({ file, workflow, approvalRequired, baselineIdentity, apiFetch, accessCode });
    const transferred = await putFileToObjectStorage({ file, session, timeoutMs, onProgress });
    completedTransfer = { session, etag: transferred.etag, baselineKey };
    completedLargeTransfers.set(file, completedTransfer);
    console.info("[neraium] object storage upload completed", {
      uploadSessionId: session.upload_session_id,
      filename: file.name,
      size: file.size,
    });
  } else {
    console.info("[neraium] resuming analysis job creation for completed upload", {
      uploadSessionId: completedTransfer.session.upload_session_id,
      filename: file.name,
      size: file.size,
    });
  }
  const result = await completeLargeUploadSession({
    session: completedTransfer.session,
    etag: completedTransfer.etag,
    file,
    apiFetch,
    accessCode,
    onProgress,
  });
  completedLargeTransfers.delete(file);
  return result;
}

export function shouldUseStoredUploadTransport(fileSize, { preferStoredUpload = false } = {}) {
  return preferStoredUpload || Number(fileSize || 0) > DIRECT_UPLOAD_MAX_BYTES;
}

export function uploadTelemetryFileWithProgress(options = {}) {
  const fileSize = Number(options?.file?.size || 0);
  if (shouldUseStoredUploadTransport(fileSize, options)) {
    return uploadLargeTelemetryFileWithProgress(options);
  }
  return uploadTelemetryFileDirectWithProgress(options);
}


export async function retryUploadAnalysisJob({ jobId, apiFetch, accessCode } = {}) {
  const cleanJobId = String(jobId ?? "").trim();
  if (!cleanJobId) {
    throw new Error("No uploaded telemetry job is available to retry.");
  }
  const path = `/api/data/upload/${encodeURIComponent(cleanJobId)}/retry`;
  const response = await apiFetch(path, {
    method: "POST",
    accessCode,
  });
  const payload = await readJsonPayload(response, { route: path, phase: "retry" });
  if (!response.ok) {
    const requestError = buildUploadRequestError(response, payload, "retry");
    throw Object.assign(new Error(requestError.detail || "Analysis results could not be loaded. Refresh and retry."), requestError);
  }
  return { ok: true, status: response.status, payload: normalizeUploadJob(payload) };
}
