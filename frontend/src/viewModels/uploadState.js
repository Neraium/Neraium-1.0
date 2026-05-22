import { NO_DATA_LABEL, noDataGuidance } from "./uiStateText";

export function hasFullUploadResult(result) {
  return Boolean(
    result
    && (
      result.engine_result
      || result.sii_intelligence
      || result.operator_report
      || result.room_summary
      || result.data_quality
      || result.processing_trace
      || result.row_count
      || result.rows_processed
    )
  );
}

export function hasActiveTelemetrySnapshot(snapshot) {
  const status = String(snapshot?.status ?? snapshot?.processing_state ?? "").toLowerCase();
  const explicitlyInactive = ["empty", "idle", "cleared", "reset", "none", "no_data"].includes(status);
  if (explicitlyInactive || snapshot?.latest_result === null || snapshot?.latest_upload === null) {
    return false;
  }
  if (["active", "baseline_active"].includes(status) && !snapshot?.latest_result && snapshot?.sii_completed !== true) {
    return false;
  }
  return Boolean(
    status === "active"
    || status === "baseline_active"
    || snapshot?.latest_result
    || snapshot?.state_available
    || (snapshot?.rows_processed ?? 0) > 0
    || (snapshot?.columns_detected ?? 0) > 0
    || snapshot?.last_filename
  );
}

export function buildEmptyLatestUploadSnapshot() {
  return {
    status: "empty",
    source: "none",
    message: `${NO_DATA_LABEL}.`,
    last_filename: null,
    rows_processed: 0,
    columns_detected: 0,
    last_processed_at: null,
    runner_module: null,
    core_engine: null,
    state_available: false,
    connection_status: "no_data",
    result_source: null,
    history: [],
    latest_result: null,
    baseline_source: null,
    baseline_status: "none",
    baseline_samples_collected: 0,
    baseline_samples_required: 0,
    last_baseline_update: null,
    adaptive_learning: {},
  };
}

export function buildEmptyIntelligenceStatus() {
  return {
    engine_loaded: true,
    source: "none",
    last_processed_at: null,
    active_rooms_count: 0,
    evidence_fields_present: [],
    mode: "empty",
    status: "no_data",
  };
}

export function deriveRoomContext(result) {
  if (!result || !Array.isArray(result.columns)) {
    const summaryRooms = extractRoomSummaryNames(result);
    if (summaryRooms.length > 0) {
      return {
        primary: summaryRooms[0],
        secondary: summaryRooms[1] ?? `${summaryRooms.length} uploaded rooms`,
        cycle: "Mixed uploaded rooms",
        irrigation: "Irrigation context pending",
        uploadedRooms: summaryRooms,
        roomCount: summaryRooms.length,
      };
    }
      return {
        primary: NO_DATA_LABEL,
        secondary: noDataGuidance(),
        cycle: "Cycle metadata unavailable",
        irrigation: "Irrigation context unavailable",
        uploadedRooms: [],
      roomCount: 0,
    };
  }

  const summaryRooms = extractRoomSummaryNames(result);
  const roomColumn = matchColumnAlias(result.columns, ["room", "zone", "location", "area"]);
  const cycleColumn = matchColumnAlias(result.columns, ["cycle", "stage", "phase", "growthstage", "mode"]);

  const roomValues = roomColumn
    ? result.preview_rows.map((row) => normalizePreviewValue(row?.[roomColumn])).filter(Boolean)
    : [];
  const cycleValues = cycleColumn
    ? result.preview_rows.map((row) => normalizePreviewValue(row?.[cycleColumn])).filter(Boolean)
    : [];
  const irrigationMapped = result.cultivation_mapping?.categories?.irrigation?.length ?? 0;
  const uploadedRooms = summaryRooms.length > 0 ? summaryRooms : uniqueValues(roomValues);

  return {
    primary: uploadedRooms[0] ?? "Room context not present in upload",
    secondary: uploadedRooms[1] ?? (uploadedRooms.length > 1 ? `${uploadedRooms.length} uploaded rooms` : "Awaiting additional room telemetry"),
    cycle: cycleValues[0] ?? "Cycle metadata unavailable",
    irrigation: irrigationMapped > 0 ? "Irrigation channels mapped" : "Awaiting irrigation telemetry",
    uploadedRooms,
    roomCount: uploadedRooms.length,
  };
}

export function deriveTimeCoverage(result) {
  if (!result?.timestamp_profile) {
    const timestampColumn = Array.isArray(result?.columns)
      ? matchColumnAlias(result.columns, ["timestamp", "time", "datetime", "date", "ts"])
      : null;
    if (timestampColumn && Array.isArray(result?.preview_rows)) {
      const samples = result.preview_rows
        .map((row) => safeTimestamp(row?.[timestampColumn]))
        .filter(Boolean);
      if (samples.length > 0) {
        return {
          hasCoverage: true,
          summary: `${samples[0]} to ${samples[samples.length - 1]}`,
        };
      }
    }
    return {
      hasCoverage: false,
      summary: "Awaiting room timestamps",
    };
  }

  const first = result.timestamp_profile.first_timestamp;
  const last = result.timestamp_profile.last_timestamp;

  return {
    hasCoverage: Boolean(first || last),
    summary:
      first && last
        ? `${first} to ${last}`
        : result.timestamp_profile.estimated_sample_interval ?? "Timestamp range unavailable",
  };
}

export function buildConnectionStateStages({ latestUploadSnapshot, uploadState, uploadError, roomContext }) {
  const normalizedState = normalizeUploadStatus(uploadError ? "failed" : uploadState);
  const latestStatus = String(latestUploadSnapshot?.status ?? "empty").toLowerCase();
  const baselineStatus = String(latestUploadSnapshot?.baseline_status ?? "none").toLowerCase();
  const baselineSamplesCollected = latestUploadSnapshot?.baseline_samples_collected ?? 0;
  const baselineSamplesRequired = latestUploadSnapshot?.baseline_samples_required ?? 0;
  const baselineDetail = baselineSamplesRequired > 0
    ? `${baselineSamplesCollected}/${baselineSamplesRequired} live samples collected.`
    : "Waiting for live telemetry samples.";
  return [
    {
      title: NO_DATA_LABEL,
      detail: latestStatus === "empty" && baselineStatus === "none"
        ? "No telemetry source is active yet."
        : "A data source is connected or a result is already active.",
      state: latestStatus === "empty" && baselineStatus === "none" ? "active" : "complete",
      tone: latestStatus === "empty" && baselineStatus === "none" ? "info" : "nominal",
    },
    {
      title: "Building live baseline",
      detail: baselineStatus === "building"
        ? baselineDetail
        : baselineStatus === "active"
          ? "Live baseline is ready for comparison."
          : "Live polling will build a baseline automatically.",
      state: baselineStatus === "building" ? "active" : (baselineStatus === "active" ? "complete" : "standby"),
      tone: baselineStatus === "building" ? "review" : (baselineStatus === "active" ? "nominal" : "info"),
    },
    {
      title: "Live telemetry processing",
      detail: latestStatus === "active" && latestUploadSnapshot?.result_source === "rest_poll"
        ? `Live telemetry is updating ${roomContext.primary}.`
        : isUploadProcessing(normalizedState)
          ? "Telemetry file received and processing is underway."
          : "Live telemetry or upload processing will appear here.",
      state: latestStatus === "active" || isUploadProcessing(normalizedState) ? "active" : "standby",
      tone: latestStatus === "active" || isUploadProcessing(normalizedState) ? "nominal" : "info",
    },
    {
      title: "Upload complete",
      detail: latestStatus === "active" && latestUploadSnapshot?.result_source !== "rest_poll"
        ? `${latestUploadSnapshot?.last_filename ?? "Latest upload"} completed and refreshed ${roomContext.primary}.`
        : "Upload telemetry remains available as an optional ingest action.",
      state: latestStatus === "active" && latestUploadSnapshot?.result_source !== "rest_poll" ? "complete" : "standby",
      tone: latestStatus === "active" && latestUploadSnapshot?.result_source !== "rest_poll" ? "nominal" : "info",
    },
    {
      title: uploadError ? "Upload failed" : (latestStatus === "active" || latestStatus === "baseline_active" ? "Active Session" : "No Active Session"),
      detail: uploadError
        ? normalizeErrorMessage(uploadError)
        : latestStatus === "active"
          ? `Dashboard is using ${latestUploadSnapshot?.last_filename ?? "the latest telemetry result"} as the active result.`
          : latestStatus === "baseline_active"
            ? "Live baseline is active. The next telemetry comparison will activate Facility Command."
            : "No Active Session. Awaiting uploaded telemetry.",
      state: uploadError ? "active" : (latestStatus === "active" || latestStatus === "baseline_active" ? "active" : "standby"),
      tone: uploadError ? "elevated" : (latestStatus === "active" || latestStatus === "baseline_active" ? "nominal" : "info"),
    },
  ];
}

export function connectionStateLabel(latestStatus, uploadState, uploadError) {
  const normalizedLatestStatus = String(latestStatus).toLowerCase();
  if (uploadError || normalizeUploadStatus(uploadState) === "failed") {
    return "Upload failed";
  }
  if (isUploadProcessing(uploadState)) {
    return "Upload processing";
  }
  if (normalizedLatestStatus === "building_baseline") {
    return "Building live baseline";
  }
  if (normalizedLatestStatus === "baseline_active") {
    return "Live baseline active";
  }
  if (normalizedLatestStatus === "active") {
    return "Active Session";
  }
  return NO_DATA_LABEL;
}

export function buildUploadHistoryRows(history = []) {
  return history.map((entry, index) => ({
    id: `${entry.job_id ?? entry.filename ?? "upload"}-${index}`,
    filename: entry.filename ?? "Unknown file",
    processedAt: entry.last_processed_at ?? "Pending",
    score: entry.neraium_score ?? "n/a",
    state: entry.operating_state ?? "Pending",
    room: entry.primary_room ?? "Unknown room",
    drift: entry.drift_status ?? "n/a",
    status: index === 0 ? "Active" : "Superseded",
    scoreDelta: entry.diff?.neraium_score_delta ?? null,
    previousFilename: entry.diff?.previous_filename ?? null,
  }));
}

export function buildUploadDiffSummary(history = []) {
  const current = history[0] ?? null;
  const previous = history[1] ?? null;
  if (!current) {
    return {
      title: "No Active Session",
      lines: [noDataGuidance()],
    };
  }
  const delta = current.diff?.neraium_score_delta;
  const deltaLabel = typeof delta === "number"
    ? `${delta > 0 ? "+" : ""}${delta}`
    : "No prior score";
  return {
    title: previous ? `${current.filename} vs ${previous.filename}` : `${current.filename} is active`,
    lines: [
      `Score delta: ${deltaLabel}`,
      `State: ${current.operating_state ?? "Unknown"}`,
      `Primary room: ${current.primary_room ?? "Unknown"}`,
    ],
  };
}

function extractRoomSummaryNames(result) {
  const rooms = result?.room_summary?.rooms;
  if (!Array.isArray(rooms)) {
    return [];
  }
  return uniqueValues(rooms.map((room) => room?.room).filter(Boolean));
}

function uniqueValues(values) {
  return [...new Set(values
    .map((value) => normalizePreviewValue(value))
    .filter(Boolean)
    .map((value) => String(value))
    .slice(0, 24))];
}

export function hasVerifiedSiiCompletion({ latestResult, latestSnapshot } = {}) {
  const result = latestResult ?? null;
  const snapshot = latestSnapshot ?? null;
  if (snapshot?.sii_completed === true) return true;
  // Fallback acceptance for large uploads where snapshot flags may lag but
  // result payload already contains a full SII intelligence artifact.
  const hasResultStructuralPayload = Boolean(
    result
    && result.sii_intelligence
    && (
      result.sii_intelligence.core_sii_outputs
      || result.sii_intelligence.instability_index
      || result.sii_intelligence.replay_timeline
    )
  );
  if (hasResultStructuralPayload) return true;
  const hasResultEvidence = Boolean(
    result
    && result.sii_intelligence
    && (
      result.engine_result
      || result.operator_report
      || result.data_quality
      || result.room_summary
    )
  );
  const status = String(snapshot?.status ?? snapshot?.processing_state ?? "").toLowerCase();
  const hasSnapshotEvidence = Boolean(
    ["active", "baseline_active"].includes(status)
    && snapshot?.state_available === true
    && (snapshot?.last_processed_at || snapshot?.last_upload_at)
  );
  return hasResultEvidence && hasSnapshotEvidence;
}

function normalizePreviewValue(value) {
  if (value === null || value === undefined) return "";
  const text = String(value).trim();
  if (!text || text.toLowerCase() === "nan" || text.toLowerCase() === "null" || text.toLowerCase() === "undefined") return "";
  return text;
}

function normalizeColumnName(value) {
  return String(value ?? "").toLowerCase().replace(/[^a-z0-9]/g, "");
}

function matchColumnAlias(columns, aliases) {
  if (!Array.isArray(columns)) return null;
  const normalizedAliases = aliases.map((alias) => normalizeColumnName(alias));
  return columns.find((column) => {
    const normalizedColumn = normalizeColumnName(column);
    return normalizedAliases.some((alias) => normalizedColumn.includes(alias));
  }) ?? null;
}

function safeTimestamp(value) {
  if (value === null || value === undefined) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toISOString();
}

function normalizeUploadStatus(status) {
  const value = String(status ?? "").toLowerCase();
  const aliases = {
    queued: "pending",
    pending: "pending",
    parsing: "parsing",
    baseline_modeling: "baseline_modeling",
    running_sii: "running_sii",
    generating_evidence: "writing_state",
    writing_state: "writing_state",
    complete: "complete",
    completed: "complete",
    failed: "failed",
    error: "failed",
    uploading: "uploading",
  };
  return aliases[value] ?? value;
}

function isUploadProcessing(status) {
  const normalized = normalizeUploadStatus(status);
  return ["uploading", "pending", "parsing", "baseline_modeling", "running_sii", "writing_state"].includes(normalized);
}

function normalizeErrorMessage(message) {
  if (message == null) return "Upload failed.";
  return String(message);
}
