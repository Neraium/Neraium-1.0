import { buildAccessHeaders, buildApiUrl } from "../../config";
import * as uploadStateView from "../../viewModels/uploadState";

export async function fetchLatestUploadState({ apiFetch, accessCode }) {
  const response = await apiFetch("/api/data/latest-upload", { accessCode });
  if (!response.ok) {
    throw new Error(`Unexpected response: ${response.status}`);
  }

  const payload = await response.json();
  const latestResult = payload?.latest_result;
  const snapshotIsActive = uploadStateView.hasActiveTelemetrySnapshot(payload);
  const hydratedSnapshotResult = snapshotIsActive
    ? {
        filename: payload?.last_filename ?? "Active telemetry import",
        row_count: payload?.rows_processed ?? 0,
        column_count: payload?.columns_detected ?? 0,
        rows_processed: payload?.rows_processed ?? 0,
        columns_detected: payload?.columns_detected ?? 0,
        room_summary: {
          rooms: [
            {
              room: "Cultivation Rooms",
            },
          ],
        },
        processing_trace: {
          completed_at: payload?.last_processed_at ?? null,
          source: payload?.source ?? payload?.result_source ?? "uploaded",
        },
        sii_intelligence: {
          source: payload?.source ?? payload?.result_source ?? "uploaded",
          last_updated: payload?.last_processed_at ?? null,
        },
      }
    : null;

  const normalizedLatestResult = uploadStateView.hasFullUploadResult(latestResult)
    ? latestResult
    : hydratedSnapshotResult;

  return {
    snapshot: payload ?? uploadStateView.buildEmptyLatestUploadSnapshot(),
    latestResult: normalizedLatestResult,
  };
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

    const xhr = new XMLHttpRequest();
    const formData = new FormData();
    const startedAt = Date.now();
    formData.append("file", file);

    xhr.open("POST", buildApiUrl("/api/data/upload"), true);
    xhr.withCredentials = true;
    xhr.timeout = timeoutMs;

    Object.entries(buildAccessHeaders()).forEach(([key, value]) => {
      xhr.setRequestHeader(key, value);
    });

    onProgress?.({
      stage: "upload_started",
      loaded: 0,
      total: file.size,
      percent: 0,
      speedBytesPerSecond: 0,
      message: "Upload started.",
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
      const payload = readJsonResponse(xhr);
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
      const error = new Error(payload?.message ?? payload?.detail?.message ?? payload?.detail ?? `Unexpected response: ${xhr.status}`);
      error.name = "UploadRequestError";
      error.status = xhr.status;
      error.payload = payload;
      reject(error);
    };

    xhr.onerror = () => {
      const error = new Error("Secure telemetry ingestion unavailable.");
      error.name = "ApiNetworkError";
      reject(error);
    };

    xhr.ontimeout = () => {
      const error = new Error(`Upload request timed out after ${timeoutMs}ms.`);
      error.name = "ApiTimeoutError";
      error.timeoutMs = timeoutMs;
      reject(error);
    };

    xhr.send(formData);
  });
}
