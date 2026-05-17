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
  { label: "Intake", status: "-" },
  { label: "Baseline", status: "-" },
  { label: "Monitoring", status: "-" },
  { label: "Drift", status: "-" },
  { label: "Review", status: "-" },
];

export const LIFECYCLE_RAIL_ACTIVE = [
  { label: "Intake", status: "Ready" },
  { label: "Baseline", status: "Ready" },
  { label: "Monitoring", status: "Active" },
  { label: "Drift", status: "Review" },
  { label: "Review", status: "Needed" },
];
