export function buildFleetSummary(interventionItems, score, tone) {
  const unstable = interventionItems.filter((item) => item.tone === "unstable").length;
  const elevated = interventionItems.filter((item) => item.tone === "elevated").length;
  const review = interventionItems.filter((item) => item.tone === "review").length;

  return {
    score,
    tone,
    summary: unstable > 0
      ? `${unstable} room${unstable === 1 ? "" : "s"} need immediate attention right now.`
      : elevated > 0
        ? `${elevated} room${elevated === 1 ? "" : "s"} are shortening the current intervention horizon.`
        : "The facility remains inside a comfortable intervention horizon.",
    metrics: [
      { label: "Immediate", value: unstable || 0, tone: unstable > 0 ? "unstable" : "nominal" },
      { label: "Scheduled", value: elevated || 0, tone: elevated > 0 ? "elevated" : "nominal" },
      { label: "Review", value: review || 0, tone: review > 0 ? "review" : "nominal" },
      { label: "Rooms", value: interventionItems.length, tone: "info" },
    ],
  };
}

export function buildStructuralExplanation(item) {
  if (item?.likelyDriver) {
    return [
      `${item.likelyDriver} is being treated as the likely driver to check first.`,
      item.confidenceBasis ?? "Supporting evidence is being compared across room signals.",
      "Infrastructure does not fail suddenly. It moves.",
    ];
  }
  if (item?.tone === "unstable") {
    return [
      "Temperature recovery is decoupling from humidity stabilization.",
      "Environmental coupling is less consistent than the room's recent baseline.",
      "Room recovery behavior is compressing the intervention horizon.",
    ];
  }
  if (item?.tone === "elevated") {
    return [
      "Airflow response consistency weakened during active climate periods.",
      "Humidity recovery is becoming less stable after environmental transitions.",
      "Room recovery behavior is compressing the intervention horizon.",
    ];
  }
  if (item?.tone === "review") {
    return [
      "Drift is visible, but the room remains controllable.",
      "Transition stability should be watched through the next operating window.",
      "Environmental coupling remains mostly consistent.",
    ];
  }
  return [
    "Room temperature response remains within expected behavior.",
    "Environmental coupling remains stable.",
    "Cycle settling remains the current operating state.",
  ];
}

export function buildGuidanceForItem(item) {
  if (item?.guidance) {
    return item.guidance;
  }
  if (item?.driverAttribution) {
    return buildGuidanceFromAttribution(item.driverAttribution, item.tone);
  }
  if (item?.likelyDriver) {
    return buildGuidanceFromLikelyDriver(item.likelyDriver);
  }
  if (item?.label?.toLowerCase().includes("irrigation") || item?.status?.toLowerCase().includes("irrigation")) {
    return buildGuidanceFromCategory("irrigation_balance");
  }
  if (item?.tone === "unstable") {
    return buildGuidanceFromCategory("humidity_recovery");
  }
  if (item?.tone === "elevated") {
    return buildGuidanceFromCategory("airflow_response");
  }
  if (item?.tone === "review") {
    return buildGuidanceFromCategory("environmental_coupling");
  }
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
  return "Based on current room climate trend, sync recency, and baseline behavior.";
}

export function processingTraceLines(trace) {
  return [
    `sii_pipeline_ran=${Boolean(trace.sii_pipeline_ran)}`,
    `driver_attribution_ran=${Boolean(trace.driver_attribution_ran)}`,
    `engine_module=${trace.engine_module ?? "unknown"}`,
    `engine_version=${trace.engine_version ?? "unknown"}`,
    `rows_processed=${trace.rows_processed ?? 0}`,
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
    `rows_processed=${result.rows_processed ?? 0}`,
    `columns_used=${Array.isArray(result.columns_used) ? result.columns_used.length : 0}`,
    `sensor_vector_count=${result.sensor_vector_count ?? 0}`,
    `latest_regime=${result.latest_state?.regime ?? result.output_summary?.latest_regime ?? "unknown"}`,
    `same_exact_fd004_validation_runner=false`,
  ];
}

export function formatFacilityPlainState(tone, primaryRoom) {
  if (tone === "unstable") {
    return `${primaryRoom?.label ?? "One room"} needs action`;
  }
  if (tone === "elevated" || tone === "review") {
    return `${primaryRoom?.label ?? "One room"} has drift observed`;
  }
  return "Facility is stable";
}

export function formatScoreReadiness(score) {
  if (score >= 86) {
    return "Operating readiness is strong.";
  }
  if (score >= 72) {
    return "Operating readiness is good, with one room to watch.";
  }
  if (score >= 58) {
    return "Operating readiness is tightening.";
  }
  return "Operating readiness needs attention.";
}

export function formatRoomDecisionState(tone, index = 0) {
  if (tone === "unstable") {
    return "Decision window";
  }
  if (tone === "elevated" || tone === "review") {
    return decisionLabelFromTone(tone, index);
  }
  return "Fine";
}

export function formatConfidenceLabel(score) {
  if ((score ?? 0) >= 82) {
    return "High";
  }
  if ((score ?? 0) >= 68) {
    return "Medium";
  }
  return "Developing";
}

export function formatOperatorActionLabel(action) {
  if (action === "acknowledge") {
    return "Acknowledged";
  }
  if (action === "review") {
    return "Under review";
  }
  if (action === "taken") {
    return "Action taken";
  }
  if (action === "log") {
    return "Intervention logged";
  }
  return "Status updated";
}

export function formatOperationalLabel(tone) {
  if (tone === "nominal") {
    return "Nominal";
  }
  if (tone === "review") {
    return "Review";
  }
  if (tone === "elevated") {
    return "Elevated";
  }
  if (tone === "unstable") {
    return "Unstable";
  }
  return "Monitoring";
}

export function formatConnectorStatus(status) {
  const value = String(status ?? "not_configured").replace(/_/g, " ");
  return value.charAt(0).toUpperCase() + value.slice(1);
}

export function connectorStatusTone(status) {
  if (status === "ready") {
    return "nominal";
  }
  if (status === "degraded") {
    return "review";
  }
  if (status === "offline") {
    return "elevated";
  }
  return "muted";
}

function buildGuidanceFromAttribution(attribution, fallbackTone) {
  if (!attribution) {
    return buildGuidanceFromCategory(fallbackTone === "unstable" ? "humidity_recovery" : "environmental_coupling");
  }
  const category = attribution.driver_category === "humidity_control"
    ? "humidity_recovery"
    : attribution.driver_category === "hvac_instability"
      ? "thermal_consistency"
      : attribution.driver_category === "airflow_restriction"
        ? "airflow_response"
        : attribution.driver_category === "irrigation_timing"
          ? "irrigation_balance"
          : attribution.driver_category === "sensor_network"
            ? "telemetry_continuity"
            : "environmental_coupling";
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
  if (normalized.includes("humid") || normalized.includes("moisture")) {
    return buildGuidanceFromCategory("humidity_recovery");
  }
  if (normalized.includes("airflow") || normalized.includes("pressure")) {
    return buildGuidanceFromCategory("airflow_response");
  }
  if (normalized.includes("temperature") || normalized.includes("hvac") || normalized.includes("thermal")) {
    return buildGuidanceFromCategory("thermal_consistency");
  }
  if (normalized.includes("irrigation") || normalized.includes("feed")) {
    return buildGuidanceFromCategory("irrigation_balance");
  }
  return buildGuidanceFromCategory("environmental_coupling");
}

function buildGuidanceFromCategory(category) {
  const guidance = {
    humidity_recovery: {
      nextMove: "Review humidity recovery behavior",
      primaryDriver: "Humidity recovery is lagging behind recent room behavior.",
      whyFlagged: "Humidity recovery has remained slower than recent room behavior across recent monitoring windows.",
      whatToCheck: [
        "Review dehumidification response",
        "Check room moisture load",
        "Compare recent recovery time to normal room behavior",
      ],
    },
    airflow_response: {
      nextMove: "Inspect airflow response",
      primaryDriver: "Airflow response appears to be recovering slower than recent baseline.",
      whyFlagged: "Room recovery suggests airflow response is not matching recent environmental behavior.",
      whatToCheck: [
        "Inspect airflow path",
        "Check fan response consistency",
        "Review room exchange behavior",
      ],
    },
    thermal_consistency: {
      nextMove: "Review thermal consistency",
      primaryDriver: "Temperature recovery is no longer matching humidity stabilization.",
      whyFlagged: "Temperature and humidity are no longer recovering together the way this room normally does.",
      whatToCheck: [
        "Review temperature recovery",
        "Check cooling response stability",
        "Compare hot spots against recent room behavior",
      ],
    },
    irrigation_balance: {
      nextMove: "Check irrigation balance",
      primaryDriver: "Irrigation balance is changing during the recovery window.",
      whyFlagged: "Recovery behavior after feed events is shifting compared to recent room baseline.",
      whatToCheck: [
        "Review irrigation timing",
        "Check runoff or substrate response if available",
        "Compare recovery behavior after feed events",
      ],
    },
    environmental_coupling: {
      nextMove: "Review environmental coupling",
      primaryDriver: "Environmental coupling is becoming less consistent.",
      whyFlagged: "Temperature and humidity recovery appear less consistent across recent monitoring windows.",
      whatToCheck: [
        "Compare temperature and humidity recovery together",
        "Review room transition behavior",
        "Check whether recovery timing is moving earlier than normal",
      ],
    },
    room_pressure: {
      nextMove: "Inspect room pressure stability",
      primaryDriver: "Room pressure stability appears to be affecting recovery behavior.",
      whyFlagged: "Room behavior is moving earlier than its recent operating baseline.",
      whatToCheck: [
        "Inspect room pressure stability",
        "Review door and room sealing behavior",
        "Compare room exchange behavior to recent baseline",
      ],
    },
    telemetry_continuity: {
      nextMove: "Review telemetry continuity",
      primaryDriver: "Telemetry coverage is limiting confidence in the current room explanation.",
      whyFlagged: "Connected signals suggest more room coverage is needed before confidence tightens.",
      whatToCheck: [
        "Confirm room telemetry coverage",
        "Review missing or stale readings",
        "Compare connected signals against expected room sources",
      ],
    },
    stable_monitoring: {
      nextMove: "Continue monitoring",
      primaryDriver: "Environmental coupling remains consistent compared to recent baseline.",
      whyFlagged: "Room behavior remains visible and controllable across recent monitoring windows.",
      whatToCheck: [
        "Continue routine room walk",
        "Watch recovery timing after the next transition",
        "Review changes only if the window shortens",
      ],
    },
  };
  return guidance[category] ?? guidance.environmental_coupling;
}

function isGenericOperatorMove(move) {
  const normalized = move.toLowerCase();
  return normalized.includes("stabilize environment")
    || normalized.includes("needs review")
    || normalized.includes("check room")
    || normalized.includes("fix environment")
    || normalized.includes("optimize conditions")
    || normalized.includes("adjust before next cycle");
}

function decisionLabelFromTone(tone, index = 0) {
  if (tone === "unstable") {
    return "Decision window";
  }
  if (tone === "elevated") {
    return index % 2 === 0 ? "Airflow response" : "Coupling review";
  }
  if (tone === "review") {
    return index % 2 === 0 ? "Drift observed" : "Transition watch";
  }
  return "Stable";
}

function humanizeDriverCategory(value) {
  if (!value) {
    return "Environmental Coupling Shift";
  }
  return value
    .split("_")
    .map((token) => token.charAt(0).toUpperCase() + token.slice(1))
    .join(" ");
}

function translateEvidenceLine(value, fallbackCategory = "environmental_coupling") {
  if (!value) {
    return buildGuidanceFromCategory(fallbackCategory).whyFlagged;
  }
  if (!isTechnicalEvidenceText(value)) {
    return value;
  }

  const guidance = buildGuidanceFromCategory(fallbackCategory);
  if (value.includes("humidity recovery")) {
    return guidance.whyFlagged;
  }
  if (value.includes("telemetry") || value.includes("coverage")) {
    return "Telemetry coverage is limiting structural confidence in the current explanation.";
  }
  if (value.includes("temperature") || value.includes("cooling")) {
    return "Temperature recovery is no longer tracking the room's normal stabilization pattern.";
  }
  if (value.includes("airflow")) {
    return "Airflow response is lagging against the room's recent operating pattern.";
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
    || normalized.includes("confidence_basis");
}
