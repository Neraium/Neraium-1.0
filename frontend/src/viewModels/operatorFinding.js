import { resolveSessionJobId } from "./currentSession";
import { hasFullUploadResult } from "./uploadState";

export const OPERATOR_EMPTY_STATE = {
  title: "No active insights.",
  subtitle: "The latest analysis found no behavior that requires operator review.",
  detail: "Review data quality or import a newer dataset when conditions change.",
};

export const OPERATOR_PENDING_STATE = {
  title: "Insights are not ready.",
  subtitle: "Telemetry is present, but it is not ready for operator review yet.",
  detail: "Wait for the analysis to finish, then review the insights.",
};

const DISALLOWED_REPLACEMENTS = [
  [/\brelationship missing\b/gi, "no longer followed its historical operating pattern"],
  [/\bcorrelation delta\b/gi, "operating pattern change"],
  [/\brelationship strength\b/gi, "operating coupling"],
  [/\boperational support\b/gi, "supporting operating evidence"],
  [/\bconfidence persistence\b/gi, "consistent recent behavior"],
  [/\bbaseline score\b/gi, "baseline comparison"],
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
  [/\bbackend\b/gi, "analysis service"],
  [/\bpipeline\b/gi, "analysis workflow"],
  [/\breplay\b/gi, "historical review"],
  [/\braw\b/gi, "source"],
  [/\bdebug\b/gi, "diagnostic"],
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
      evidenceButtonLabel: "Review Evidence",
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
      evidenceButtonLabel: "Review Evidence",
      affectedVariables: [],
      historicalComparison: "No behavior requiring operator review was detected.",
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
    status: statusLevel === "critical" ? "Critical" : "High",
    confidence,
    summary,
    whyItMatters,
    reviewNext,
    emptyState: OPERATOR_EMPTY_STATE,
    supportingEvidence,
    technicalDetails,
    dataQuality,
    evidenceButtonLabel: "Review Evidence",
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
    source_name: canonicalFinding.sourceName ?? result?.filename ?? "Current telemetry session",
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
  return text
    .replace(/\b(The)\s+\1\b/gi, "$1")
    .replace(/\.\s+(has|have|had|is|are|was|were)\b/g, " $1")
    .replace(/\s+([,.!?;:])/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
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
  if (raw.includes("replay")) return "Review supporting evidence.";
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
    { label: "Behavior evidence references", value: replayReferences.length ? replayReferences.join("; ") : "-" },
    { label: "Current operating pattern", value: sanitizeOperatorText(result?.regime_label ?? result?.sii_intelligence?.regime_label ?? "Historical pattern") },
    { label: "Current analysis", value: sanitizeOperatorText(result?.processing_state ?? result?.status ?? "Complete") },
    { label: "Observation method", value: "System behavior change only. No automatic control." },
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
      title: "Insights are not ready.",
      subtitle: "Telemetry is still being processed into an evidence-backed interpretation.",
      detail: "Wait for the analysis to complete, then review the insights.",
    };
  }
  if (reviewReadiness === "quality_gate") {
    return {
      title: "Insights are not ready.",
      subtitle: "The current telemetry does not yet meet the reliability requirements for operator review.",
      detail: "Import a more complete dataset or correct the data-quality warnings, then run the analysis again.",
    };
  }
  if (reviewReadiness === "unaligned") {
    return {
      title: "Insights are not ready.",
      subtitle: "The latest result does not match the active analysis.",
      detail: "Refresh the page. If the result still does not match, run the analysis again.",
    };
  }
  return OPERATOR_PENDING_STATE;
}

function buildReplayReferences(result, frame) {
  const refs = [];
  if (result?.job_id) refs.push(`Analysis ${result.job_id}`);
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


export const FINDING_CLASSIFICATIONS = Object.freeze({
  known_operational_change: {
    label: "Known operational change",
    tone: "known",
    priority: "Informational review",
    meaning: "A directly observed operating-context change coincided with the relationship shift; causality is not established.",
  },
  context_limited_relationship_change: {
    label: "Context-limited relationship change",
    tone: "context",
    priority: "Context review",
    meaning: "The relationship changed, but recent operating conditions differ too much from the learned baseline to determine why.",
  },
  possible_instrumentation_issue: {
    label: "Possible instrumentation issue",
    tone: "instrumentation",
    priority: "Verify instrumentation",
    meaning: "Verify sensor or telemetry quality before treating the finding as a physical-system change.",
  },
  unexplained_systemic_change: {
    label: "Unexplained systemic change",
    tone: "systemic",
    priority: "Engineering review",
    meaning: "A persistent relationship change remains during comparable operating conditions and is not explained by available context.",
  },
  observed_change_under_review: {
    label: "Observed change under review",
    tone: "context",
    priority: "Monitoring review",
    meaning: "The baseline/current comparison supports a measured change, while persistence and attribution remain under review.",
  },
  insufficient_evidence: {
    label: "Insufficient evidence",
    tone: "insufficient",
    priority: "Evidence review",
    meaning: "The evidence is not strong enough for a reliable interpretation.",
  },
});

const GUIDANCE_CATEGORIES = new Set([
  "instrumentation",
  "controls",
  "operating_context",
  "physical_system",
  "data_quality",
  "documentation",
]);

const TIMELINE_EVENT_TYPES = new Set([
  "baseline_reference",
  "first_detectable_deviation",
  "persistence_supported",
  "persistence_threshold",
  "operating_mode_event",
  "sensor_health_warning",
  "analysis_window",
  "condition_evidence_window",
  "evidence_trend_classified",
  "finding_generated",
]);

const LEGACY_CLASSIFICATION_EXPLANATION = "This historical finding was generated before contextual classification was available.";

export function normalizeFindingPresentation(finding = {}) {
  const rawClassification = objectValue(finding.classification);
  const type = Object.hasOwn(FINDING_CLASSIFICATIONS, rawClassification.type)
    ? rawClassification.type
    : "insufficient_evidence";
  const meta = FINDING_CLASSIFICATIONS[type];
  const legacy = !rawClassification.type || !Object.hasOwn(FINDING_CLASSIFICATIONS, rawClassification.type);
  const rawDataConfidence = objectValue(finding.dataConfidence ?? finding.data_confidence);
  const rawOperatingMode = objectValue(finding.operatingMode ?? finding.operating_mode);
  const rawPersistence = objectValue(finding.persistence);
  const sensorHealth = listValue(finding.sensorHealth ?? finding.sensor_health)
    .filter((item) => item && typeof item === "object")
    .map((item) => ({
      signal: presentationText(item.signal) || "Unidentified signal",
      health: presentationText(item.health) || "unavailable",
      conditions: listValue(item.conditions).filter((condition) => condition && typeof condition === "object").map((condition) => ({
        type: presentationText(condition.type) || "unavailable",
        severity: presentationText(condition.severity) || "unavailable",
        evidence: presentationText(condition.evidence),
      })),
    }));
  const reasons = uniquePresentationText(rawClassification.reasons);
  const alternatives = uniquePresentationText(
    finding.alternativeExplanations
      ?? finding.alternative_explanations
      ?? rawClassification.alternative_explanations,
  );
  const certaintyLimit = presentationText(
    finding.certaintyLimit
      ?? finding.certainty_limit
      ?? rawClassification.certainty_limit,
  ) || (legacy
    ? LEGACY_CLASSIFICATION_EXPLANATION
    : "This classification is bounded by the evidence recorded in the current analysis.");
  const dataRating = normalizeEvidenceLabel(rawDataConfidence.rating, "Unavailable");
  const modeMatch = normalizeModeMatch(rawOperatingMode.match);
  const persistence = normalizePersistence(rawPersistence);
  const classificationConfidence = legacy
    ? "Unavailable"
    : normalizeEvidenceLabel(rawClassification.confidence, "Unavailable");
  const dataLimitations = uniquePresentationText([
    ...listValue(finding.dataLimitations ?? finding.data_limitations),
    ...listValue(rawDataConfidence.reasons),
    ...listValue(finding.qualityWarnings ?? finding.quality_warnings),
  ]);

  return {
    type,
    label: meta.label,
    tone: meta.tone,
    meaning: legacy ? LEGACY_CLASSIFICATION_EXPLANATION : meta.meaning,
    reviewPriority: legacy ? "Historical evidence review" : meta.priority,
    classificationConfidence,
    reasons: reasons.length ? reasons : [legacy ? LEGACY_CLASSIFICATION_EXPLANATION : "No classification rationale was recorded."],
    alternativeExplanations: alternatives,
    certaintyLimit,
    legacy,
    dataConfidence: {
      rating: dataRating,
      summary: presentationText(rawDataConfidence.summary) || (legacy ? "Unavailable for this historical finding." : "No data-confidence summary was recorded."),
      reasons: uniquePresentationText(rawDataConfidence.reasons),
      affectedSignals: uniquePresentationText(rawDataConfidence.affected_signals ?? rawDataConfidence.affectedSignals),
    },
    operatingMode: {
      match: modeMatch,
      confidence: normalizeEvidenceLabel(rawOperatingMode.confidence, "Unavailable"),
      baseline: presentationText(rawOperatingMode.baseline_mode_label ?? rawOperatingMode.baselineModeLabel ?? rawOperatingMode.baseline_mode ?? rawOperatingMode.baselineMode) || "Unavailable",
      recent: presentationText(rawOperatingMode.recent_mode_label ?? rawOperatingMode.recentModeLabel ?? rawOperatingMode.recent_mode ?? rawOperatingMode.recentMode) || "Unavailable",
      differences: listValue(rawOperatingMode.differences).filter((item) => item && typeof item === "object").map((item) => ({
        feature: presentationText(item.feature) || "Operating context",
        reason: presentationText(item.reason),
      })),
      reasons: uniquePresentationText(rawOperatingMode.reasons),
    },
    persistence,
    sensorHealth,
    relationshipEvidence: objectValue(finding.relationshipEvidence ?? finding.relationship_evidence),
    investigationGuidance: normalizeInvestigationGuidance(finding, reasons, legacy),
    timeline: normalizeFindingTimeline(finding),
    dataLimitations,
  };
}

export function normalizeInvestigationGuidance(finding = {}, classificationReasons = [], legacy = false) {
  let raw = listValue(finding.investigationGuidance ?? finding.investigation_guidance);
  if (!raw.length) {
    raw = listValue(
      finding.recommendedInvestigation
        ?? finding.recommended_investigation
        ?? finding.recommendedChecksStructured
        ?? finding.recommended_checks,
    );
  }
  if (!raw.length) {
    raw = listValue(
      finding.recommendedFirstAction
        ?? finding.recommended_first_action
        ?? finding.recommendedAction
        ?? finding.recommended_action
        ?? finding.operatorCheck
        ?? finding.operator_check,
    );
  }
  const fallbackReason = presentationText(classificationReasons[0])
    || (legacy
      ? "This check was retained from the historical finding; supporting rationale was not recorded."
      : "This check is tied to the evidence available for the current finding.");
  const normalized = raw.map((item, index) => {
    const source = item && typeof item === "object" ? item : { check: item };
    const check = presentationText(source.check ?? source.recommendation ?? source.recommended_check);
    const category = GUIDANCE_CATEGORIES.has(source.category) ? source.category : "documentation";
    const rank = Number(source.rank);
    return {
      rank: Number.isFinite(rank) && rank > 0 ? rank : index + 1,
      check,
      reason: presentationText(source.reason) || fallbackReason,
      category,
      editable: source.editable !== false,
    };
  }).filter((item) => item.check);

  return normalized
    .sort((left, right) => left.rank - right.rank)
    .slice(0, 3)
    .map((item, index) => ({ ...item, rank: index + 1 }));
}

export function normalizeFindingTimeline(finding = {}) {
  const sourceRanges = [
    ...listValue(finding.sourceTimeRanges ?? finding.source_time_ranges),
    ...listValue(finding.evidence).flatMap((item) => listValue(item?.source_time_ranges ?? item?.sourceTimeRanges)),
  ].filter((item) => item && typeof item === "object");
  const rawEvents = listValue(finding.activityTimeline ?? finding.activity_timeline)
    .filter((item) => item && typeof item === "object")
    .map(normalizeTimelineEvent)
    .filter(Boolean);
  const events = [...rawEvents];
  const bounds = sourceRanges[0] ?? {};

  if (!events.some((item) => item.eventType === "baseline_reference")) {
    const baseline = timelineRangeEvent({
      eventType: "baseline_reference",
      title: "Baseline reference period",
      detail: "This recorded period supplied the learned relationship reference.",
      start: bounds.baseline_start ?? bounds.baselineStart,
      end: bounds.baseline_end ?? bounds.baselineEnd,
    });
    if (baseline) events.unshift(baseline);
  }
  if (!events.some((item) => ["analysis_window", "first_detectable_deviation"].includes(item.eventType))) {
    const current = timelineRangeEvent({
      eventType: "analysis_window",
      title: "Relationship comparison period",
      detail: "This is the recorded period evaluated against the learned reference.",
      start: bounds.current_start ?? bounds.currentStart ?? bounds.start,
      end: bounds.current_end ?? bounds.currentEnd ?? bounds.end,
    });
    if (current) events.push(current);
  }

  const firstDetectedAt = presentationText(finding.firstDetectedAt ?? finding.first_detected_at);
  if (firstDetectedAt && !events.some((item) => item.eventType === "first_detectable_deviation")) {
    events.push({
      eventType: "first_detectable_deviation",
      title: "First detectable deviation",
      detail: "The source finding records this as the first detectable change.",
      time: firstDetectedAt,
      start: "",
      end: "",
      periodLabel: "",
      precision: "source_timestamp",
    });
  }

  const generatedAt = presentationText(finding.generatedAt ?? finding.generated_at);
  if (generatedAt && !events.some((item) => item.eventType === "finding_generated")) {
    events.push({
      eventType: "finding_generated",
      title: "Finding generated",
      detail: "Neraium generated this evidence-bounded finding for human review.",
      time: generatedAt,
      start: "",
      end: "",
      periodLabel: "",
      precision: "source_timestamp",
    });
  }

  const seen = new Set();
  return events.filter((event) => {
    const key = [event.eventType, event.time, event.start, event.end, event.periodLabel, event.title].join("|").toLowerCase();
    if (seen.has(key)) return false;
    seen.add(key);
    return Boolean(event.time || event.start || event.end || event.periodLabel);
  });
}

function normalizeTimelineEvent(item) {
  const rawEventType = presentationText(item.event_type ?? item.eventType);
  const eventType = rawEventType === "trajectory_classified" ? "evidence_trend_classified" : rawEventType;
  const time = presentationText(item.time);
  const start = presentationText(item.start);
  const end = presentationText(item.end);
  let periodLabel = presentationText(item.period_label ?? item.periodLabel)
    || (!parseableDate(time) ? time : "");
  if (rawEventType === "trajectory_classified" && /^observed for\b/i.test(periodLabel) && !start && !end) {
    periodLabel = "";
  }
  const exactTime = parseableDate(time) ? time : "";
  if (!eventType && !time && !start && !end && !periodLabel) return null;
  const normalizedType = TIMELINE_EVENT_TYPES.has(eventType) ? eventType : "analysis_window";
  return {
    eventType: normalizedType,
    title: (presentationText(item.title) || "Recorded evidence event").replace(/^Trajectory:/i, "Evidence trend:"),
    detail: presentationText(item.detail),
    time: exactTime,
    start,
    end,
    periodLabel,
    precision: presentationText(item.precision) || (start && end ? "range" : exactTime ? "source_timestamp" : "period"),
  };
}

function timelineRangeEvent({ eventType, title, detail, start, end }) {
  const normalizedStart = presentationText(start);
  const normalizedEnd = presentationText(end);
  if (!normalizedStart && !normalizedEnd) return null;
  return {
    eventType,
    title,
    detail,
    time: "",
    start: normalizedStart,
    end: normalizedEnd,
    periodLabel: "",
    precision: normalizedStart && normalizedEnd ? "range" : "boundary",
  };
}

function normalizePersistence(value) {
  const status = presentationText(value.status).toLowerCase();
  const persistent = value.persistent === true || ["persistent", "confirmed", "sustained"].includes(status);
  let label = "Unavailable";
  if (persistent) label = "Persistent";
  else if (status === "observing") label = "Observing";
  else if (status === "not_assessed") label = "Not assessed";
  else if (status === "not_persistent") label = "Not persistent";
  else if (status === "intermittent") label = "Intermittent";
  else if (status === "no_longer_observed") label = "No longer observed";
  else if (["limited", "unconfirmed", "not_established"].includes(status) || value.persistent === false) label = "Not established";
  return {
    status: status || "unavailable",
    persistent,
    duration: "",
    label,
    summary: presentationText(value.summary ?? value.reason) || (persistent ? "Persistence is supported by the current evidence." : "Persistence evidence is unavailable or not established."),
    reasons: uniquePresentationText(value.reasons),
  };
}

function normalizeModeMatch(value) {
  const normalized = presentationText(value).toLowerCase();
  if (normalized === "strong") return "Strong";
  if (normalized === "partial") return "Partial";
  if (normalized === "weak") return "Weak";
  return "Unavailable";
}

function normalizeEvidenceLabel(value, fallback) {
  const normalized = presentationText(value).replace(/_/g, " ").toLowerCase();
  if (!normalized) return fallback;
  return normalized.replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function uniquePresentationText(values) {
  return [...new Set(listValue(values).map(presentationText).filter(Boolean))];
}

function presentationText(value) {
  if (value === null || value === undefined) return "";
  if (["string", "number", "boolean"].includes(typeof value)) return String(value).trim();
  if (typeof value === "object") return presentationText(value.summary ?? value.description ?? value.reason ?? value.label);
  return "";
}

function listValue(value) {
  if (Array.isArray(value)) return value;
  if (value === null || value === undefined || value === "") return [];
  return [value];
}

function objectValue(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function parseableDate(value) {
  if (!value) return false;
  return !Number.isNaN(new Date(value).getTime());
}
