import { resolveSessionJobId } from "./currentSession";
import { hasFullUploadResult } from "./uploadState";

export const OPERATOR_EMPTY_STATE = {
  title: "No current observations.",
  subtitle: "Telemetry is being monitored.",
  detail: "No equipment issues detected.",
};

export const OPERATOR_PENDING_STATE = {
  title: "Telemetry still processing.",
  subtitle: "Telemetry is present, but it is not ready for operator review yet.",
  detail: "Wait for processing to finish before reviewing issues.",
};

const DISALLOWED_REPLACEMENTS = [
  [/\brelationship divergence\b/gi, "system behavior changed from its normal pattern"],
  [/\breplay\/relationship evidence\b/gi, "historical comparison evidence"],
  [/\breplay relationship evidence\b/gi, "historical comparison evidence"],
  [/\brelationship evidence\b/gi, "supporting evidence"],
  [/\bstate group [a-z]\b/gi, "current operating pattern"],
  [/\bdeformation age\b/gi, "behavior duration"],
  [/\bobservation grammar\b/gi, "observation method"],
  [/\blatest_result\b/gi, "current observation"],
  [/\bupload_state\b/gi, "current analysis"],
  [/\bregime\b/gi, "operating pattern"],
  [/\btopology\b/gi, "relationship pattern"],
  [/\bdeformation\b/gi, "behavior change"],
  [/\bbaseline separation\b/gi, "change from the historical pattern"],
  [/\bstructural drift\b/gi, "system behavior change"],
];

export function deriveCanonicalFinding({ currentSession, latestReplayFrame = null }) {
  const result = currentSession?.latestUploadResult ?? null;
  const sii = result?.sii_intelligence ?? {};
  const replayTimeline = result?.replay_timeline?.timeline ?? sii?.replay_timeline?.timeline ?? [];
  const frame = latestReplayFrame ?? replayTimeline[replayTimeline.length - 1] ?? null;
  const jobId = resolveSessionJobId(currentSession);
  const hasTelemetry = hasFullUploadResult(result) || Boolean(frame) || currentSession?.hasRealSiiOutput;
  const statusLevel = classifyStatusLevel(result, frame);
  const confidence = normalizeConfidenceLabel(
    frame?.confidence
      ?? frame?.evidence_state?.confidence
      ?? sii?.confidence
      ?? result?.confidence
      ?? result?.operator_report?.confidence
      ?? result?.drift_metrics?.confidence
      ?? result?.data_quality?.confidence,
    result,
    frame,
  );
  const variables = readVariables(result);
  const evidenceSummary = readEvidenceSummary(result);
  const driftMagnitude = firstFiniteNumber(
    frame?.baseline_distance,
    frame?.topology_state?.drift_index,
    result?.drift_metrics?.baseline_distance,
    result?.drift_metrics?.drift_index,
    sii?.instability_index,
  );
  const duration = formatBehaviorDuration(
    frame?.timestamp_start
      ?? result?.deformation_started_at
      ?? result?.timestamp_profile?.first_timestamp
      ?? null,
  );
  const dataQuality = buildDataQualityGroups(result);
  const replayReferences = buildReplayReferences(result, frame);
  const reviewReady = currentSession?.hasReliableOperatorEvidence === true;
  const hasFinding = hasTelemetry && statusLevel !== "normal";

  if (hasTelemetry && !reviewReady) {
    const pendingState = buildPendingState(currentSession?.reviewReadiness);
    return {
      id: jobId ? `current-${jobId}` : "current-pending",
      runId: jobId,
      exists: false,
      status: "Processing",
      confidence: "Pending",
      summary: pendingState.title,
      whyItMatters: pendingState.subtitle,
      reviewNext: pendingState.detail,
      emptyState: pendingState,
      supportingEvidence: [],
      technicalDetails: [],
      dataQuality,
      evidenceButtonLabel: "View Evidence",
      affectedVariables: [],
      historicalComparison: pendingState.detail,
      replayReferences,
      sourceName: result?.filename ?? null,
    };
  }

  if (!hasFinding) {
    return {
      id: jobId ? `current-${jobId}` : "current-empty",
      runId: jobId,
      exists: false,
      status: "Normal",
      confidence,
      summary: OPERATOR_EMPTY_STATE.title,
      whyItMatters: OPERATOR_EMPTY_STATE.subtitle,
      reviewNext: "Check data quality, then continue monitoring.",
      emptyState: OPERATOR_EMPTY_STATE,
      supportingEvidence: [],
      technicalDetails: [],
      dataQuality,
      evidenceButtonLabel: "View Evidence",
      affectedVariables: [],
      historicalComparison: "No equipment issues detected.",
      replayReferences,
      sourceName: result?.filename ?? null,
    };
  }

  const summary = buildObservationSummary({ result, frame, variables, evidenceSummary });
  const whyItMatters = buildWhyItMatters({ result, frame, variables });
  const reviewNext = buildReviewNext({ result, frame, variables });
  const supportingEvidence = buildSupportingEvidence({ result, frame, evidenceSummary, variables, driftMagnitude, duration });
  const technicalDetails = buildTechnicalDetails({
    result,
    frame,
    variables,
    driftMagnitude,
    duration,
    replayReferences,
    evidenceCount: supportingEvidence.length,
  });

  return {
    id: jobId ? `current-${jobId}` : "current-observation",
    runId: jobId,
    exists: true,
    status: statusLevel === "critical" ? "High" : "Medium",
    confidence,
    summary,
    whyItMatters,
    reviewNext,
    emptyState: OPERATOR_EMPTY_STATE,
    supportingEvidence,
    technicalDetails,
    dataQuality,
    evidenceButtonLabel: "View Evidence",
    affectedVariables: variables,
    historicalComparison: sanitizeOperatorText(
      result?.historical_comparison
        ?? result?.historical_fact
        ?? result?.relationship_summary
        ?? "Historical comparison evidence supports a change from the normal pattern.",
    ),
    replayReferences,
    sourceName: result?.filename ?? null,
  };
}

export function buildCanonicalFindingRun({ canonicalFinding, currentSession }) {
  if (!canonicalFinding?.exists || currentSession?.hasReliableOperatorEvidence !== true) return null;
  const result = currentSession?.latestUploadResult ?? null;
  const runId = canonicalFinding.runId ?? resolveSessionJobId(currentSession) ?? "current-observation";
  const evidenceSummary = Array.isArray(canonicalFinding.supportingEvidence) && canonicalFinding.supportingEvidence.length > 0
    ? canonicalFinding.supportingEvidence
    : [canonicalFinding.summary];
  const confidence = normalizeOperatorConfidenceLabel(canonicalFinding.confidence);

  return {
    run_id: runId,
    source_name: canonicalFinding.sourceName ?? result?.filename ?? "Current telemetry",
    source_type: "current_session",
    observation_type: result?.observation_type ?? "trajectory_drift",
    observation_status: "open",
    status: "complete",
    structural_state: canonicalFinding.status,
    operating_state: canonicalFinding.status,
    evidence_summary: evidenceSummary,
    historical_fact: canonicalFinding.historicalComparison ?? "Historical comparison evidence supports a change from the normal pattern.",
    potential_impact: canonicalFinding.whyItMatters,
    operator_impact: canonicalFinding.whyItMatters,
    variables: canonicalFinding.affectedVariables ?? [],
    confidence,
    evidence_confidence: confidence,
    created_at: result?.completed_at ?? result?.last_processed_at ?? result?.processing_trace?.completed_at ?? result?.timestamp_profile?.last_timestamp ?? null,
    deformation_started_at: result?.deformation_started_at ?? result?.timestamp_profile?.first_timestamp ?? null,
    regime_label: result?.sii_intelligence?.baseline_regime ?? result?.sii_intelligence?.regime_label ?? null,
    drift_metrics: {
      baseline_distance: firstFiniteNumber(
        result?.drift_metrics?.baseline_distance,
        result?.drift_metrics?.drift_index,
        result?.sii_intelligence?.instability_index,
      ) ?? null,
      drift_index: firstFiniteNumber(
        result?.drift_metrics?.drift_index,
        result?.drift_metrics?.baseline_distance,
        result?.sii_intelligence?.instability_index,
      ) ?? null,
      confidence: confidence.toLowerCase(),
    },
    data_conditions: buildDataQualityGroups(result).missingRecentValues ?? [],
    technical_details: canonicalFinding.technicalDetails ?? [],
    replay_references: canonicalFinding.replayReferences ?? [],
    synthetic_current_run: true,
  };
}

export function sanitizeOperatorText(value) {
  let text = String(value ?? "").trim();
  for (const [pattern, replacement] of DISALLOWED_REPLACEMENTS) {
    text = text.replace(pattern, replacement);
  }
  return text.replace(/\s+/g, " ").trim();
}


export function sanitizeOperatorList(values) {
  if (!Array.isArray(values)) return [];
  return values.map((item) => sanitizeOperatorText(item)).filter(Boolean);
}

export function normalizeOperatorConfidenceLabel(value) {
  const normalized = String(value ?? "").toLowerCase().trim();
  if (!normalized) return "Low";
  if (normalized.includes("high") || normalized.includes("confirmed") || normalized.includes("strong")) return "High";
  if (normalized.includes("moderate") || normalized.includes("medium") || normalized.includes("present") || normalized.includes("reference")) return "Moderate";
  if (normalized.includes("low") || normalized.includes("weak") || normalized.includes("developing") || normalized.includes("monitoring") || normalized.includes("pending")) return "Low";
  return sanitizeOperatorText(value);
}

export function containsDisallowedOperatorTerms(value) {
  const text = String(value ?? "");
  return DISALLOWED_REPLACEMENTS.some(([pattern]) => pattern.test(text));
}

function classifyStatusLevel(result, frame) {
  const raw = [
    result?.operating_state,
    result?.drift_status,
    result?.sii_intelligence?.facility_state,
    result?.sii_intelligence?.urgency,
    frame?.cognition_state?.facility_state,
    frame?.topology_state?.stability_state,
  ].filter(Boolean).join(" ").toLowerCase();
  const magnitude = firstFiniteNumber(
    frame?.baseline_distance,
    frame?.topology_state?.drift_index,
    result?.drift_metrics?.baseline_distance,
    result?.drift_metrics?.drift_index,
    result?.sii_intelligence?.instability_index,
  ) ?? 0;

  if (/(critical|alert|unstable|fragment|needs action)/.test(raw) || magnitude >= 0.82) return "critical";
  if (/(drift|change|review|watch|degrad|diverg|elevated)/.test(raw) || magnitude >= 0.24) return "change";
  return "normal";
}

function normalizeConfidenceLabel(value, result, frame) {
  const numeric = Number(value);
  if (Number.isFinite(numeric)) {
    const normalized = numeric > 1 ? numeric / 100 : numeric;
    if (normalized >= 0.82) return "High";
    if (normalized >= 0.62) return "Moderate";
    return "Low";
  }

  const raw = String(value ?? "").toLowerCase();
  if (/(high|confirmed|strong)/.test(raw)) return "High";
  if (/(moderate|medium|likely|present)/.test(raw)) return "Moderate";
  if (/(low|developing|weak|emerging|monitoring|pending)/.test(raw)) return "Low";

  const magnitude = firstFiniteNumber(
    frame?.baseline_distance,
    frame?.topology_state?.drift_index,
    result?.drift_metrics?.baseline_distance,
    result?.drift_metrics?.drift_index,
  );
  if ((magnitude ?? 0) >= 0.82) return "High";
  if ((magnitude ?? 0) >= 0.24) return "Moderate";
  return "Low";
}

function readVariables(result) {
  return (result?.operator_report?.affected_variables ?? result?.variables ?? [])
    .filter(Boolean)
    .map((item) => String(item).trim())
    .filter(Boolean)
    .slice(0, 6);
}

function readEvidenceSummary(result) {
  return (result?.operator_report?.evidence_summary ?? result?.evidence_summary ?? [])
    .filter(Boolean)
    .map((item) => sanitizeOperatorText(item))
    .slice(0, 5);
}

function buildObservationSummary({ result, frame, variables, evidenceSummary }) {
  const type = String(result?.observation_type ?? result?.operator_report?.observation_type ?? "").toLowerCase();
  if ((type.includes("coupling") || type.includes("covariance")) && variables.length >= 2) {
    return `The relationship between ${variables[0]} and ${variables[1]} changed from its historical pattern.`;
  }
  if (type.includes("recovery")) {
    return "Recovery behavior differs from previous observations.";
  }
  if (type.includes("trajectory") || type.includes("drift")) {
    return "System behavior has moved away from its historical operating pattern.";
  }
  const raw = sanitizeOperatorText(
    frame?.why_summary
      ?? result?.relationship_summary
      ?? result?.sii_intelligence?.why_summary
      ?? evidenceSummary[0]
      ?? "",
  );
  return raw || "System behavior changed from its normal pattern.";
}

function buildWhyItMatters({ result, frame, variables }) {
  const type = String(result?.observation_type ?? "").toLowerCase();
  const raw = sanitizeOperatorText(
    result?.potential_impact
      ?? result?.impact_summary
      ?? result?.operator_report?.why_it_matters
      ?? frame?.relationship_summary
      ?? "",
  );
  if (raw) return raw;
  if ((type.includes("coupling") || type.includes("covariance")) && variables.length >= 2) {
    return "The observed relationships between system variables have changed.";
  }
  if (type.includes("recovery")) {
    return "This indicates the operating pattern differs from historical evidence.";
  }
  return "Historical comparison evidence indicates a change from the normal operating pattern.";
}

function buildReviewNext({ result, frame, variables }) {
  const raw = sanitizeOperatorText(
    result?.operator_report?.review_next
      ?? frame?.topology_state?.primary_driver
      ?? "",
  ).toLowerCase();
  if (raw.includes("histor")) return "Review historical comparison evidence.";
  if (variables.length >= 2) return "Review affected variables.";
  if (raw.includes("replay")) return "Review replay evidence.";
  return "Review supporting evidence.";
}

function buildSupportingEvidence({ result, frame, evidenceSummary, variables, driftMagnitude, duration }) {
  const items = [...evidenceSummary];
  if (variables.length > 0) items.push(`Affected variables: ${variables.join(", ")}.`);
  if (Number.isFinite(driftMagnitude)) items.push(`Drift magnitude: ${driftMagnitude.toFixed(2)}.`);
  if (duration !== "-") items.push(`Behavior has persisted for ${duration}.`);
  const frameSummary = sanitizeOperatorText(frame?.relationship_summary ?? frame?.evidence_state?.summary ?? "");
  if (frameSummary) items.push(frameSummary);
  return [...new Set(items)].slice(0, 6);
}

function buildTechnicalDetails({ result, frame, variables, driftMagnitude, duration, replayReferences, evidenceCount }) {
  return [
    { label: "Drift magnitude", value: Number.isFinite(driftMagnitude) ? driftMagnitude.toFixed(2) : "-" },
    { label: "Behavior duration", value: duration },
    { label: "Affected variables", value: variables.length ? variables.join(", ") : "-" },
    { label: "Historical comparison", value: sanitizeOperatorText(result?.relationship_summary ?? result?.historical_fact ?? "Available in supporting evidence") },
    { label: "Evidence count", value: String(evidenceCount || 0) },
    { label: "Replay references", value: replayReferences.length ? replayReferences.join("; ") : "-" },
    { label: "Current operating pattern", value: sanitizeOperatorText(result?.regime_label ?? result?.sii_intelligence?.regime_label ?? "Historical pattern") },
    { label: "Current analysis", value: sanitizeOperatorText(result?.processing_state ?? result?.status ?? "Complete") },
    { label: "Observation method", value: "Structural change only. No recommendations." },
    { label: "Source", value: result?.filename ?? "-" },
    { label: "Run ID", value: result?.job_id ?? "-" },
    { label: "Observed at", value: sanitizeOperatorText(frame?.timestamp_end ?? result?.completed_at ?? result?.last_processed_at ?? "-") },
  ];
}

function buildDataQualityGroups(result) {
  const warnings = [
    ...(Array.isArray(result?.data_quality?.warnings) ? result.data_quality.warnings : []),
    ...(Array.isArray(result?.timestamp_profile?.warnings) ? result.timestamp_profile.warnings : []),
    ...(Array.isArray(result?.data_conditions) ? result.data_conditions : []),
  ].map((item) => sanitizeOperatorText(item)).filter(Boolean);

  const missingBaselineValues = warnings.filter((item) => /baseline|reference/.test(item.toLowerCase()));
  const missingRecentValues = warnings.filter((item) => /recent|current|latest|missing/.test(item.toLowerCase()) && !missingBaselineValues.includes(item));
  const unavailableTelemetry = warnings.filter((item) => /telemetry|timestamp|stale|unavailable|sparse|coverage/.test(item.toLowerCase()) && !missingBaselineValues.includes(item) && !missingRecentValues.includes(item));

  return {
    missingBaselineValues,
    missingRecentValues,
    unavailableTelemetry,
  };
}

export function buildPendingState(reviewReadiness) {
  if (reviewReadiness === "processing") {
    return {
      title: "Telemetry still processing.",
      subtitle: "Telemetry is still being processed into an evidence-backed interpretation.",
      detail: "Wait for processing to complete before reviewing findings.",
    };
  }
  if (reviewReadiness === "quality_gate") {
    return {
      title: "Telemetry still processing.",
      subtitle: "The current telemetry does not yet meet the reliability threshold for operator review.",
      detail: "Upload more stable telemetry or correct data quality issues before reviewing findings.",
    };
  }
  if (reviewReadiness === "unaligned") {
    return {
      title: "Telemetry still processing.",
      subtitle: "The latest interpretation is not aligned to the active upload session.",
      detail: "Refresh telemetry and wait for the evidence packet to realign before reviewing findings.",
    };
  }
  return OPERATOR_PENDING_STATE;
}

function buildReplayReferences(result, frame) {
  const refs = [];
  if (result?.job_id) refs.push(`Run ${result.job_id}`);
  if (frame?.frame_number != null) refs.push(`Frame ${frame.frame_number}`);
  if (frame?.timestamp_end ?? frame?.timestamp) refs.push(String(frame?.timestamp_end ?? frame?.timestamp));
  return refs;
}

function firstFiniteNumber(...values) {
  for (const value of values) {
    const numeric = Number(value);
    if (Number.isFinite(numeric)) return numeric;
  }
  return null;
}

function formatBehaviorDuration(value) {
  if (!value) return "-";
  const ms = Date.now() - new Date(value).getTime();
  if (!Number.isFinite(ms) || ms < 0) return "-";
  const hours = Math.round(ms / 3600000);
  if (hours < 24) return `${hours} hours`;
  return `${Math.round(hours / 24)} days`;
}
