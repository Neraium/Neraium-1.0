export function buildFleetSummary(interventionItems, score, tone) {
  const unstable = interventionItems.filter((item) => item.tone === "unstable").length;
  const elevated = interventionItems.filter((item) => item.tone === "elevated").length;
  const review = interventionItems.filter((item) => item.tone === "review").length;

  return {
    score,
    tone,
    summary: unstable > 0
      ? `${unstable} area${unstable === 1 ? "" : "s"} show a persistent change that warrants review.`
      : elevated > 0
        ? `${elevated} area${elevated === 1 ? "" : "s"} changed from usual behavior and should be watched closely.`
        : "The observed telemetry remains close to usual behavior.",
    metrics: [
      { label: "Immediate", value: unstable || 0, tone: unstable > 0 ? "unstable" : "nominal" },
      { label: "Watch", value: elevated || 0, tone: elevated > 0 ? "elevated" : "nominal" },
      { label: "Review", value: review || 0, tone: review > 0 ? "review" : "nominal" },
      { label: "Segments", value: interventionItems.length, tone: "info" },
    ],
  };
}

export function buildStructuralExplanation(item) {
  if (item?.likelyDriver) {
    return [
      `${item.likelyDriver} is the strongest available explanation at this time.`,
      item.confidenceBasis ?? "Supporting evidence is being compared across variable relationships.",
      "Neraium is describing a change, not assigning root cause.",
    ];
  }
  if (item?.tone === "unstable") {
    return [
      "Key variable relationships have changed materially.",
      "A subset of variables is changing in the same direction over time.",
      "Recovery behavior appears less stable than usual.",
    ];
  }
  if (item?.tone === "elevated") {
    return [
      "Variable relationships are weaker than usual.",
      "The current state trajectory is moving away from its normal operating envelope.",
      "Persistence should be watched through the next analysis window.",
    ];
  }
  if (item?.tone === "review") {
    return [
      "A change is visible, but it remains inside a reviewable range.",
      "The usual relationship pattern is still partially intact.",
      "Additional persistence would strengthen the observation.",
    ];
  }
  return [
    "The system remains inside its usual behavior pattern.",
    "Variable relationships are stable relative to recent history.",
    "No persistent behavior change is visible.",
  ];
}

export function buildGuidanceForItem(item) {
  if (item?.guidance) return item.guidance;
  if (item?.driverAttribution) return buildGuidanceFromAttribution(item.driverAttribution, item.tone);
  if (item?.likelyDriver) return buildGuidanceFromLikelyDriver(item.likelyDriver);
  if (item?.tone === "unstable") return buildGuidanceFromCategory("persistent_drift");
  if (item?.tone === "elevated") return buildGuidanceFromCategory("relationship_shift");
  if (item?.tone === "review") return buildGuidanceFromCategory("baseline_divergence");
  return buildGuidanceFromCategory("stable_monitoring");
}

export function buildConfidenceBasis(item, findings) {
  const drivers = item?.drivers ?? findings.map((entry) => entry.detail).slice(0, 3);
  if (drivers.length >= 2) {
    return `Based on ${drivers[0].toLowerCase()} and ${drivers[1].toLowerCase()}.`;
  }
  if (drivers.length === 1) {
    return `Based on ${drivers[0].toLowerCase()}.`;
  }
  return "Based on change strength, persistence, and relationship support.";
}

export function processingTraceLines(trace) {
  return [
    `sii_pipeline_ran=${Boolean(trace.sii_pipeline_ran)}`,
    `driver_attribution_ran=${Boolean(trace.driver_attribution_ran)}`,
    `engine_module=${trace.engine_module ?? "unknown"}`,
    `engine_version=${trace.engine_version ?? "unknown"}`,
    `rows_processed=${trace.rows_processed ?? 0}`,
    `sii_vector_rows_processed=${trace.sii_vector_rows_processed ?? trace.sensor_vector_count ?? 0}`,
    `sii_rows_excluded=${trace.sii_rows_excluded ?? 0}`,
    `columns_analyzed=${trace.columns_analyzed ?? 0}`,
    `evidence_count=${trace.evidence_count ?? 0}`,
    `git_commit=${trace.git_commit ?? "unknown"}`,
  ];
}

export function runnerTraceLines(result) {
  return [
    `runner_used=${Boolean(result.runner_used)}`,
    `runner_module=${result.runner_module ?? "unknown"}`,
    `core_engine=${result.core_engine ?? "unknown"}`,
    `sii_vector_rows_processed=${result.rows_processed ?? 0}`,
    `rows_received=${result.rows_received ?? result.rows_processed ?? 0}`,
    `rows_excluded=${result.rows_excluded ?? 0}`,
    `columns_used=${Array.isArray(result.columns_used) ? result.columns_used.length : 0}`,
    `sensor_vector_count=${result.sensor_vector_count ?? 0}`,
    `latest_regime=${result.latest_state?.regime ?? result.output_summary?.latest_regime ?? "unknown"}`,
    `same_exact_fd004_validation_runner=false`,
  ];
}

export function formatPlainState(tone, primarySegment) {
  const label = primarySegment?.label ?? "One segment";
  if (tone === "unstable") return `${label} shows a persistent behavior change`;
  if (tone === "elevated" || tone === "review") return `${label} changed from usual behavior`;
  return "Usual behavior";
}

export function formatScoreReadiness(score) {
  if (score >= 86) return "Structural stability is strong.";
  if (score >= 72) return "Structural stability is good, with one segment to watch.";
  if (score >= 58) return "Structural stability is tightening.";
  return "Structural stability needs review.";
}

export function formatSegmentDecisionState(tone, index = 0) {
  if (tone === "unstable") return "Immediate review window";
  if (tone === "elevated" || tone === "review") return decisionLabelFromTone(tone, index);
  return "Usual behavior";
}

export const formatFacilityPlainState = formatPlainState;
export const formatRoomDecisionState = formatSegmentDecisionState;

export function formatConfidenceLabel(score) {
  if ((score ?? 0) >= 82) return "High";
  if ((score ?? 0) >= 68) return "Medium";
  return "Developing";
}

export function formatOperatorActionLabel(action) {
  if (action === "acknowledge") return "Acknowledged";
  if (action === "review") return "Under review";
  if (action === "taken") return "Action taken";
  if (action === "log") return "Interpretation logged";
  return "Status updated";
}

export function formatOperationalLabel(tone) {
  if (tone === "nominal") return "Nominal";
  if (tone === "review") return "Review";
  if (tone === "elevated") return "Elevated";
  if (tone === "unstable") return "Unstable";
  return "Monitoring";
}

export function formatConnectorStatus(status) {
  const value = String(status ?? "not_configured").replace(/_/g, " ");
  return value.charAt(0).toUpperCase() + value.slice(1);
}

export function connectorStatusTone(status) {
  if (status === "ready") return "nominal";
  if (status === "degraded") return "review";
  if (status === "offline") return "elevated";
  return "muted";
}

function buildGuidanceFromAttribution(attribution, fallbackTone) {
  if (!attribution) {
    return buildGuidanceFromCategory(fallbackTone === "unstable" ? "persistent_drift" : "baseline_divergence");
  }
  const category = attribution.driver_category === "sensor_network"
    ? "telemetry_continuity"
    : attribution.driver_category === "structural_drift"
      ? "persistent_drift"
      : "relationship_shift";
  const guidance = buildGuidanceFromCategory(category);
  return {
    ...guidance,
    primaryDriver: humanizeDriverCategory(attribution.driver_category ?? category),
    whyFlagged: attribution.supporting_evidence?.[0]
      ? translateEvidenceLine(attribution.supporting_evidence[0], category)
      : guidance.whyFlagged,
    nextMove: attribution.next_operator_move && !isGenericOperatorMove(attribution.next_operator_move)
      ? attribution.next_operator_move
      : guidance.nextMove,
  };
}

function buildGuidanceFromLikelyDriver(likelyDriver) {
  const normalized = likelyDriver.toLowerCase();
  if (normalized.includes("telemetry") || normalized.includes("sensor")) {
    return buildGuidanceFromCategory("telemetry_continuity");
  }
  if (normalized.includes("coupling") || normalized.includes("relationship")) {
    return buildGuidanceFromCategory("relationship_shift");
  }
  if (normalized.includes("persistent") || normalized.includes("drift")) {
    return buildGuidanceFromCategory("persistent_drift");
  }
  return buildGuidanceFromCategory("baseline_divergence");
}

function buildGuidanceFromCategory(category) {
  const guidance = {
    persistent_drift: {
      nextMove: "Inspect the affected variable relationships",
      primaryDriver: "A persistent behavior change is visible across the active telemetry window.",
      whyFlagged: "The system changed from usual behavior and has not returned.",
      whatToCheck: [
        "Inspect the affected variables in context",
        "Check whether the shift reflects an operational change, sensor issue, or emerging fault",
        "Compare the current recovery path to usual behavior",
      ],
    },
    relationship_shift: {
      nextMove: "Review the coupling change",
      primaryDriver: "A relationship between key variables changed.",
      whyFlagged: "Variable relationships are weaker than usual.",
      whatToCheck: [
        "Compare before/after relationship strength",
        "Review the time window where the shift began",
        "Check whether the shift persists across subsequent windows",
      ],
    },
    baseline_divergence: {
      nextMove: "Watch the next analysis window",
      primaryDriver: "The current state is moving away from usual behavior.",
      whyFlagged: "The active state is no longer centered inside its usual pattern.",
      whatToCheck: [
        "Review change strength",
        "Watch change direction and persistence",
        "Confirm whether recovery remains normal after perturbations",
      ],
    },
    telemetry_continuity: {
      nextMove: "Review telemetry continuity",
      primaryDriver: "Telemetry coverage is limiting structural confidence in the current observation.",
      whyFlagged: "The observed shift may be data-quality related because the telemetry window is sparse or inconsistent.",
      whatToCheck: [
        "Confirm telemetry continuity for the affected variables",
        "Review missing, stale, or noisy readings",
        "Check whether the behavior change survives after filtering suspect data",
      ],
    },
    stable_monitoring: {
      nextMove: "Continue monitoring",
      primaryDriver: "Current variable relationships remain close to usual behavior.",
      whyFlagged: "No persistent behavior change is visible in the current telemetry window.",
      whatToCheck: [
        "Continue monitoring",
        "Watch the next perturbation and recovery cycle",
        "Review only if persistence or change strength increases",
      ],
    },
  };
  return guidance[category] ?? guidance.baseline_divergence;
}

function isGenericOperatorMove(move) {
  const normalized = move.toLowerCase();
  return normalized.includes("needs review")
    || normalized.includes("check segment")
    || normalized.includes("stabilize")
    || normalized.includes("optimize")
    || normalized.includes("monitor");
}

function decisionLabelFromTone(tone, index = 0) {
  if (tone === "unstable") return "Immediate review window";
  if (tone === "elevated") return index % 2 === 0 ? "Relationship shift" : "Persistence watch";
  if (tone === "review") return index % 2 === 0 ? "Pattern change" : "Transition watch";
  return "Usual behavior";
}

function humanizeDriverCategory(value) {
  if (!value) return "System Behavior Change";
  return value
    .split("_")
    .map((token) => token.charAt(0).toUpperCase() + token.slice(1))
    .join(" ");
}

function translateEvidenceLine(value, fallbackCategory = "baseline_divergence") {
  if (!value) return buildGuidanceFromCategory(fallbackCategory).whyFlagged;
  if (!isTechnicalEvidenceText(value)) return value;

  const guidance = buildGuidanceFromCategory(fallbackCategory);
  if (value.includes("telemetry") || value.includes("coverage")) {
    return "Telemetry coverage is limiting structural confidence in the current observation.";
  }
  if (value.includes("coupling") || value.includes("correlation")) {
    return "A variable-to-variable relationship has shifted away from baseline.";
  }
  if (value.includes("drift") || value.includes("baseline")) {
    return guidance.whyFlagged;
  }
  return guidance.whyFlagged;
}

function isTechnicalEvidenceText(value) {
  const normalized = String(value ?? "").toLowerCase();
  return normalized.includes("=")
    || normalized.includes("correlation")
    || normalized.includes("signal")
    || normalized.includes("drift")
    || normalized.includes("telemetry")
    || normalized.includes("confidence_basis")
    || normalized.includes("baseline");
}
