export const OPERATIONAL_VOCABULARY = {
  neutral: {
    awaitingTelemetry: "Awaiting telemetry",
    baselinePending: "Behavior baseline needed",
    standby: "Ready",
    noActiveAnalysis: "No active analysis",
    noActiveTrajectory: "No active behavior trajectory",
    noActiveProgression: "No active behavior sequence",
    awaitingHistorianStream: "Awaiting telemetry stream",
  },
  monitoring: {
    monitoringActive: "Monitoring",
    structuralTrackingActive: "Tracking sustained change",
  },
  escalation: {
    driftEmerging: "Emerging change",
    structuralInstabilityDetected: "Unstable behavior",
    relationshipDivergenceObserved: "Relationship change observed",
    crossSubsystemPropagationObserved: "Change spreading across systems",
  },
  recovery: {
    structuralConvergenceObserved: "Returning to stable behavior",
    recoveryStabilizationDetected: "Stable after intervention",
  },
};

export const ESCALATION_LAYERS = [
  "Stable",
  "Monitoring",
  "Change Emerging",
  "Persistent Change",
  "Unstable Behavior",
  "Sustained Behavior Change",
  "Widespread Behavior Change",
];

export const LIFECYCLE_RAIL_NEUTRAL = ESCALATION_LAYERS.map((label) => ({
  label,
  status: "Pending",
}));

export const LIFECYCLE_RAIL_ACTIVE_BASE = ESCALATION_LAYERS.map((label, index) => ({
  label,
  level: index + 1,
}));
