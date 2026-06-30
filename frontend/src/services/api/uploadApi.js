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
    const response = await apiFetch(path, { accessCode });
    const payload = await readJsonPayload(response, { route: path, phase: "result" });
    if (!response.ok) {
      const requestError = buildUploadRequestError(response, payload, "result");
      throw Object.assign(new Error(requestError.detail || `Unexpected response: ${response.status}`), requestError);
    }

    const latestResult = uploadStateView.resolveCurrentUploadResult(payload);
    const normalizedLatestResult = uploadStateView.hasFullUploadResult(latestResult) ? latestResult : null;
    const normalizedSnapshot = payload ?? uploadStateView.buildEmptyLatestUploadSnapshot();
    const value = {
      snapshot: normalizedSnapshot,
      latestResult: normalizedLatestResult,
    };
    latestUploadCache.set(key, { expiresAt: Date.now() + LATEST_UPLOAD_DEDUPE_TTL_MS, value });
    return value;
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
    throw new Error(`Unexpected response: ${response.status}`);
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
  const error = new Error(requestError.detail || `Unexpected response: ${xhr.status}`);
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

export function uploadTelemetryFileWithProgress({ file, timeoutMs = 4 * 60 * 60 * 1000, onProgress, onDebug, accessCode } = {}) {
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
    throw Object.assign(new Error(requestError.detail || `Unexpected response: ${response.status}`), requestError);
  }
  return { ok: true, status: response.status, payload: normalizeUploadJob(payload) };
}
