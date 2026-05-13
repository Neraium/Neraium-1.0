import * as uploadStateView from "../../viewModels/uploadState";

export async function fetchLatestUploadState({ apiFetch, accessCode }) {
  const response = await apiFetch("/api/data/latest-upload", { accessCode });
  if (!response.ok) {
    throw new Error(`Unexpected response: ${response.status}`);
  }

  const payload = await response.json();
  const latestResult = payload?.latest_result;
  return {
    snapshot: payload ?? uploadStateView.buildEmptyLatestUploadSnapshot(),
    latestResult: uploadStateView.hasFullUploadResult(latestResult) ? latestResult : null,
  };
}
