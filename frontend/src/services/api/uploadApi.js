import { buildAccessHeaders, buildApiCandidateUrls } from "../../config";
import * as uploadStateView from "../../viewModels/uploadState";
import { normalizeUploadJob } from "../../viewModels/uploadContract";

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
    const response = await apiFetch(`/api/data/latest-upload?include_persisted=${includePersisted ? 1 : 0}`, { accessCode });
    if (!response.ok) {
      throw new Error(`Unexpected response: ${response.status}`);
    }

    const payload = await response.json();
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

function readJsonResponse(xhr) {
  try {
    return xhr.responseText ? JSON.parse(xhr.responseText) : {};
  } catch {
    return { message: xhr.responseText || "Upload response was not valid JSON." };
  }
}

function getUploadResponseTimeoutMs(fileSizeBytes, baseTimeoutMs) {
  const size = Number(fileSizeBytes) || 0;
  const base = Number(baseTimeoutMs) || 0;
  const mobileMinimumMs = 90 * 1000;
  const largeFileMinimumMs = size >= 25 * 1024 * 1024 ? 3 * 60 * 1000 : mobileMinimumMs;
  return Math.min(Math.max(base || largeFileMinimumMs, largeFileMinimumMs), 10 * 60 * 1000);
}

export function uploadTelemetryFileWithProgress({ file, timeoutMs = 10 * 60 * 1000, onProgress, accessCode } = {}) {
  return new Promise((resolve, reject) => {
    if (!file) {
      reject(new Error("Choose a CSV or JSON telemetry file to upload."));
      return;
    }

    const startedAt = Date.now();
    const uploadUrls = buildApiCandidateUrls("/api/data/upload", { method: "POST", allowSameOriginFallback: true });

    onProgress?.({
      stage: "upload_started",
      loaded: 0,
      total: file.size,
      percent: 0,
      speedBytesPerSecond: 0,
      message: "Upload started.",
    });

    const shouldRetryStatus = (status) => status >= 500 || status === 404 || status === 405 || status === 408 || status === 425 || status === 429;
    const MAX_SAME_URL_RETRIES = 2;
    const RESPONSE_GRACE_TIMEOUT_MS = getUploadResponseTimeoutMs(file.size, timeoutMs);
    const scheduleTimer = typeof window !== "undefined" ? window.setTimeout.bind(window) : setTimeout;
    const cancelTimer = typeof window !== "undefined" ? window.clearTimeout.bind(window) : clearTimeout;

    const uploadAttempt = (index, retryCount = 0) => {
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
      xhr.open("POST", uploadUrls[index], true);
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
        // Mobile browsers can finish sending bytes well before the API has
        // written the temp file, created the queue job, and returned 202.
        // Keep the XHR open for large CSVs instead of aborting after 8s.
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
        const payload = normalizeUploadJob(readJsonResponse(xhr));
        const response = { ok: xhr.status >= 200 && xhr.status < 300, status: xhr.status, payload };
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
        if (index < uploadUrls.length - 1 && shouldRetryStatus(xhr.status)) {
          uploadAttempt(index + 1);
          return;
        }
        const detail = payload?.message ?? payload?.detail?.message ?? payload?.detail ?? payload?.error;
        const errorType = payload?.error_type ?? payload?.detail?.error_type ?? null;
        console.error("Upload HTTP error", {
          url: uploadUrls[index],
          attempt: index + 1,
          status: xhr.status,
          errorType,
          payload,
          responseText: xhr.responseText,
        });
        const error = new Error(detail ? String(detail) : `Unexpected response: ${xhr.status}`);
        error.name = "UploadRequestError";
        error.status = xhr.status;
        error.errorType = errorType;
        error.detail = detail;
        error.payload = payload;
        error.responseText = xhr.responseText;
        error.apiBaseUrl = uploadUrls[index];
        reject(error);
      };

      xhr.onerror = () => {
        responseSettled = true;
        clearResponseGraceTimer();
        console.error("Upload network error", {
          url: uploadUrls[index],
          attempt: index + 1,
          readyState: xhr.readyState,
          status: xhr.status,
          responseText: xhr.responseText,
          attemptedUrls: uploadUrls.slice(0, index + 1),
        });

        if (index < uploadUrls.length - 1) {
          uploadAttempt(index + 1, 0);
          return;
        }

        if (retryCount < MAX_SAME_URL_RETRIES) {
          uploadAttempt(index, retryCount + 1);
          return;
        }

        const error = new Error(
          `Upload network error before server accepted the file. Failed URL: ${uploadUrls[index]}`
        );
        error.name = "ApiNetworkError";
        error.apiBaseUrl = uploadUrls[index];
        error.attempt = index + 1;
        error.status = xhr.status;
        error.responseText = xhr.responseText;
        error.attemptedUrls = uploadUrls.slice(0, index + 1);
        reject(error);
      };

      xhr.ontimeout = () => {
        responseSettled = true;
        clearResponseGraceTimer();
        console.error("Upload timeout", {
          url: uploadUrls[index],
          attempt: index + 1,
          timeoutMs,
          readyState: xhr.readyState,
          status: xhr.status,
          responseText: xhr.responseText,
          attemptedUrls: uploadUrls.slice(0, index + 1),
        });

        if (index < uploadUrls.length - 1) {
          uploadAttempt(index + 1, 0);
          return;
        }

        if (retryCount < MAX_SAME_URL_RETRIES) {
          uploadAttempt(index, retryCount + 1);
          return;
        }

        const error = new Error(
          `Upload request timed out before server accepted the file. Failed URL: ${uploadUrls[index]}`
        );
        error.name = "ApiTimeoutError";
        error.timeoutMs = timeoutMs;
        error.status = xhr.status;
        error.responseText = xhr.responseText;
        reject(error);
      };

      xhr.onabort = () => {
        clearResponseGraceTimer();
      };

      xhr.send(formData);
    };

    uploadAttempt(0, 0);
  });
}


export async function retryUploadAnalysisJob({ jobId, apiFetch, accessCode } = {}) {
  const cleanJobId = String(jobId ?? "").trim();
  if (!cleanJobId) {
    throw new Error("No uploaded telemetry job is available to retry.");
  }
  const response = await apiFetch(`/api/data/upload/${encodeURIComponent(cleanJobId)}/retry`, {
    method: "POST",
    accessCode,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload?.message ?? payload?.detail?.message ?? payload?.detail ?? payload?.error;
    const error = new Error(detail || `Unexpected response: ${response.status}`);
    error.name = "UploadRequestError";
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  return { ok: true, status: response.status, payload: normalizeUploadJob(payload) };
}
