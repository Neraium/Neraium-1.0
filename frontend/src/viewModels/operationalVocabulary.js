export const OPERATIONAL_VOCABULARY = {
  neutral: {
    awaitingTelemetry: "Awaiting telemetry",
    baselinePending: "Baseline pending",
    standby: "Standby",
    noActiveAnalysis: "No Active Structural Analysis",
    noActiveTrajectory: "No Active Structural Trajectory",
    noActiveProgression: "No Active Progression Sequence",
    awaitingHistorianStream: "Awaiting historian stream",
  },
  monitoring: {
    monitoringActive: "Monitoring active",
    structuralTrackingActive: "Structural tracking active",
  },
  escalation: {
    driftEmerging: "Drift emerging",
    structuralInstabilityDetected: "Structural instability detected",
    relationshipDivergenceObserved: "Relationship divergence observed",
    crossSubsystemPropagationObserved: "Cross-subsystem propagation observed",
  },
  recovery: {
    structuralConvergenceObserved: "Structural convergence observed",
    recoveryStabilizationDetected: "Recovery stabilization detected",
  },
};

export const LIFECYCLE_RAIL_NEUTRAL = [
  { label: "Intake", status: "Pending" },
  { label: "Baseline", status: "Pending" },
  { label: "Monitoring", status: "Idle" },
  { label: "Drift", status: "None" },
  { label: "Review", status: "None" },
];
