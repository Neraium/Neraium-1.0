import {
  API_BASE_URL,
  API_ROUTE_MODE,
  CONFIGURED_API_BASE_URL,
  buildAccessHeaders,
  buildApiDebugState,
  buildApiUrl,
} from "../../config";
import * as uploadStateView from "../../viewModels/uploadState";
import { normalizeUploadJob } from "../../viewModels/uploadContract";
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

export function clearLatestUploadStateCache() {
  latestUploadInflight.clear();
  latestUploadCache.clear();
}

export async function fetchLatestUploadState({ apiFetch, accessCode, includePersisted = false, forceRefresh = false } = {}) {
  const key = `latest:${includePersisted ? 1 : 0}`;
  const now = Date.now();
  if (forceRefresh) {
    latestUploadInflight.delete(key);
    latestUploadCache.delete(key);
  } else {
    const cached = latestUploadCache.get(key);
    if (cached && cached.expiresAt > now) {
      return cached.value;
    }
    const inFlight = latestUploadInflight.get(key);
    if (inFlight) return inFlight;
  }

  const request = (async () => {
    const path = `/api/data/latest-upload?include_persisted=${includePersisted ? 1 : 0}`;
    let lastError = null;

    for (let attempt = 0; attempt <= LATEST_UPLOAD_MAX_RETRIES; attempt += 1) {
      try {
        const response = await apiFetch(path, { accessCode });
        const rawPayload = await readJsonPayload(response, { route: path, phase: "result" });
        if (!response.ok) {
          const requestError = buildUploadRequestError(response, rawPayload, "result");
          throw Object.assign(new Error(requestError.detail || "Analysis results could not be loaded. Refresh and retry."), requestError);
        }

        const normalizedSnapshot = uploadStateView.normalizeLatestUploadPayload(rawPayload);
        const latestResult = uploadStateView.resolveCurrentUploadResult(normalizedSnapshot);
        const normalizedLatestResult = uploadStateView.hasFullUploadResult(latestResult) ? latestResult : null;
        const value = {
          snapshot: normalizedSnapshot,
          latestResult: normalizedLatestResult,
        };
        latestUploadCache.set(key, { expiresAt: Date.now() + LATEST_UPLOAD_DEDUPE_TTL_MS, value });
        return value;
      } catch (error) {
        lastError = error;
        if (attempt >= LATEST_UPLOAD_MAX_RETRIES || !isTransientLatestUploadError(error)) break;
        console.info("[neraium] latest telemetry retry scheduled", { attempt: attempt + 1, status: error?.status ?? null });
        await sleep(latestUploadRetryDelayMs(attempt));
      }
    }

    throw lastError;
  })();

  latestUploadInflight.set(key, request);
  try {
    return await request;
  } finally {
    latestUploadInflight.delete(key);
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
  if (!rawBody) return {};
  try {
    return JSON.parse(rawBody);
  } catch {
    return buildUploadServiceUnavailablePayload({
      status: xhr.status,
      rawBody,
      route,
      phase,
      contentType,
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

function uploadTelemetryFileDirectWithProgress({ file, timeoutMs = 4 * 60 * 60 * 1000, onProgress, onDebug, accessCode } = {}) {
  return new Promise((resolve, reject) => {
    if (!file) {
      reject(new Error("Choose a CSV or JSON telemetry file to upload."));
      return;
    }

    const startedAt = Date.now();
    const uploadUrl = buildApiUrl("/api/data/upload");
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
      const clearResponseGraceTimer = () => {
        if (responseGraceTimer) {
          cancelTimer(responseGraceTimer);
          responseGraceTimer = null;
        }
      };
      formData.append("file", file);
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

      xhr.onload = () => {
        responseSettled = true;
        clearResponseGraceTimer();
        const payload = normalizeUploadJob(readJsonResponse(xhr, { route: uploadUrl, phase: "upload" }));
        const response = { ok: xhr.status >= 200 && xhr.status < 300, status: xhr.status, payload };
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
        if (isTransientUploadServiceStatus(xhr.status) && retryCount < MAX_SAME_URL_RETRIES) {
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
        reject(buildUploadXhrError(xhr, payload, uploadUrl, "upload"));
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

        if (retryCount < MAX_SAME_URL_RETRIES) {
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
          `Upload network error before server accepted the file. Failed URL: ${uploadUrl}`
        );
        error.name = "ApiNetworkError";
        error.apiBaseUrl = uploadUrl;
        error.attempt = retryCount + 1;
        error.status = xhr.status;
        error.responseText = xhr.responseText;
        error.uploadUrl = uploadUrl;
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

        if (retryCount < MAX_SAME_URL_RETRIES) {
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
          `Upload request timed out before server accepted the file. Failed URL: ${uploadUrl}`
        );
        error.name = "ApiTimeoutError";
        error.timeoutMs = timeoutMs;
        error.status = xhr.status;
        error.responseText = xhr.responseText;
        error.uploadUrl = uploadUrl;
        reject(error);
      };

      xhr.onabort = () => {
        clearResponseGraceTimer();
      };

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

async function requestLargeUploadSession({ file, apiFetch, accessCode }) {
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
      }),
    });
  } catch (error) {
    error.phase = error.phase || "upload_session";
    throw error;
  }
  const payload = await readJsonPayload(response, { route: path, phase: "upload_session" });
  if (!response.ok) {
    throw largeUploadRequestError(response, payload, "upload_session", "Upload could not start. Check the connection and try again.");
  }
  const sessionId = String(payload?.upload_session_id || "").trim();
  const uploadUrl = String(payload?.upload_url || "").trim();
  if (!sessionId || !uploadUrl) {
    throw Object.assign(new Error("Upload could not start. Check the connection and try again."), {
      name: "UploadRequestError",
      phase: "upload_session",
      errorType: "invalid_upload_session",
      detail: "Upload could not start. Check the connection and try again.",
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
        message: percent === 100 ? "Upload completed. Validating data." : "Uploading dataset.",
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
      reject(Object.assign(new Error("Upload could not be completed. Check the connection and try again."), {
        name: "UploadRequestError",
        status: xhr.status || null,
        phase: "upload",
        errorType: "object_storage_upload_failed",
        detail: "Upload could not be completed. Check the connection and try again.",
        retryable: true,
      }));
    };
    xhr.onerror = () => reject(Object.assign(new Error("Upload could not be completed. Check the connection and try again."), {
      name: "ApiNetworkError",
      phase: "upload",
      errorType: "network",
      status: xhr.status || null,
    }));
    xhr.ontimeout = () => reject(Object.assign(new Error("Upload timed out. Check the connection and try again."), {
      name: "ApiTimeoutError",
      phase: "upload",
      errorType: "timeout",
      status: xhr.status || 408,
      timeoutMs,
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
    message: "Validating data",
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
    throw error;
  }
  const payload = await readJsonPayload(response, { route: path, phase: "job_creation" });
  if (!response.ok) {
    const fallback = response.status >= 500
      ? "Upload completed, but analysis could not be started."
      : "Upload could not be verified. Check the connection and try again.";
    throw largeUploadRequestError(response, payload, "job_creation", fallback);
  }
  const normalized = normalizeUploadJob(payload);
  if (!normalized?.job_id) {
    throw Object.assign(new Error("Upload completed, but analysis could not be started."), {
      name: "UploadRequestError",
      phase: "job_creation",
      errorType: "missing_job_id",
      detail: "Upload completed, but analysis could not be started.",
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

async function uploadLargeTelemetryFileWithProgress({ file, timeoutMs = 4 * 60 * 60 * 1000, onProgress, onDebug, accessCode, apiFetch }) {
  if (typeof apiFetch !== "function") {
    throw new Error("Upload could not start. Check the connection and try again.");
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
  let completedTransfer = completedLargeTransfers.get(file);
  if (!completedTransfer) {
    const session = await requestLargeUploadSession({ file, apiFetch, accessCode });
    const transferred = await putFileToObjectStorage({ file, session, timeoutMs, onProgress });
    completedTransfer = { session, etag: transferred.etag };
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

export function uploadTelemetryFileWithProgress(options = {}) {
  const fileSize = Number(options?.file?.size || 0);
  if (fileSize > DIRECT_UPLOAD_MAX_BYTES) {
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
