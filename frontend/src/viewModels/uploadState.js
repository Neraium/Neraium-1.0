export function hasFullUploadResult(result) {
  return Boolean(result?.data_quality && result?.engine_result && result?.cultivation_mapping);
}

export function buildEmptyLatestUploadSnapshot() {
  return {
    status: "empty",
    source: "none",
    message: "No data connected yet.",
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
      primary: "No data connected yet",
      secondary: "Upload a telemetry file to activate room context",
      cycle: "Cycle metadata unavailable",
      irrigation: "Irrigation context unavailable",
      uploadedRooms: [],
      roomCount: 0,
    };
  }

  const summaryRooms = extractRoomSummaryNames(result);
  const roomColumn = result.columns.find((column) => {
    const normalized = column.toLowerCase();
    return normalized.includes("room") || normalized.includes("zone");
  });
  const cycleColumn = result.columns.find((column) => {
    const normalized = column.toLowerCase();
    return normalized.includes("cycle") || normalized.includes("stage") || normalized.includes("phase");
  });

  const roomValues = roomColumn
    ? result.preview_rows.map((row) => row[roomColumn]).filter(Boolean)
    : [];
  const cycleValues = cycleColumn
    ? result.preview_rows.map((row) => row[cycleColumn]).filter(Boolean)
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
  return [
    {
      title: "No data connected yet",
      detail: latestStatus === "empty" ? "No completed telemetry upload is available." : "A completed upload is already available.",
      state: latestStatus === "empty" ? "active" : "complete",
      tone: latestStatus === "empty" ? "info" : "nominal",
    },
    {
      title: "Upload processing",
      detail: isUploadProcessing(normalizedState)
        ? "Telemetry file received and processing is underway."
        : "Upload a telemetry file to start ingestion.",
      state: isUploadProcessing(normalizedState) ? "active" : (latestStatus === "active" || uploadError ? "complete" : "standby"),
      tone: isUploadProcessing(normalizedState) ? "review" : "info",
    },
    {
      title: "Upload complete",
      detail: latestStatus === "active"
        ? `${latestUploadSnapshot?.last_filename ?? "Latest upload"} completed and refreshed ${roomContext.primary}.`
        : "Waiting for the next completed upload.",
      state: latestStatus === "active" ? "complete" : "standby",
      tone: latestStatus === "active" ? "nominal" : "info",
    },
    {
      title: "Upload failed",
      detail: uploadError ? normalizeErrorMessage(uploadError) : "Upload errors appear here if processing fails.",
      state: uploadError ? "active" : "standby",
      tone: uploadError ? "elevated" : "info",
    },
    {
      title: "Latest result active",
      detail: latestStatus === "active"
        ? `Dashboard is using ${latestUploadSnapshot?.last_filename ?? "the latest upload"} as the active result.`
        : "Dashboard will switch to the newest completed upload automatically.",
      state: latestStatus === "active" ? "active" : "standby",
      tone: latestStatus === "active" ? "nominal" : "info",
    },
  ];
}

export function connectionStateLabel(latestStatus, uploadState, uploadError) {
  if (uploadError || normalizeUploadStatus(uploadState) === "failed") {
    return "Upload failed";
  }
  if (isUploadProcessing(uploadState)) {
    return "Upload processing";
  }
  if (String(latestStatus).toLowerCase() === "active") {
    return "Latest result active";
  }
  return "No data connected yet";
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
      title: "No active result",
      lines: ["Upload a telemetry file to establish a baseline."],
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
  return [...new Set(values.map((value) => String(value).trim()).filter(Boolean))];
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
  return ["uploading", "pending", "parsing", "baseline_modeling", "running_sii", "writing_state"].includes(normalizeUploadStatus(status));
}

function normalizeErrorMessage(error) {
  if (!error) {
    return "";
  }
  if (typeof error === "string") {
    return error;
  }
  if (error instanceof Error) {
    return error.message;
  }
  try {
    return JSON.stringify(error);
  } catch {
    return String(error);
  }
}
