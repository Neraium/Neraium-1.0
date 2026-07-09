const ANALYSIS_HISTORY_STORAGE_KEY = "neraium.completed_analysis_history";
const MAX_ANALYSIS_HISTORY = 20;

export function readAnalysisHistory() {
  if (typeof window === "undefined") return [];
  try {
    const parsed = JSON.parse(window.localStorage.getItem(ANALYSIS_HISTORY_STORAGE_KEY) || "[]");
    return Array.isArray(parsed) ? parsed.filter(isAnalysisRecord).slice(0, MAX_ANALYSIS_HISTORY) : [];
  } catch {
    return [];
  }
}

export function writeAnalysisHistory(records) {
  const safeRecords = Array.isArray(records) ? records.filter(isAnalysisRecord).slice(0, MAX_ANALYSIS_HISTORY) : [];
  if (typeof window !== "undefined") {
    window.localStorage.setItem(ANALYSIS_HISTORY_STORAGE_KEY, JSON.stringify(safeRecords));
  }
  return safeRecords;
}

export function deleteAnalysisRecord(records, recordId) {
  return writeAnalysisHistory((records ?? []).filter((record) => record.id !== recordId));
}

export function createAnalysisRecord({ result = null, snapshot = null } = {}) {
  if (!isCompletedAnalysisPayload({ result, snapshot })) return null;
  const analysis = extractAnalysis(result, snapshot);
  const metadata = analysis?.analysis_metadata ?? {};
  const timestamp = firstText(
    analysis?.generated_at,
    result?.completed_at,
    result?.processed_at,
    result?.last_processed_at,
    snapshot?.processed_at,
    snapshot?.last_processed_at,
    snapshot?.last_upload_at,
    new Date().toISOString(),
  );
  const datasetName = firstText(
    analysis?.source_file,
    metadata.source_file,
    result?.source_file,
    result?.filename,
    snapshot?.filename,
    snapshot?.last_filename,
    snapshot?.current_upload?.filename,
    "Operational dataset",
  );
  const jobId = firstText(
    result?.job_id,
    result?.upload_id,
    result?.run_id,
    snapshot?.current_upload?.job_id,
    snapshot?.job_id,
    analysis?.analysis_id,
    timestamp,
  );
  const fingerprint = analysis?.fingerprint ?? {};
  const systems = Array.isArray(analysis?.systems) ? analysis.systems : [];
  const insights = Array.isArray(analysis?.insights) ? analysis.insights : [];
  return {
    id: stableRecordId(jobId, datasetName, timestamp),
    jobId,
    datasetName,
    timestamp,
    fingerprintStatus: formatStatus(firstText(fingerprint.drift_status, fingerprint.status, result?.drift_status, "Active")),
    systemsCount: systems.length,
    insightsCount: insights.length,
    savedAt: new Date().toISOString(),
    result,
    snapshot,
  };
}

export function upsertCompletedAnalysis(records, nextRecord) {
  if (!isAnalysisRecord(nextRecord)) return Array.isArray(records) ? records : [];
  const existing = Array.isArray(records) ? records : [];
  const withoutDuplicate = existing.filter((record) => record.id !== nextRecord.id && record.jobId !== nextRecord.jobId);
  return writeAnalysisHistory([nextRecord, ...withoutDuplicate].sort(sortNewestFirst));
}

export function isCompletedAnalysisPayload({ result = null, snapshot = null } = {}) {
  if (!result) return false;
  const analysis = extractAnalysis(result, snapshot);
  const hasIntelligence = Boolean(
    analysis?.fingerprint
      || analysis?.systems
      || analysis?.insights
      || result?.analysis_result
      || result?.sii_intelligence
      || result?.engine_result
      || result?.operator_report
      || result?.data_quality
  );
  const statusText = [
    result?.status,
    result?.processing_state,
    snapshot?.status,
    snapshot?.processing_state,
  ].map((value) => String(value ?? "").toLowerCase()).join(" ");
  const explicitlyRunning = /\b(processing|running|queued|pending|analyzing|incomplete|interrupted|paused)\b/.test(statusText);
  const completed = Boolean(
    result?.sii_reliable_enough_to_show === true
      || result?.sii_completed === true
      || result?.processing_trace?.sii_completed === true
      || snapshot?.sii_completed === true
      || /\b(complete|completed|ready|active|processed|success)\b/.test(statusText)
  );
  return hasIntelligence && completed && !explicitlyRunning;
}

function extractAnalysis(result, snapshot) {
  const currentUpload = snapshot?.current_upload ?? {};
  const interpretation = result?.system_interpretation ?? snapshot?.system_interpretation ?? {};
  const analysis = result?.analysis_result
    ?? result?.analysis_explanation
    ?? currentUpload?.result?.analysis_result
    ?? snapshot?.analysis_result
    ?? interpretation?.analysis_result
    ?? interpretation?.analysis_explanation
    ?? snapshot?.analysis_explanation;
  return analysis && typeof analysis === "object" ? analysis : {};
}

function stableRecordId(jobId, datasetName, timestamp) {
  return [jobId, datasetName, timestamp]
    .map((value) => String(value ?? "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "-"))
    .filter(Boolean)
    .join(":")
    .slice(0, 180) || `analysis-${Date.now()}`;
}

function sortNewestFirst(left, right) {
  return new Date(right.timestamp ?? right.savedAt ?? 0).getTime() - new Date(left.timestamp ?? left.savedAt ?? 0).getTime();
}

function isAnalysisRecord(record) {
  return Boolean(record && typeof record === "object" && record.id && record.result && record.snapshot);
}

function formatStatus(value) {
  return String(value ?? "")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase()) || "Active";
}

function firstText(...values) {
  for (const value of values) {
    if (value === null || value === undefined) continue;
    const text = String(value).trim();
    if (text) return text;
  }
  return "";
}
