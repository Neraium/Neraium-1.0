import { buildAccessHeaders, buildApiCandidateUrls } from "../../config";
import * as uploadStateView from "../../viewModels/uploadState";\nimport { normalizeUploadJob } from "../../viewModels/uploadContract";

export async function fetchLatestUploadState({ apiFetch, accessCode, includePersisted = false }) {
  const response = await apiFetch(`/api/data/latest-upload?include_persisted=${includePersisted ? 1 : 0}`, { accessCode });
  if (!response.ok) {
    throw new Error(`Unexpected response: ${response.status}`);
  }

  const payload = await response.json();
  const latestResult = payload?.latest_result;
  const normalizedLatestResult = uploadStateView.hasFullUploadResult(latestResult) ? latestResult : null;
  const normalizedSnapshot = payload ?? uploadStateView.buildEmptyLatestUploadSnapshot();
  const status = String(normalizedSnapshot?.status ?? normalizedSnapshot?.processing_state ?? "").toLowerCase();
  const shouldDowngradeActive =
    ["active", "baseline_active"].includes(status)
    && !normalizedLatestResult
    && normalizedSnapshot?.sii_completed !== true;

  return {
    snapshot: shouldDowngradeActive
      ? {
        ...uploadStateView.buildEmptyLatestUploadSnapshot(),
        status: "empty",
        source: "none",
        message: "No data connected yet.",
      }
      : normalizedSnapshot,
    latestResult: normalizedLatestResult,
  };
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

export function uploadTelemetryFileWithProgress({ file, timeoutMs = 10 * 60 * 1000, onProgress } = {}) {
  return new Promise((resolve, reject) => {
    if (!file) {
      reject(new Error("Choose a CSV or JSON telemetry file to upload."));
      return;
    }

    const startedAt = Date.now();
    const uploadUrls = buildApiCandidateUrls("/api/data/upload");

    onProgress?.({
      stage: "upload_started",
      loaded: 0,
      total: file.size,
      percent: 0,
      speedBytesPerSecond: 0,
      message: "Upload started.",
    });

    const shouldRetryStatus = (status) => status >= 500 || status === 404 || status === 405 || status === 408 || status === 425 || status === 429;

    const uploadAttempt = (index) => {
      const xhr = new XMLHttpRequest();
      const formData = new FormData();
      formData.append("file", file);
      xhr.open("POST", uploadUrls[index], true);
      xhr.withCredentials = true;
      xhr.timeout = timeoutMs;

      Object.entries(buildAccessHeaders()).forEach(([key, value]) => {
        xhr.setRequestHeader(key, value);
      });

      xhr.upload.onprogress = (event) => {
        const loaded = event.loaded ?? 0;
        const total = event.lengthComputable ? event.total : file.size;
        const elapsedSeconds = Math.max((Date.now() - startedAt) / 1000, 0.001);
        onProgress?.({
          stage: "uploading",
          loaded,
          total,
          percent: total > 0 ? Math.min(100, Math.round((loaded / total) * 100)) : null,
          speedBytesPerSecond: loaded / elapsedSeconds,
          message: "Uploading telemetry export.",
        });
      };

      xhr.onload = () => {
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
        const error = new Error(payload?.message ?? payload?.detail?.message ?? payload?.detail ?? `Unexpected response: ${xhr.status}`);
        error.name = "UploadRequestError";
        error.status = xhr.status;
        error.payload = payload;
        reject(error);
      };

      xhr.onerror = () => {
        console.error("Upload network error", {
          url: uploadUrls[index],
          attempt: index + 1,
          readyState: xhr.readyState,
          status: xhr.status,
          responseText: xhr.responseText,
          attemptedUrls: uploadUrls.slice(0, index + 1),
        });

        if (index < uploadUrls.length - 1) {
          uploadAttempt(index + 1);
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
          uploadAttempt(index + 1);
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

      xhr.send(formData);
    };

    uploadAttempt(0);
  });
}
