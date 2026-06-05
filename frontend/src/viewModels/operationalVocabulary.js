export const OPERATIONAL_VOCABULARY = {
  neutral: {
    awaitingTelemetry: "Awaiting telemetry",
    baselinePending: "Baseline pending",
    standby: "Standby",
    noActiveAnalysis: "No Active Structural Analysis",
    noActiveTrajectory: "No Active Structural Trajectory",
    noActiveProgression: "No Active Progression Sequence",
    awaitingHistorianStream: "Awaiting telemetry stream",
  },
  monitoring: {
    monitoringActive: "Monitoring",
    structuralTrackingActive: "Persistence Under Evaluation",
  },
  escalation: {
    driftEmerging: "Emerging Drift",
    structuralInstabilityDetected: "Structural Instability",
    relationshipDivergenceObserved: "Divergence Observed",
    crossSubsystemPropagationObserved: "Drift Propagation",
  },
  recovery: {
    structuralConvergenceObserved: "Stability Recovery",
    recoveryStabilizationDetected: "Containment Stable",
  },
};

export const ESCALATION_LAYERS = [
  "Stable",
  "Monitoring",
  "Emerging Drift",
  "Persistent Drift",
  "Structural Instability",
  "Escalation Candidate",
  "Critical Escalation",
];

export const LIFECYCLE_RAIL_NEUTRAL = ESCALATION_LAYERS.map((label) => ({
  label,
  status: "Pending",
}));

export const LIFECYCLE_RAIL_ACTIVE_BASE = ESCALATION_LAYERS.map((label, index) => ({
  label,
  level: index + 1,
}));
