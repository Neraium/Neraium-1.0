const ANALYSIS_HISTORY_STORAGE_KEY = "neraium.completed_analysis_history";
const MAX_ANALYSIS_HISTORY = 6;
const MAX_ANALYSIS_HISTORY_STORAGE_BYTES = 1_500_000;
const MAX_TEXT_LENGTH = 2_000;
const MAX_OBJECT_KEYS = 40;
const MAX_ARRAY_ITEMS = 20;

export function readAnalysisHistory() {
  if (typeof window === "undefined") return [];
  try {
    const parsed = JSON.parse(window.localStorage.getItem(ANALYSIS_HISTORY_STORAGE_KEY) || "[]");
    return compactAnalysisRecords(Array.isArray(parsed) ? parsed : []);
  } catch {
    return [];
  }
}

export function writeAnalysisHistory(records) {
  const safeRecords = compactAnalysisRecords(records);
  if (typeof window !== "undefined") {
    persistAnalysisHistory(safeRecords);
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

function persistAnalysisHistory(records) {
  const candidates = [
    records,
    records.slice(0, 3),
    records.slice(0, 1),
    records.slice(0, 1).map(compactRecordForStorageFallback),
  ];
  for (const candidate of candidates) {
    const payload = JSON.stringify(candidate);
    if (payload.length > MAX_ANALYSIS_HISTORY_STORAGE_BYTES) continue;
    try {
      window.localStorage.setItem(ANALYSIS_HISTORY_STORAGE_KEY, payload);
      return candidate;
    } catch (error) {
      console.warn("[neraium] completed analysis history persistence failed", {
        name: error?.name,
        message: error?.message,
      });
    }
  }
  return [];
}

function compactAnalysisRecords(records) {
  return (Array.isArray(records) ? records : [])
    .filter(isAnalysisRecord)
    .slice(0, MAX_ANALYSIS_HISTORY)
    .map(compactAnalysisRecord);
}

function compactAnalysisRecord(record) {
  const result = compactResult(record.result);
  const snapshot = compactSnapshot(record.snapshot, result);
  const analysis = extractAnalysis(result, snapshot);
  const timestamp = firstDisplayText(
    record.timestamp,
    record.savedAt,
    result?.completed_at,
    result?.processed_at,
    result?.last_processed_at,
    snapshot?.last_processed_at,
    snapshot?.last_upload_at,
    new Date().toISOString(),
  );
  const datasetName = firstDisplayText(
    record.datasetName,
    record.filename,
    result?.source_file,
    result?.filename,
    snapshot?.filename,
    snapshot?.last_filename,
    snapshot?.current_upload?.filename,
    "Operational dataset",
  );
  const jobId = firstDisplayText(
    record.jobId,
    record.job_id,
    result?.job_id,
    result?.upload_id,
    result?.run_id,
    snapshot?.current_upload?.job_id,
    snapshot?.job_id,
    analysis?.analysis_id,
    timestamp,
  );
  return {
    id: firstDisplayText(record.id, stableRecordId(jobId, datasetName, timestamp)),
    jobId,
    datasetName,
    timestamp,
    fingerprintStatus: formatStatus(firstDisplayText(
      record.fingerprintStatus,
      record.fingerprint_status,
      analysis?.fingerprint?.drift_status,
      analysis?.fingerprint?.status,
      "Active",
    )),
    systemsCount: firstCount(record.systemsCount, analysis?.systems?.length, 0),
    insightsCount: firstCount(record.insightsCount, analysis?.insights?.length, 0),
    savedAt: firstDisplayText(record.savedAt, timestamp),
    result,
    snapshot,
  };
}

function compactRecordForStorageFallback(record) {
  return {
    id: record.id,
    jobId: record.jobId,
    datasetName: record.datasetName,
    timestamp: record.timestamp,
    fingerprintStatus: record.fingerprintStatus,
    systemsCount: record.systemsCount,
    insightsCount: record.insightsCount,
    savedAt: record.savedAt,
    result: {
      job_id: record.jobId,
      filename: record.datasetName,
      status: "complete",
      processing_state: "complete",
      completed_at: record.timestamp,
      analysis_result: {
        source_file: record.datasetName,
        generated_at: record.timestamp,
        fingerprint: { status: record.fingerprintStatus },
        systems: [],
        insights: [],
      },
    },
    snapshot: {
      status: "complete",
      processing_state: "complete",
      current_upload: {
        job_id: record.jobId,
        filename: record.datasetName,
      },
      last_filename: record.datasetName,
      last_processed_at: record.timestamp,
      state_available: true,
    },
  };
}

function compactResult(result) {
  const analysis = extractAnalysis(result, null);
  return {
    job_id: firstText(result?.job_id, result?.upload_id, result?.run_id),
    upload_id: result?.upload_id,
    run_id: result?.run_id,
    filename: result?.filename,
    source_file: result?.source_file,
    status: result?.status ?? "complete",
    processing_state: result?.processing_state ?? "complete",
    completed_at: result?.completed_at,
    processed_at: result?.processed_at,
    last_processed_at: result?.last_processed_at,
    rows_processed: result?.rows_processed,
    row_count: result?.row_count,
    columns: trimArray(result?.columns, 80),
    timestamp_profile: compactValue(result?.timestamp_profile),
    room_summary: compactValue(result?.room_summary),
    data_quality: compactValue(result?.data_quality ?? analysis?.data_quality),
    processing_trace: compactValue(result?.processing_trace),
    operator_report: compactValue(result?.operator_report),
    sii_intelligence: compactValue(result?.sii_intelligence),
    engine_result: compactValue(result?.engine_result),
    identified_systems: trimArray(result?.identified_systems, 20).map(compactValue),
    analyzed_systems: trimArray(result?.analyzed_systems, 20).map(compactValue),
    systems_identified: trimArray(result?.systems_identified, 20).map(compactValue),
    systems: trimArray(result?.systems, 20).map(compactValue),
    analysis_result: compactAnalysis(analysis),
  };
}

function compactSnapshot(snapshot, result) {
  return {
    status: snapshot?.status ?? "complete",
    processing_state: snapshot?.processing_state ?? "complete",
    message: snapshot?.message,
    last_filename: snapshot?.last_filename ?? result?.filename,
    filename: snapshot?.filename ?? result?.filename,
    rows_processed: snapshot?.rows_processed ?? result?.rows_processed ?? result?.row_count,
    columns_detected: snapshot?.columns_detected,
    last_processed_at: snapshot?.last_processed_at ?? result?.last_processed_at ?? result?.completed_at,
    last_upload_at: snapshot?.last_upload_at,
    processed_at: snapshot?.processed_at,
    state_available: snapshot?.state_available ?? true,
    result_source: snapshot?.result_source,
    source: snapshot?.source,
    baseline_source: snapshot?.baseline_source,
    baseline_status: snapshot?.baseline_status,
    adaptive_learning: compactValue(snapshot?.adaptive_learning),
    history: trimArray(snapshot?.history, 5).map(compactValue),
    latest_result: null,
    current_upload: {
      job_id: firstText(snapshot?.current_upload?.job_id, result?.job_id),
      filename: snapshot?.current_upload?.filename ?? result?.filename,
      status: snapshot?.current_upload?.status ?? result?.status ?? "complete",
      processing_state: snapshot?.current_upload?.processing_state ?? result?.processing_state ?? "complete",
      result,
    },
  };
}

function compactAnalysis(analysis) {
  return {
    analysis_id: analysis?.analysis_id,
    generated_at: analysis?.generated_at,
    source_file: analysis?.source_file,
    fingerprint: compactValue(analysis?.fingerprint),
    systems: trimArray(analysis?.systems, 20).map(compactValue),
    insights: trimArray(analysis?.insights, 20).map(compactValue),
    data_quality: compactValue(analysis?.data_quality),
    analysis_metadata: compactValue(analysis?.analysis_metadata),
  };
}

function compactValue(value, depth = 0) {
  if (value === null || value === undefined) return value;
  if (typeof value === "string") return value.length > MAX_TEXT_LENGTH ? value.slice(0, MAX_TEXT_LENGTH) + "..." : value;
  if (typeof value !== "object") return value;
  if (depth >= 4) return Array.isArray(value) ? [] : {};
  if (Array.isArray(value)) return trimArray(value, MAX_ARRAY_ITEMS).map((item) => compactValue(item, depth + 1));
  return Object.fromEntries(
    Object.entries(value)
      .filter(([, nested]) => typeof nested !== "function")
      .slice(0, MAX_OBJECT_KEYS)
      .map(([key, nested]) => [key, compactValue(nested, depth + 1)]),
  );
}

function trimArray(value, maxItems) {
  return Array.isArray(value) ? value.slice(0, maxItems) : [];
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

function firstDisplayText(...values) {
  for (const value of values) {
    const text = displayText(value);
    if (text) return text;
  }
  return "";
}

function displayText(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value).trim();
  }
  if (Array.isArray(value)) {
    return value.map(displayText).filter(Boolean).join(", ");
  }
  if (typeof value === "object") {
    return firstDisplayText(
      value.filename,
      value.last_filename,
      value.source_file,
      value.source,
      value.name,
      value.label,
      value.title,
      value.status,
      value.processing_state,
      value.processed_at,
      value.last_processed_at,
      value.timestamp,
      value.value,
    );
  }
  return String(value ?? "").trim();
}

function firstCount(...values) {
  for (const value of values) {
    const count = countValue(value);
    if (count !== null) return count;
  }
  return 0;
}

function countValue(value) {
  const direct = Number(value);
  if (Number.isFinite(direct)) return Math.max(0, Math.round(direct));
  if (Array.isArray(value)) return value.length;
  if (value && typeof value === "object") {
    for (const candidate of [value.count, value.value, value.length, value.total]) {
      const nested = Number(candidate);
      if (Number.isFinite(nested)) return Math.max(0, Math.round(nested));
    }
  }
  return null;
}
