export const BASELINE_ANALYSIS_STATES = Object.freeze({
  NO_DATASET: "no_dataset",
  DATASET_SELECTED: "dataset_selected",
  UPLOADING: "uploading",
  UPLOAD_COMPLETE: "upload_complete",
  READY_TO_ANALYZE: "ready_to_analyze",
  ANALYSIS_QUEUED: "analysis_queued",
  VALIDATING: "validating",
  MAPPING: "mapping",
  BASELINE_CREATION: "baseline_creation",
  COMPARISON: "comparison",
  EVIDENCE_GENERATION: "evidence_generation",
  COMPLETED: "completed",
  FAILED: "failed",
  CANCELLED: "cancelled",
});

export const CANONICAL_BACKEND_ANALYSIS_STATES = Object.freeze([
  BASELINE_ANALYSIS_STATES.NO_DATASET,
  BASELINE_ANALYSIS_STATES.DATASET_SELECTED,
  BASELINE_ANALYSIS_STATES.UPLOAD_COMPLETE,
  BASELINE_ANALYSIS_STATES.READY_TO_ANALYZE,
  BASELINE_ANALYSIS_STATES.ANALYSIS_QUEUED,
  BASELINE_ANALYSIS_STATES.VALIDATING,
  BASELINE_ANALYSIS_STATES.MAPPING,
  BASELINE_ANALYSIS_STATES.BASELINE_CREATION,
  BASELINE_ANALYSIS_STATES.COMPARISON,
  BASELINE_ANALYSIS_STATES.EVIDENCE_GENERATION,
  BASELINE_ANALYSIS_STATES.COMPLETED,
  BASELINE_ANALYSIS_STATES.FAILED,
  BASELINE_ANALYSIS_STATES.CANCELLED,
]);

const BACKEND_STATE_SET = new Set(CANONICAL_BACKEND_ANALYSIS_STATES);

export const BASELINE_ANALYSIS_TRANSITIONS = Object.freeze({
  [BASELINE_ANALYSIS_STATES.NO_DATASET]: [BASELINE_ANALYSIS_STATES.DATASET_SELECTED],
  [BASELINE_ANALYSIS_STATES.DATASET_SELECTED]: [BASELINE_ANALYSIS_STATES.NO_DATASET, BASELINE_ANALYSIS_STATES.READY_TO_ANALYZE],
  [BASELINE_ANALYSIS_STATES.READY_TO_ANALYZE]: [BASELINE_ANALYSIS_STATES.NO_DATASET, BASELINE_ANALYSIS_STATES.DATASET_SELECTED, BASELINE_ANALYSIS_STATES.UPLOADING],
  [BASELINE_ANALYSIS_STATES.UPLOADING]: [BASELINE_ANALYSIS_STATES.UPLOAD_COMPLETE, BASELINE_ANALYSIS_STATES.ANALYSIS_QUEUED, BASELINE_ANALYSIS_STATES.FAILED, BASELINE_ANALYSIS_STATES.CANCELLED],
  [BASELINE_ANALYSIS_STATES.UPLOAD_COMPLETE]: [BASELINE_ANALYSIS_STATES.READY_TO_ANALYZE, BASELINE_ANALYSIS_STATES.ANALYSIS_QUEUED, BASELINE_ANALYSIS_STATES.FAILED, BASELINE_ANALYSIS_STATES.CANCELLED],
  [BASELINE_ANALYSIS_STATES.ANALYSIS_QUEUED]: [BASELINE_ANALYSIS_STATES.VALIDATING, BASELINE_ANALYSIS_STATES.FAILED, BASELINE_ANALYSIS_STATES.CANCELLED],
  [BASELINE_ANALYSIS_STATES.VALIDATING]: [BASELINE_ANALYSIS_STATES.MAPPING, BASELINE_ANALYSIS_STATES.BASELINE_CREATION, BASELINE_ANALYSIS_STATES.FAILED, BASELINE_ANALYSIS_STATES.CANCELLED],
  [BASELINE_ANALYSIS_STATES.MAPPING]: [BASELINE_ANALYSIS_STATES.BASELINE_CREATION, BASELINE_ANALYSIS_STATES.FAILED, BASELINE_ANALYSIS_STATES.CANCELLED],
  [BASELINE_ANALYSIS_STATES.BASELINE_CREATION]: [BASELINE_ANALYSIS_STATES.COMPARISON, BASELINE_ANALYSIS_STATES.FAILED, BASELINE_ANALYSIS_STATES.CANCELLED],
  [BASELINE_ANALYSIS_STATES.COMPARISON]: [BASELINE_ANALYSIS_STATES.EVIDENCE_GENERATION, BASELINE_ANALYSIS_STATES.FAILED, BASELINE_ANALYSIS_STATES.CANCELLED],
  [BASELINE_ANALYSIS_STATES.EVIDENCE_GENERATION]: [BASELINE_ANALYSIS_STATES.COMPLETED, BASELINE_ANALYSIS_STATES.FAILED, BASELINE_ANALYSIS_STATES.CANCELLED],
  [BASELINE_ANALYSIS_STATES.COMPLETED]: [BASELINE_ANALYSIS_STATES.NO_DATASET, BASELINE_ANALYSIS_STATES.DATASET_SELECTED],
  [BASELINE_ANALYSIS_STATES.FAILED]: [BASELINE_ANALYSIS_STATES.NO_DATASET, BASELINE_ANALYSIS_STATES.DATASET_SELECTED, BASELINE_ANALYSIS_STATES.READY_TO_ANALYZE, BASELINE_ANALYSIS_STATES.ANALYSIS_QUEUED],
  [BASELINE_ANALYSIS_STATES.CANCELLED]: [BASELINE_ANALYSIS_STATES.NO_DATASET, BASELINE_ANALYSIS_STATES.DATASET_SELECTED, BASELINE_ANALYSIS_STATES.READY_TO_ANALYZE],
});

function cleanIdentity(value) {
  return String(value ?? "").trim();
}

export function backendAnalysisState(payload) {
  const state = String(payload?.analysis_state ?? payload?.analysisState ?? "").trim().toLowerCase();
  return BACKEND_STATE_SET.has(state) ? state : null;
}

export function datasetIdFromPayload(payload) {
  if (!payload || typeof payload !== "object") return null;
  const currentUpload = payload.current_upload ?? payload.snapshot?.current_upload ?? null;
  const value = cleanIdentity(
    payload.dataset_id
      ?? payload.job_id
      ?? currentUpload?.dataset_id
      ?? currentUpload?.job_id
      ?? payload.upload_id
      ?? payload.run_id
  );
  return value || null;
}

export function payloadMatchesDataset(payload, datasetId) {
  const expected = cleanIdentity(datasetId);
  const actual = datasetIdFromPayload(payload);
  return Boolean(expected && actual && expected === actual);
}

function canonicalCompletedAnalysis(value) {
  if (!value || typeof value !== "object") return null;
  const status = String(value.status ?? "").trim().toLowerCase();
  if (!["complete", "completed", "ready"].includes(status)) return null;
  if (!Array.isArray(value.systems) || !Array.isArray(value.insights)) return null;
  return value;
}

function analysisFromMatchingEnvelope(envelope, datasetId) {
  if (!payloadMatchesDataset(envelope, datasetId)) return null;
  if (backendAnalysisState(envelope) !== BASELINE_ANALYSIS_STATES.COMPLETED) return null;
  const nestedResult = envelope?.current_upload?.result ?? envelope?.latest_result ?? envelope?.latestResult ?? envelope?.result ?? null;
  if (nestedResult && datasetIdFromPayload(nestedResult) && !payloadMatchesDataset(nestedResult, datasetId)) return null;
  return canonicalCompletedAnalysis(
    envelope?.analysis_result
      ?? nestedResult?.analysis_result
      ?? (Array.isArray(envelope?.systems) && Array.isArray(envelope?.insights) ? envelope : null)
  );
}

export function completedAnalysisForDataset(datasetId, ...candidates) {
  for (const candidate of candidates) {
    const analysis = analysisFromMatchingEnvelope(candidate, datasetId);
    if (analysis) return analysis;
  }
  return null;
}

export function resolveBaselineAnalysisState({ selectedFiles, uploadState, uploadJob, activeDatasetId }) {
  const hasDataset = Array.isArray(selectedFiles) && selectedFiles.length > 0;
  if (!hasDataset) return BASELINE_ANALYSIS_STATES.NO_DATASET;

  const clientState = String(uploadState ?? "").trim().toLowerCase();
  if (["failed", "error", "validation_error", "timeout"].includes(clientState)) return BASELINE_ANALYSIS_STATES.FAILED;
  if (clientState === "cancelled") return BASELINE_ANALYSIS_STATES.CANCELLED;
  const datasetId = cleanIdentity(activeDatasetId);
  if (!datasetId) {
    if (clientState === "uploading") return BASELINE_ANALYSIS_STATES.UPLOADING;
    if (clientState === "validated") return BASELINE_ANALYSIS_STATES.READY_TO_ANALYZE;
    return BASELINE_ANALYSIS_STATES.DATASET_SELECTED;
  }

  if (!payloadMatchesDataset(uploadJob, datasetId)) return BASELINE_ANALYSIS_STATES.UPLOADING;
  return backendAnalysisState(uploadJob) ?? BASELINE_ANALYSIS_STATES.UPLOADING;
}

export function canRenderCompletedAnalysis({ analysisState, activeDatasetId, selectedFiles, analysisResult }) {
  return analysisState === BASELINE_ANALYSIS_STATES.COMPLETED
    && Boolean(cleanIdentity(activeDatasetId))
    && Array.isArray(selectedFiles)
    && selectedFiles.length > 0
    && Boolean(canonicalCompletedAnalysis(analysisResult));
}
