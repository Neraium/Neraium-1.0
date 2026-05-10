const TELEMETRY_CHANNELS = [
  "temperature",
  "humidity",
  "CO2",
  "HVAC",
  "airflow",
  "irrigation",
  "lighting",
  "sensor network",
];

export function buildOperationalContext(state, deps) {
  const {
    result,
    latestUploadSnapshot,
    apiStatus,
    roomContext,
    systems,
    systemsState,
    intelligenceStatus,
    tick,
  } = state;

  const connectionTone = apiStatus.state === "online" ? "nominal" : "elevated";
  const connectionSummary = apiStatus.checkedAt
    ? `Updated ${deps.formatClockTime(apiStatus.checkedAt)} CT`
    : "Sync initializing";
  const connectionStatusLine = apiStatus.state === "online"
    ? connectionSummary
    : `${connectionSummary}. Using last confirmed state.`;
  const connectionActionHint = apiStatus.state === "online"
    ? ""
    : "Check facility WiFi if room changes stop syncing.";

  const fullResult = deps.hasFullUploadResult(result) ? result : null;
  const uploadIntelligence = fullResult?.sii_intelligence;
  if (uploadIntelligence) {
    return buildSiiOperationalContext({
      intelligence: uploadIntelligence,
      intelligenceStatus,
      result: fullResult,
      latestUploadSnapshot,
      apiStatus,
      roomContext,
      systems,
      systemsState,
      tick,
      connectionTone,
      connectionSummary,
      connectionStatusLine,
      connectionActionHint,
    }, deps);
  }

  if (fullResult) {
    const telemetryCards = buildTelemetryCards(fullResult, deps);
    const facilityTone = deps.mapOperationalTone(fullResult.engine_result?.overall_result ?? fullResult.data_quality?.readiness ?? "nominal");
    const interventionItems = buildUploadedInterventionItems(fullResult, roomContext, telemetryCards, facilityTone, deps);
    const actionQueue = buildActionQueue(interventionItems);
    const primaryWindow = interventionItems[0] ?? null;
    return {
      useDemoTelemetry: false,
      intelligenceMode: "live",
      facilityTone,
      facilityStateLabel: deps.formatEngineResult(fullResult.engine_result?.overall_result ?? "normal"),
      heroTag: facilityTone === "nominal" ? "Control window established" : "Decision window tightening",
      heroHeadline: deps.heroHeadlineFromTone(facilityTone),
      heroSubline: deps.heroSublineFromTone(facilityTone, roomContext.primary),
      readinessLabel: deps.formatReadiness(fullResult.data_quality?.readiness),
      connectionTone,
      connectionLabel: "Latest upload active",
      connectionDetail: apiStatus.detail,
      connectionSummary,
      connectionStatusLine,
      connectionActionHint,
      dataSourceLabel: latestManualSourceLabel(fullResult),
      neraiumScore: calculateNeraiumScore(facilityTone, interventionItems, true),
      scoreNarrative: summarizeScoreNarrative(facilityTone, interventionItems),
      scoreContext: buildScoreContext(calculateNeraiumScore(facilityTone, interventionItems, true), facilityTone, interventionItems),
      windowContext: deps.buildWindowContext(primaryWindow, roomContext),
      primaryWindow,
      interventionItems,
      actionQueue,
      topologyNodes: buildTopologyNodes(interventionItems),
      alerts: buildAlertItems(fullResult, apiStatus),
      findings: buildFindingsFeed(fullResult, deps),
      timeline: buildOperationalTimeline(fullResult, apiStatus, roomContext, deps),
      telemetryCards,
      summaryTelemetry: telemetryCards,
      overviewMetrics: buildOverviewMetrics(fullResult, apiStatus, systems, systemsState, deps),
      roomCards: buildZoneSummary(roomContext),
      roomTransitions: buildRoomTransitions(fullResult, roomContext),
      driftRows: (fullResult.baseline_analysis?.column_drift ?? []).map((row) => ({
        ...row,
        drift_flag: deps.mapOperationalTone(row.drift_flag),
      })),
      relationshipRows: buildRelationshipRows(fullResult, deps),
      irrigationNotes: [
        `Irrigation context: ${roomContext.irrigation}.`,
        "Baseline established from current upload.",
        "Review recommended for irrigation variance only where the room trend persists across the active window.",
      ],
      systemRows: systems.map((system) => [
        system.name,
        system.scope,
        deps.systemRoomContext(system.name, roomContext),
        systemsState === "ready" ? "Backend feed active" : "Backend connection unavailable",
      ]),
      intakeStages: deps.buildConnectionStateStages
        ? deps.buildIntakeStages(fullResult, "complete", roomContext)
        : deps.buildIntakeStages(fullResult, "complete", roomContext),
      evidenceLines: buildEvidenceConsole(fullResult, deps),
      consoleEvents: buildConsoleEvents(fullResult, apiStatus, roomContext, deps),
      observations: deps.buildRoomObservations(fullResult, roomContext),
      reportNotes: deps.reportTemplates,
      connectionEvents: buildConnectionEvents(apiStatus, deps),
    };
  }

  return buildEmptyOperationalContext({
    latestUploadSnapshot,
    apiStatus,
    roomContext,
    systems,
    systemsState,
    connectionTone,
    connectionSummary,
    connectionStatusLine,
    connectionActionHint,
  }, deps);
}

function buildSiiOperationalContext(state, deps) {
  const {
    intelligence,
    intelligenceStatus,
    result,
    latestUploadSnapshot,
    apiStatus,
    roomContext,
    systems,
    systemsState,
    tick,
    connectionTone,
    connectionSummary,
    connectionStatusLine,
    connectionActionHint,
  } = state;

  const safeIntelligence = deps.normalizeFacilityIntelligence(intelligence);
  const fullResult = deps.hasFullUploadResult(result) ? result : null;
  const facilityTone = deps.mapSiiUrgency(safeIntelligence.urgency);
  const interventionItems = buildSiiInterventionItems(safeIntelligence, deps);
  const primaryWindow = interventionItems[0] ?? null;
  const telemetryCards = fullResult ? buildTelemetryCards(fullResult, deps) : buildSiiTelemetryCards(safeIntelligence, deps);
  const actionQueue = buildActionQueue(interventionItems);
  const score = safeIntelligence.neraium_score ?? calculateNeraiumScore(facilityTone, interventionItems, Boolean(fullResult));

  return {
    useDemoTelemetry: false,
    intelligenceMode: safeIntelligence.mode ?? intelligenceStatus?.mode ?? (fullResult ? "live" : "empty"),
    facilityTone,
    facilityStateLabel: safeIntelligence.facility_state ?? deps.formatOperationalLabel(facilityTone),
    heroTag: facilityTone === "nominal" ? "SII state stable" : "SII drift observed",
    heroHeadline: deps.heroHeadlineFromTone(facilityTone),
    heroSubline: safeIntelligence.why_flagged ?? deps.heroSublineFromTone(facilityTone, safeIntelligence.primary_room ?? roomContext.primary),
    readinessLabel: fullResult ? deps.formatReadiness(fullResult.data_quality?.readiness) : "Operational Intelligence Active",
    connectionTone,
    connectionLabel: deps.formatIntelligenceSourceLabel(safeIntelligence.mode ?? intelligenceStatus?.mode),
    connectionDetail: apiStatus.detail,
    connectionSummary,
    connectionStatusLine,
    connectionActionHint,
    dataSourceLabel: fullResult ? latestManualSourceLabel(fullResult) : (latestUploadSnapshot?.result_source ? "File upload" : "No data connected"),
    neraiumScore: score,
    scoreNarrative: summarizeScoreNarrative(facilityTone, interventionItems),
    scoreContext: safeIntelligence.observed_persistence && !deps.isTechnicalEvidenceText(safeIntelligence.observed_persistence)
      ? safeIntelligence.observed_persistence
      : "Room behavior is being compared against recent operating patterns.",
    windowContext: safeIntelligence.baseline_comparison ?? deps.buildWindowContext(primaryWindow, roomContext),
    primaryWindow,
    interventionItems,
    actionQueue,
    topologyNodes: buildTopologyNodes(interventionItems),
    alerts: fullResult ? buildAlertItems(fullResult, apiStatus) : buildSiiAlerts(safeIntelligence, deps),
    findings: fullResult ? buildFindingsFeed(fullResult, deps) : buildSiiFindings(safeIntelligence, deps),
    timeline: fullResult ? buildOperationalTimeline(fullResult, apiStatus, roomContext, deps) : buildSiiTimeline(safeIntelligence, apiStatus, tick, deps),
    telemetryCards,
    summaryTelemetry: telemetryCards.slice(0, 4),
    overviewMetrics: buildOverviewMetrics(fullResult, apiStatus, systems, systemsState, deps),
    roomCards: buildSiiRoomCards(safeIntelligence, deps),
    roomTransitions: fullResult ? buildRoomTransitions(fullResult, roomContext) : buildSiiRoomTransitions(safeIntelligence, deps),
    driftRows: fullResult
      ? (fullResult?.baseline_analysis?.column_drift ?? []).map((row) => ({
          ...row,
          drift_flag: deps.mapOperationalTone(row.drift_flag),
        }))
      : buildSiiDriftRows(safeIntelligence, deps),
    relationshipRows: fullResult ? buildRelationshipRows(fullResult, deps) : buildSiiRelationshipRows(safeIntelligence, deps),
    irrigationNotes: safeIntelligence.what_to_check ?? [],
    systemRows: systems.map((system) => [
      system.name,
      system.scope,
      deps.systemRoomContext(system.name, roomContext),
      systemsState === "ready" ? "Latest upload active" : "Backend connection unavailable",
    ]),
    intakeStages: fullResult
      ? deps.buildIntakeStages(fullResult, "complete", roomContext)
      : deps.buildConnectionStateStages({ latestUploadSnapshot, uploadState: "idle", uploadError: "", roomContext }),
    evidenceLines: fullResult ? buildEvidenceConsole(fullResult, deps) : buildSiiEvidenceLines(safeIntelligence),
    consoleEvents: fullResult ? buildConsoleEvents(fullResult, apiStatus, roomContext, deps) : buildSiiConsoleEvents(safeIntelligence, apiStatus),
    observations: fullResult ? deps.buildRoomObservations(fullResult, roomContext) : [
      safeIntelligence.why_flagged,
      safeIntelligence.baseline_comparison,
      safeIntelligence.confidence_basis,
    ].filter(Boolean),
    reportNotes: [
      "Operational intelligence is active",
      `Mode: ${deps.formatIntelligenceModeValue(safeIntelligence.mode)}`,
      `Evidence fields: ${(intelligenceStatus?.evidence_fields_present ?? []).length}`,
    ],
    connectionEvents: buildConnectionEvents(apiStatus, deps),
  };
}

function buildEmptyOperationalContext(state, deps) {
  const {
    latestUploadSnapshot,
    apiStatus,
    roomContext,
    systems,
    systemsState,
    connectionTone,
    connectionSummary,
    connectionStatusLine,
    connectionActionHint,
  } = state;

  const message = latestUploadSnapshot?.message ?? "No data connected yet.";
  const items = [{
    id: "connect-data",
    label: "Connect telemetry",
    detail: "Upload a telemetry file in Data Connections to activate dashboard values.",
    tone: "info",
    window: "Awaiting upload",
    impact: "No active result",
    actions: ["Upload"],
    technicalDetails: [
      `latest_upload_status=${latestUploadSnapshot?.status ?? "empty"}`,
      `api_status=${apiStatus.state}`,
    ],
  }];

  return {
    useDemoTelemetry: false,
    intelligenceMode: "empty",
    facilityTone: "info",
    facilityStateLabel: "No data connected yet",
    heroTag: "Awaiting telemetry",
    heroHeadline: "Upload telemetry to activate live facility intelligence.",
    heroSubline: message,
    readinessLabel: "No active upload",
    connectionTone,
    connectionLabel: "No upload connected",
    connectionDetail: apiStatus.detail,
    connectionSummary,
    connectionStatusLine,
    connectionActionHint,
    dataSourceLabel: "Awaiting upload",
    neraiumScore: null,
    scoreNarrative: "Neraium score will appear after a completed upload.",
    scoreContext: "No completed upload is available yet.",
    windowContext: "Upload a telemetry file to establish the operating window.",
    primaryWindow: items[0],
    interventionItems: items,
    actionQueue: [],
    topologyNodes: [],
    alerts: [{ title: "No data connected yet", detail: message, tone: "info" }],
    findings: [{ title: "Upload required", detail: "Dashboard cards will update when a telemetry file finishes processing.", tone: "info" }],
    timeline: buildConnectionEvents(apiStatus, deps),
    telemetryCards: buildEmptyTelemetryCards(),
    summaryTelemetry: buildEmptyTelemetryCards().slice(0, 4),
    overviewMetrics: buildEmptyOverviewMetrics(systems, systemsState),
    roomCards: [{ label: "Primary room", value: roomContext.primary, detail: roomContext.secondary, tone: "info" }],
    roomTransitions: [],
    driftRows: [],
    relationshipRows: [],
    irrigationNotes: ["No telemetry has been processed yet."],
    systemRows: systems.map((system) => [
      system.name,
      system.scope,
      deps.systemRoomContext(system.name, roomContext),
      systemsState === "ready" ? "Awaiting connected telemetry" : "Backend connection unavailable",
    ]),
    intakeStages: deps.buildConnectionStateStages({ latestUploadSnapshot, uploadState: "idle", uploadError: "", roomContext }),
    evidenceLines: [
      "connection.state=no_data",
      `api.state=${apiStatus.state}`,
      "latest_result=unavailable",
    ],
    consoleEvents: [
      `telemetry.link=${apiStatus.state}`,
      "telemetry.status=no_data",
      "event.awaiting_upload=true",
    ],
    observations: [message],
    reportNotes: ["No data connected yet", "Upload required before facility intelligence can run"],
    connectionEvents: buildConnectionEvents(apiStatus, deps),
  };
}

function buildTelemetryCards(result, deps) {
  if (!result) {
    return TELEMETRY_CHANNELS.map((channel) => ({
      label: deps.formatCategory(channel),
      primary: "No active result",
      secondary: "Upload telemetry to populate this system signal.",
      series: [],
      tone: "info",
    }));
  }

  const mapping = result.cultivation_mapping?.categories ?? {};
  const profilesByColumn = new Map((result.numeric_profiles ?? []).map((profile) => [profile.column, profile]));
  const driftByColumn = new Map((result.baseline_analysis?.column_drift ?? []).map((row) => [row.column, row]));

  return TELEMETRY_CHANNELS.map((channel) => {
    const mappedColumns = mapping[channel] ?? [];
    const profile = mappedColumns.map((column) => profilesByColumn.get(column)).find(Boolean);
    const drift = mappedColumns.map((column) => driftByColumn.get(column)).find(Boolean);

    if (!profile) {
      return {
        label: deps.formatCategory(channel),
        primary: mappedColumns.length > 0 ? "Mapped without numeric profile" : "Awaiting additional room telemetry",
        secondary: mappedColumns.length > 0
          ? mappedColumns.join(", ")
          : "No uploaded channel mapped to this system category yet.",
        series: [],
        tone: "info",
      };
    }

    return {
      label: deps.formatCategory(channel),
      primary: `${profile.average} avg`,
      secondary: `${profile.column} | ${profile.missing_percent}% missing`,
      series: buildSeries(profile, drift),
      tone: deps.mapOperationalTone(drift?.drift_flag ?? profile.variability ?? "normal"),
    };
  });
}

function buildOperationalTimeline(result, apiStatus, roomContext, deps) {
  const items = [];

  if (apiStatus) {
    items.push({
      time: "Session",
      title: apiStatus.label,
      detail: apiStatus.detail,
      tone: apiStatus.state,
    });
  }

  if (!deps.hasFullUploadResult(result)) {
    items.push({
      time: "Standby",
      title: "Telemetry batch processing",
      detail: `SII processing is active. ${roomContext.primary} remains on the last confirmed state until the runner writes new findings.`,
      tone: "info",
    });
    items.push({
      time: "Standby",
      title: "Awaiting completed runner output",
      detail: "Facility Command will update after the completed SII state is available.",
      tone: "review",
    });
    return items;
  }

  const timeCoverage = deps.deriveTimeCoverage(result);
  items.push({
    time: timeCoverage.first ?? "Batch start",
    title: "Time coverage opened",
    detail: `Detected ${result.detected_timestamp_column ?? "row-order"} timeline context.`,
    tone: "online",
  });
  items.push({
    time: "Batch",
    title: "Ingest validated",
    detail: `${result.row_count} rows and ${result.column_count} columns parsed in memory.`,
    tone: "online",
  });
  items.push({
    time: "Batch",
    title: "Room context resolved",
    detail: roomContext.primary,
    tone: "muted",
  });
  items.push({
    time: "Review",
    title: "Readiness assessed",
    detail: deps.formatReadiness(result.data_quality?.readiness),
    tone: deps.mapOperationalTone(result.data_quality?.readiness),
  });
  items.push({
    time: "Review",
    title: "Mapping coverage",
    detail: `${result.cultivation_mapping?.mapped_column_count ?? 0} mapped columns across cultivation systems.`,
    tone: (result.cultivation_mapping?.mapped_column_count ?? 0) > 0 ? "nominal" : "info",
  });
  if (result.engine_result) {
    items.push({
      time: timeCoverage.last ?? "Findings",
      title: "Operational findings generated",
      detail: deps.formatEngineResult(result.engine_result.overall_result),
      tone: deps.mapOperationalTone(result.engine_result.overall_result),
    });
  }
  return items;
}

function buildFindingsFeed(result, deps) {
  if (!result) {
    return [];
  }

  const items = [];
  const signals = result.engine_result?.signals ?? [];
  const observations = result.operator_report?.key_observations ?? [];
  const reviewColumns = result.operator_report?.columns_requiring_review ?? [];

  signals.slice(0, 4).forEach((signal) => {
    items.push({
      title: "Engine signal",
      detail: signal.message,
      tone: deps.mapOperationalTone(signal.level ?? result.engine_result?.overall_result ?? "info"),
    });
  });

  observations.slice(0, 3).forEach((observation) => {
    items.push({
      title: "Observation",
      detail: observation,
      tone: "info",
    });
  });

  reviewColumns.slice(0, 3).forEach((item) => {
    items.push({
      title: "Column review",
      detail: `${item.column}: ${item.reasons.join(" ")}`,
      tone: "review",
    });
  });

  return items;
}

function buildAlertItems(result, apiStatus) {
  const alerts = [];

  if (apiStatus.state !== "online") {
    alerts.push({
      title: "Facility sync delayed",
      detail: "Using the last confirmed state. Check facility WiFi if room changes stop syncing.",
      tone: "elevated",
    });
  }

  if (!result) {
    alerts.push({
      title: "No active result",
      detail: "Upload telemetry in Data Connections to activate Facility Command.",
      tone: "info",
    });
    return alerts;
  }

  (result.warnings ?? []).slice(0, 2).forEach((warning) => {
    alerts.push({
      title: "Batch warning",
      detail: warning,
      tone: "review",
    });
  });

  (result.engine_result?.limitations ?? []).slice(0, 2).forEach((limitation) => {
    alerts.push({
      title: "Review limitation",
      detail: limitation,
      tone: "info",
    });
  });

  (result.operator_report?.recommended_operator_checks ?? []).slice(0, 2).forEach((check) => {
    alerts.push({
      title: "Grower check",
      detail: check,
      tone: "review",
    });
  });

  return alerts.length > 0
    ? alerts
    : [{ title: "No active grower alerts", detail: "Current upload remains within monitored operational baselines.", tone: "nominal" }];
}

function buildOverviewMetrics(result, apiStatus, systems, systemsState, deps) {
  return [
    { label: "Facility stability", value: result?.engine_result ? deps.deriveFacilityStability(result) : "No active result" },
    { label: "Active alerts", value: buildAlertItems(result, apiStatus).length },
    { label: "Data source", value: result ? latestManualSourceLabel(result) : "No data connected" },
    { label: "Uploaded rooms", value: result?.room_summary?.room_count ?? result?.sii_intelligence?.rooms?.length ?? 0 },
    { label: "Systems in scope", value: systemsState === "ready" ? `${systems.length} monitored` : `${systems.length} defined` },
  ];
}

function buildZoneSummary(roomContext) {
  const uploadedRooms = Array.isArray(roomContext.uploadedRooms) ? roomContext.uploadedRooms : [];
  if (uploadedRooms.length > 0) {
    return uploadedRooms.slice(0, 8).map((room, index) => ({
      label: index === 0 ? "Primary room" : `Uploaded room ${index + 1}`,
      value: room,
      detail: `${uploadedRooms.length} room${uploadedRooms.length === 1 ? "" : "s"} detected in the latest upload.`,
      tone: index === 0 ? "nominal" : "info",
    }));
  }

  return [
    { label: "Primary room", value: roomContext.primary, detail: "Current room or zone resolved from the latest completed upload.", tone: "nominal" },
    { label: "Secondary lane", value: roomContext.secondary, detail: "Secondary review context from the latest completed upload.", tone: "info" },
    { label: "Grow cycle", value: roomContext.cycle, detail: "Cycle context from the uploaded telemetry when available.", tone: "review" },
    { label: "Irrigation review", value: roomContext.irrigation, detail: "Irrigation context reflects mapped channels when present.", tone: "review" },
  ];
}

function buildRoomTransitions(result, roomContext) {
  const items = [
    { time: "Transition", title: "Primary room context", detail: roomContext.primary, tone: "nominal" },
    { time: "Transition", title: "Secondary review lane", detail: roomContext.secondary, tone: "info" },
    { time: "Transition", title: "Irrigation context", detail: roomContext.irrigation, tone: "review" },
  ];

  if (result?.timestamp_profile?.estimated_sample_interval) {
    items.push({ time: "Timing", title: "Sample interval", detail: result.timestamp_profile.estimated_sample_interval, tone: "nominal" });
  }

  return items;
}

function buildEvidenceConsole(result, deps) {
  if (!deps.hasFullUploadResult(result)) {
    return [
      "evidence.console=telemetry_processing",
      "schema.mapping=awaiting_completed_runner_output",
      "grower.report=last_confirmed_state_preserved",
    ];
  }

  const lines = [
    `batch.file=${result.filename}`,
    `data.readiness=${result.data_quality?.readiness ?? "processing"}`,
    `rows=${result.row_count}`,
    `columns=${result.column_count}`,
    `mapping.coverage=${result.cultivation_mapping?.coverage_percent ?? 0}%`,
  ];

  (result.operator_report?.source_sections_used ?? []).forEach((section) => lines.push(`report.source=${section}`));
  (result.operator_report?.columns_requiring_review ?? []).slice(0, 4).forEach((item) => lines.push(`review.column=${item.column}`));
  (result.engine_result?.audit_trace ?? []).slice(0, 12).forEach((entry) => lines.push(`engine.audit=${entry}`));
  return lines;
}

function buildConsoleEvents(result, apiStatus, roomContext, deps) {
  const lines = [
    `console.link=${apiStatus.label}`,
    `console.room=${roomContext.primary}`,
    `console.secondary=${roomContext.secondary}`,
    `console.irrigation=${roomContext.irrigation}`,
  ];

  if (deps.hasFullUploadResult(result)) {
    lines.push(`console.batch=${result.filename}`);
    lines.push(`console.readiness=${result.data_quality?.readiness ?? "processing"}`);
    (result.engine_result?.signals ?? []).slice(0, 6).forEach((signal) => lines.push(`signal.event=${signal.message}`));
  } else {
    lines.push("console.batch=telemetry_processing");
  }

  return [...lines, ...buildEvidenceConsole(result, deps).slice(0, 10)];
}

function buildRelationshipRows(result, deps) {
  const evidence = result?.engine_result?.evidence ?? [];
  return evidence
    .filter((item) => item.type === "relationship_change")
    .map((item) => ({
      ...item,
      detail: deps.translateEvidenceLine(
        deps.relationshipDetail(item),
        deps.inferOperationalCategory(item.columns?.join(" "), item.detail),
      ),
      tone: deps.mapOperationalTone(item.level ?? "review"),
      technicalDetails: [
        item.detail && `detail=${item.detail}`,
        item.baseline_correlation !== undefined && `baseline_correlation=${item.baseline_correlation}`,
        item.recent_correlation !== undefined && `recent_correlation=${item.recent_correlation}`,
        item.columns && `columns=${item.columns.join(",")}`,
      ].filter(Boolean),
    }));
}

function buildUploadedInterventionItems(result, roomContext, telemetryCards, facilityTone, deps) {
  const engineSignals = result?.engine_result?.signals ?? [];
  const columnReview = result?.operator_report?.columns_requiring_review ?? [];
  const attribution = result?.driver_attribution;
  const irrigationTone = result?.cultivation_mapping?.categories?.irrigation?.length ? "review" : "info";
  const attributionGuidance = deps.buildGuidanceFromAttribution(attribution, facilityTone);
  const attributionTechnicalDetails = [
    attribution?.driver_category && `driver_category=${attribution.driver_category}`,
    attribution?.likely_driver && `likely_driver=${attribution.likely_driver}`,
    attribution?.confidence_basis && `confidence_basis=${attribution.confidence_basis}`,
    attribution?.attribution_confidence && `attribution_confidence=${attribution.attribution_confidence}`,
    ...(attribution?.supporting_evidence ?? []).map((line, index) => `supporting_evidence_${index + 1}=${line}`),
    ...(engineSignals ?? []).slice(0, 4).map((signal, index) => `engine_signal_${index + 1}=${signal.message}`),
  ].filter(Boolean);

  return [
    {
      id: "upload-hvac-balance",
      label: attribution?.room ?? roomContext.primary,
      title: `${attribution?.room ?? roomContext.primary} intervention window`,
      shortTitle: attribution?.room ?? roomContext.primary,
      status: "HVAC balance review",
      window: deps.windowLabelFromTone(facilityTone),
      tone: deps.attributionTone(attribution, facilityTone),
      confidence: deps.confidenceFromAttribution(attribution, facilityTone),
      summary: attributionGuidance.primaryDriver,
      detail: `Current upload places ${attribution?.room ?? roomContext.primary} in the primary review lane.`,
      shortDetail: attributionGuidance.primaryDriver,
      whyHeadline: attribution?.supporting_evidence?.[0]
        ? deps.translateEvidenceLine(attribution.supporting_evidence[0], attribution?.driver_category)
        : engineSignals[0]?.message
          ? deps.translateEvidenceLine(engineSignals[0].message, attribution?.driver_category)
          : "Current room trend and readiness signals are tightening the available intervention window.",
      drivers: (attribution?.supporting_evidence ?? buildWhyDrivers(result, telemetryCards, roomContext))
        .map((line) => deps.translateEvidenceLine(line, attribution?.driver_category)),
      driverAttribution: attribution,
      likelyDriver: attribution?.likely_driver,
      contributingSignals: attribution?.contributing_signals,
      confidenceBasis: attribution?.confidence_basis && deps.isTechnicalEvidenceText(attribution.confidence_basis)
        ? "Telemetry evidence is strong enough to prioritize an operator inspection."
        : attribution?.confidence_basis,
      supportingEvidence: (attribution?.supporting_evidence ?? []).map((line) => deps.translateEvidenceLine(line, attribution?.driver_category)),
      structuralExplanation: buildUploadedStructuralExplanation(attribution, engineSignals).map((line) => deps.translateEvidenceLine(line, attribution?.driver_category)),
      technicalDetails: attributionTechnicalDetails,
      guidance: attributionGuidance,
      decisionLabel: deps.decisionLabelFromTone(facilityTone, 0),
      baselineContext: deps.buildUploadBaselineContext(roomContext, facilityTone),
      recommendation: deps.recommendationFromTone(facilityTone),
      primaryAction: deps.operatorMoveFromGuidance(attributionGuidance),
      actions: deps.actionSetFromTone(facilityTone),
      impact: deps.impactFromTone(facilityTone),
      change: "Updated from active upload",
      rankLabel: "Priority 01",
    },
    {
      id: "upload-irrigation-recovery",
      label: roomContext.secondary,
      title: `${roomContext.secondary} review horizon`,
      shortTitle: roomContext.secondary,
      status: "Irrigation recovery",
      window: deps.windowLabelFromTone(irrigationTone),
      tone: irrigationTone,
      confidence: deps.confidenceFromTone(irrigationTone, true),
      summary: columnReview[0]
        ? `${columnReview[0].column} requires review before the next irrigation cycle change.`
        : "Irrigation variance remains a secondary review lane until more room telemetry is uploaded.",
      detail: roomContext.irrigation,
      shortDetail: columnReview[0]
        ? `${columnReview[0].column} should be validated before the next cycle change.`
        : "Irrigation balance remains a scheduled review item.",
      whyHeadline: "Current irrigation behavior is not yet critical, but it is close enough to justify scheduled review.",
      drivers: [
        `Current irrigation context: ${roomContext.irrigation}.`,
        "Baseline established from current upload.",
        "Review is being prioritized over passive monitoring.",
      ],
      structuralExplanation: [
        "Irrigation response is being compared against recent room behavior.",
        "Cycle settling remains the current operating state.",
        "Room behavior is moving earlier than its recent baseline.",
      ],
      guidance: deps.buildGuidanceFromCategory("irrigation_balance"),
      decisionLabel: "Validate irrigation balance",
      baselineContext: `${roomContext.secondary} typically holds a longer recovery window. Current irrigation recovery is shortening.`,
      recommendation: deps.recommendationFromTone(irrigationTone),
      primaryAction: deps.operatorMoveFromGuidance(deps.buildGuidanceFromCategory("irrigation_balance")),
      actions: deps.actionSetFromTone(irrigationTone),
      impact: deps.impactFromTone(irrigationTone),
      change: "Review horizon opened",
      rankLabel: "Priority 02",
    },
    {
      id: "upload-telemetry-continuity",
      label: "Facility telemetry",
      title: "Telemetry continuity window",
      shortTitle: "Facility telemetry",
      status: "Upload continuity",
      window: deps.apiStatusWindow(result),
      tone: "info",
      confidence: 68,
      summary: "Uploaded telemetry is connected, but additional room context will improve intervention precision.",
      detail: result?.filename ?? "Latest upload active",
      shortDetail: "Additional room coverage will improve decision confidence.",
      whyHeadline: "The facility is connected, but the confidence of longer-range decisions improves as room coverage deepens.",
      drivers: [
        `${result.row_count} rows and ${result.column_count} columns parsed in memory.`,
        `${result.cultivation_mapping?.mapped_column_count ?? 0} mapped columns currently in scope.`,
        "Awaiting additional room telemetry where facility context is partial.",
      ],
      structuralExplanation: [
        "Traceability is improving as room coverage deepens.",
        "Relationship evidence is limited until more facility telemetry is connected.",
        "Infrastructure movement remains under observation.",
      ],
      guidance: deps.buildGuidanceFromCategory("telemetry_continuity"),
      decisionLabel: "Continue monitoring",
      baselineContext: "Facility-level confidence improves as room coverage deepens and more week-specific context is connected.",
      recommendation: "Continue monitoring",
      primaryAction: deps.operatorMoveFromGuidance(deps.buildGuidanceFromCategory("telemetry_continuity")),
      actions: ["Acknowledge", "Schedule", "Escalate", "Ignore"],
      impact: "Facility-wide confidence",
      change: "Latest ingest synchronized",
      rankLabel: "Priority 03",
    },
  ];
}

function buildSiiInterventionItems(intelligence, deps) {
  const rooms = Array.isArray(intelligence.rooms) && intelligence.rooms.length > 0 ? intelligence.rooms : [intelligence];
  return rooms.map((room, index) => {
    const tone = deps.mapSiiUrgency(room.urgency ?? intelligence.urgency);
    const rawSupportingEvidence = room.supporting_evidence ?? intelligence.supporting_evidence ?? [];
    const rawRelationshipEvidence = room.relationship_evidence ?? intelligence.relationship_evidence ?? [];
    const translation = deps.buildOperationalTranslation({
      driver: room.primary_driver ?? intelligence.primary_driver,
      driverCategory: room.driver_category ?? intelligence.driver_category,
      why: room.why_flagged ?? intelligence.why_flagged,
      evidence: rawSupportingEvidence,
      relationships: rawRelationshipEvidence,
      confidenceBasis: room.confidence_basis ?? intelligence.confidence_basis,
      baselineContext: room.baseline_comparison ?? intelligence.baseline_comparison,
      urgency: room.urgency ?? intelligence.urgency,
      window: room.intervention_window ?? intelligence.intervention_window,
    });
    const guidance = {
      nextMove: room.recommended_operator_review ?? intelligence.recommended_operator_review ?? "Continue monitoring",
      primaryDriver: translation.primaryDriver,
      whyFlagged: translation.whyFlagged,
      whatToCheck: room.what_to_check ?? intelligence.what_to_check ?? translation.whatToCheck,
    };
    return {
      id: `sii-room-${index + 1}`,
      label: room.room ?? intelligence.primary_room ?? "Current room",
      title: `${room.room ?? intelligence.primary_room ?? "Current room"} SII state`,
      shortTitle: room.room ?? intelligence.primary_room ?? "Current room",
      status: room.room_state ?? intelligence.facility_state ?? "Monitoring",
      window: room.intervention_window ?? intelligence.intervention_window ?? "Monitoring",
      tone,
      confidence: room.confidence ?? deps.confidenceFromTone(tone, intelligence.mode === "live"),
      summary: guidance.primaryDriver,
      detail: translation.baselineContext,
      shortDetail: guidance.primaryDriver,
      whyHeadline: guidance.whyFlagged,
      drivers: translation.supportingEvidence,
      supportingEvidence: translation.supportingEvidence,
      relationshipEvidence: translation.relationshipEvidence,
      structuralExplanation: (room.structural_explanation ?? intelligence.structural_explanation ?? [])
        .map((line) => deps.translateEvidenceLine(line, translation.category)),
      confidenceBasis: translation.confidenceBasis,
      technicalDetails: translation.technicalDetails,
      guidance,
      baselineContext: translation.baselineContext,
      recommendation: guidance.nextMove,
      primaryAction: guidance.nextMove,
      decisionLabel: room.room_state ?? intelligence.facility_state ?? deps.decisionLabelFromTone(tone, index),
      actions: deps.actionSetFromTone(tone),
      impact: deps.impactFromTone(tone),
      change: deps.isTechnicalEvidenceText(room.observed_persistence ?? intelligence.observed_persistence)
        ? deps.translateEvidenceLine(room.observed_persistence ?? intelligence.observed_persistence, translation.category)
        : (room.observed_persistence ?? intelligence.observed_persistence ?? "Evidence active"),
      rankLabel: `Priority ${String(index + 1).padStart(2, "0")}`,
    };
  }).sort((a, b) => deps.tonePriority(a.tone) - deps.tonePriority(b.tone));
}

function buildActionQueue(interventionItems) {
  return interventionItems
    .map((item, index) => ({
      ...item,
      id: `action-${item.id}`,
      targetId: item.id,
      rankLabel: `Priority ${String(index + 1).padStart(2, "0")}`,
      title: item.title,
      detail: item.summary,
    }))
    .sort((a, b) => (a.tone > b.tone ? 1 : -1));
}

function buildTopologyNodes(interventionItems) {
  return interventionItems.slice(0, 6).map((item) => ({
    id: item.id,
    label: item.label,
    window: item.window,
    status: item.status,
    tone: item.tone,
    confidence: item.confidence,
    summary: item.summary,
    whyHeadline: item.whyHeadline,
    drivers: item.drivers,
    recommendation: item.recommendation,
    change: item.change,
  }));
}

function buildSiiTelemetryCards(intelligence, deps) {
  const translation = deps.buildOperationalTranslation({
    driver: intelligence.primary_driver,
    driverCategory: intelligence.driver_category,
    why: intelligence.why_flagged,
    evidence: intelligence.supporting_evidence ?? [],
    relationships: intelligence.relationship_evidence ?? [],
    confidenceBasis: intelligence.confidence_basis,
    baselineContext: intelligence.baseline_comparison,
    urgency: intelligence.urgency,
    window: intelligence.intervention_window,
  });
  return [
    { label: "Primary driver", primary: translation.primaryDriver, secondary: translation.whyFlagged, series: [72, 74, 76, 75, 78, 80], tone: deps.mapSiiUrgency(intelligence.urgency), technicalDetails: translation.technicalDetails },
    { label: "Relationship evidence", primary: translation.relationshipEvidence[0] ?? "Relationship evidence limited", secondary: translation.confidenceBasis, series: [60, 61, 63, 62, 64, 66], tone: "info", technicalDetails: translation.technicalDetails },
    { label: "Intervention window", primary: intelligence.intervention_window ?? "Monitoring", secondary: translation.baselineContext, series: [80, 78, 76, 73, 71, 69], tone: deps.mapSiiUrgency(intelligence.urgency), technicalDetails: translation.technicalDetails },
  ];
}

function buildSiiRoomCards(intelligence, deps) {
  return (intelligence.rooms ?? [intelligence]).map((room) => ({
    label: room.room ?? intelligence.primary_room ?? "Current room",
    value: room.room_state ?? intelligence.facility_state ?? "Monitoring",
    detail: deps.buildOperationalTranslation({
      driver: room.primary_driver ?? intelligence.primary_driver,
      why: room.why_flagged ?? intelligence.why_flagged,
      evidence: room.supporting_evidence ?? intelligence.supporting_evidence ?? [],
      relationships: room.relationship_evidence ?? intelligence.relationship_evidence ?? [],
    }).primaryDriver,
    tone: deps.mapSiiUrgency(room.urgency ?? intelligence.urgency),
  }));
}

function buildSiiAlerts(intelligence, deps) {
  const translation = deps.buildOperationalTranslation({
    driver: intelligence.primary_driver,
    why: intelligence.why_flagged,
    evidence: intelligence.supporting_evidence ?? [],
    relationships: intelligence.relationship_evidence ?? [],
  });
  return [{ title: intelligence.facility_state ?? "SII state active", detail: translation.whyFlagged, tone: deps.mapSiiUrgency(intelligence.urgency) }];
}

function buildSiiFindings(intelligence, deps) {
  const translation = deps.buildOperationalTranslation({
    driver: intelligence.primary_driver,
    driverCategory: intelligence.driver_category,
    why: intelligence.why_flagged,
    evidence: intelligence.supporting_evidence ?? [],
    relationships: intelligence.relationship_evidence ?? [],
    confidenceBasis: intelligence.confidence_basis,
  });
  return [
    { title: "Primary driver", detail: translation.primaryDriver, tone: deps.mapSiiUrgency(intelligence.urgency) },
    { title: "Why flagged", detail: translation.whyFlagged, tone: "info" },
    ...(intelligence.what_to_check ?? []).slice(0, 2).map((check) => ({ title: "What to check", detail: check, tone: "info" })),
  ];
}

function buildSiiTimeline(intelligence, apiStatus, tick, deps) {
  const translation = deps.buildOperationalTranslation({
    driver: intelligence.primary_driver,
    why: intelligence.why_flagged,
    evidence: intelligence.supporting_evidence ?? [],
    relationships: intelligence.relationship_evidence ?? [],
  });
  return [{
    time: deps.formatClockTime(intelligence.last_updated ?? apiStatus.checkedAt ?? new Date(Date.now() - tick * 30000).toISOString()),
    title: "Operational intelligence updated",
    detail: deps.isTechnicalEvidenceText(intelligence.observed_persistence)
      ? deps.translateEvidenceLine(intelligence.observed_persistence, translation.category)
      : (intelligence.observed_persistence ?? translation.whyFlagged),
    tone: deps.mapSiiUrgency(intelligence.urgency),
  }];
}

function buildSiiRoomTransitions(intelligence, deps) {
  return (intelligence.structural_explanation ?? []).slice(0, 3).map((detail, index) => ({
    title: index === 0 ? "Operational explanation" : "Relationship movement",
    detail: deps.translateEvidenceLine(detail, deps.inferOperationalCategory(intelligence.primary_driver, intelligence.why_flagged)),
    tone: deps.mapSiiUrgency(intelligence.urgency),
  }));
}

function buildSiiDriftRows(intelligence, deps) {
  return [{
    column: "SII baseline comparison",
    direction: "observed",
    drift_flag: deps.mapSiiUrgency(intelligence.urgency),
    baseline_average: 0,
    recent_average: 0,
    detail: deps.buildOperationalTranslation({
      driver: intelligence.primary_driver,
      baselineContext: intelligence.baseline_comparison,
      why: intelligence.why_flagged,
    }).baselineContext,
  }];
}

function buildSiiRelationshipRows(intelligence, deps) {
  return (intelligence.relationship_evidence ?? []).map((detail, index) => ({
    columns: ["environmental coupling", "recent baseline"],
    change: deps.relationshipDetail({ detail }),
    tone: deps.mapSiiUrgency(intelligence.urgency),
    detail: deps.translateEvidenceLine(detail, deps.inferOperationalCategory(intelligence.primary_driver, intelligence.why_flagged)),
    technicalDetails: [`relationship_evidence_${index + 1}=${detail}`],
  }));
}

function buildSiiEvidenceLines(intelligence) {
  return [
    `sii.source=${intelligence.source ?? "sii_engine"}`,
    `sii.mode=${intelligence.mode ?? "unknown"}`,
    `sii.score=${intelligence.neraium_score ?? "unavailable"}`,
    `sii.primary_driver=${intelligence.primary_driver ?? "unavailable"}`,
    ...(intelligence.supporting_evidence ?? []).slice(0, 4).map((line, index) => `sii.evidence_${index + 1}=${line}`),
  ];
}

function buildSiiConsoleEvents(intelligence, apiStatus) {
  return [
    `event.sii_mode=${intelligence.mode ?? "unknown"}`,
    `event.api_state=${apiStatus.state}`,
    `event.active_rooms=${intelligence.rooms?.length ?? 0}`,
    ...buildSiiEvidenceLines(intelligence),
  ];
}

function buildEmptyTelemetryCards() {
  return [
    { label: "Neraium Score", primary: "No active result", secondary: "Complete an upload to calculate a score.", series: [], tone: "info" },
    { label: "Operating State", primary: "No data connected yet", secondary: "This updates from the latest completed upload.", series: [], tone: "info" },
    { label: "Primary Room", primary: "Awaiting upload", secondary: "Room context appears after ingestion completes.", series: [], tone: "info" },
    { label: "Drift", primary: "Awaiting upload", secondary: "Drift and alerts appear after a completed upload.", series: [], tone: "info" },
  ];
}

function buildEmptyOverviewMetrics(systems, systemsState) {
  return [
    { label: "Facility Stability", value: "No data connected yet" },
    { label: "Rooms Under Review", value: 0 },
    { label: "Telemetry Cadence", value: "Awaiting upload" },
    { label: "Systems in Scope", value: systemsState === "ready" ? `${systems.length} monitored` : `${systems.length} defined` },
  ];
}

function calculateNeraiumScore(facilityTone, interventionItems, hasUpload) {
  const base = facilityTone === "nominal" ? 92 : facilityTone === "review" ? 78 : facilityTone === "elevated" ? 63 : 49;
  const confidenceLift = Math.round(average(interventionItems.map((item) => item.confidence)) / 12);
  const uploadLift = hasUpload ? 4 : 0;
  return Math.max(0, Math.min(base + confidenceLift + uploadLift, 100));
}

function summarizeScoreNarrative(facilityTone, interventionItems) {
  const urgentCount = interventionItems.filter((item) => item.tone === "elevated" || item.tone === "unstable").length;
  if (facilityTone === "nominal") {
    return "The facility remains inside a comfortable intervention horizon.";
  }
  if (urgentCount > 0) {
    return `${urgentCount} room window${urgentCount === 1 ? "" : "s"} shortened enough to warrant immediate grower attention.`;
  }
  return "Most rooms remain controllable, with review concentrated in a narrow set of rooms.";
}

function buildScoreContext(score, facilityTone) {
  const facilityAverage = facilityTone === "nominal" ? 74 : facilityTone === "review" ? 68 : facilityTone === "elevated" ? 62 : 58;
  const trendDelta = facilityTone === "nominal" ? 2 : facilityTone === "review" ? -1 : facilityTone === "elevated" ? -4 : -7;
  const trendArrow = trendDelta >= 0 ? "+" : "";
  return `Facility confidence ${facilityAverage} | Goal 80+ | Trend ${trendArrow}${trendDelta} pts since yesterday`;
}

function latestManualSourceLabel(result) {
  return result?.filename ? "Telemetry upload" : "No data connected";
}

function buildWhyDrivers(result, telemetryCards, roomContext) {
  const firstCards = telemetryCards.slice(0, 2);
  return [
    firstCards[0] ? `${firstCards[0].label} currently reading ${firstCards[0].primary}.` : `Primary room context: ${roomContext.primary}.`,
    firstCards[1] ? `${firstCards[1].label} currently reading ${firstCards[1].primary}.` : `Secondary room context: ${roomContext.secondary}.`,
    result?.operator_report?.recommended_operator_checks?.[0] ?? "Recommended next move is based on the current room readiness and trend pattern.",
  ];
}

function buildUploadedStructuralExplanation(attribution, engineSignals) {
  if (attribution?.driver_category === "humidity_control") {
    return [
      "Temperature recovery is decoupling from humidity stabilization.",
      "Environmental coupling is less consistent than the room's recent baseline.",
      "Room recovery behavior is compressing the intervention horizon.",
    ];
  }
  if (attribution?.driver_category === "sensor_network") {
    return [
      "Telemetry continuity is limiting structural confidence.",
      "Room relationships need cleaner source coverage before attribution tightens.",
      "Traceability is the next operating constraint.",
    ];
  }
  if (engineSignals?.length) {
    return [
      "Room behavior is moving against its recent baseline.",
      "Relationship evidence is being held as supporting context.",
      "Infrastructure does not fail suddenly. It moves.",
    ];
  }
  return [
    "Environmental coupling remains stable.",
    "Room behavior is staying within its recent baseline.",
    "Infrastructure does not fail suddenly. It moves.",
  ];
}

function buildConnectionEvents(apiStatus, deps) {
  const checkedAt = apiStatus.checkedAt ?? new Date().toISOString();
  return [
    {
      title: apiStatus.state === "online" ? "Backend sync current" : "Sync delayed",
      detail: apiStatus.state === "online"
        ? `Last sync ${deps.formatClockTime(checkedAt)} CT.`
        : `Last confirmed state held from ${deps.formatClockTime(checkedAt)} CT.`,
      tone: apiStatus.state === "online" ? "nominal" : "elevated",
    },
    {
      title: apiStatus.state === "online" ? "Connection monitor" : "Grower action",
      detail: apiStatus.state === "online"
        ? "Backend connection is healthy."
        : "Check facility WiFi if room changes stop syncing.",
      tone: apiStatus.state === "online" ? "info" : "review",
    },
  ];
}

function buildSeries(profile, drift) {
  const values = [profile.min, profile.average, profile.max]
    .filter((value) => typeof value === "number")
    .map((value) => Math.abs(value));
  if (drift && typeof drift.absolute_change === "number") {
    values.push(Math.abs(drift.absolute_change));
  }
  return values;
}

function average(values) {
  return values.reduce((sum, value) => sum + value, 0) / Math.max(values.length, 1);
}
