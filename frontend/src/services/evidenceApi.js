export async function fetchLatestEvidence({ apiFetch, readJsonPayload, accessCode }) {
  const response = await apiFetch("/api/evidence/latest", { accessCode });
  return readJsonPayload(response);
}

export async function fetchEvidenceRuns({ apiFetch, readJsonPayload, accessCode }) {
  const response = await apiFetch("/api/evidence/runs", { accessCode });
  return readJsonPayload(response);
}

export async function fetchEvidenceRun({ apiFetch, readJsonPayload, accessCode, runId }) {
  const response = await apiFetch(`/api/evidence/runs/${runId}`, { accessCode });
  return readJsonPayload(response);
}

export async function exportEvidenceRun({ apiFetch, accessCode, runId }) {
  const response = await apiFetch(`/api/evidence/export/${runId}`, { accessCode });
  return response.text();
}
