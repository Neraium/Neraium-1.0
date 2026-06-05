export const WORKSPACES = [
  {
    id: "system-body",
    label: "Structural State",
    eyebrow: "Operator View",
    description: "Current structural state, baseline alignment, and the highest-signal relational shift in the telemetry.",
  },
  {
    id: "data-connections",
    label: "Telemetry Intake",
    eyebrow: "Intake",
    description: "Connect or upload multivariate telemetry with no domain-specific configuration.",
  },
  {
    id: "historical-replay",
    label: "Structural Replay",
    eyebrow: "Technical",
    description: "Replay baseline drift, relationship changes, persistence, and evidence lineage over time.",
  },
  {
    id: "observation-center",
    label: "Observation Center",
    eyebrow: "Evidence",
    description: "Search structural observations, record operator findings, explore variable coupling, and export evidence records.",
  },
  {
    id: "governance-admin",
    label: "Governance Admin",
    eyebrow: "Admin",
    description: "Internal Aletheia Gate custody records (PASS and NO_PASS EVP receipts).",
  },
];

export const FALLBACK_SYSTEMS = [
  {
    name: "Relationship Cluster A",
    scope: "Variables that currently move together as one structural pattern.",
  },
  {
    name: "Relationship Cluster B",
    scope: "A second correlation cluster visible in the uploaded telemetry.",
  },
  {
    name: "Recovery Pattern",
    scope: "How the system returns toward baseline after perturbations.",
  },
  {
    name: "Covariance Shift",
    scope: "Where the current covariance structure differs from baseline.",
  },
  {
    name: "Trajectory Drift",
    scope: "Direction, velocity, and acceleration of state-space drift.",
  },
  {
    name: "Persistence Window",
    scope: "How long the current structural change has remained active.",
  },
];

export const INTAKE_STAGES = [
  "Batch receipt",
  "Variable and timestamp detection",
  "Baseline window profiling",
  "Structural drift analysis",
  "Observation and state write",
  "Complete",
];

export const REPORT_TEMPLATES = [
  "Structural Drift Summary",
  "Relationship Shift Review",
  "Observation Feedback Record",
];

export const DEFAULT_WORKSPACE_ID = "system-body";

export const PRIMARY_WORKSPACE_ORDER = WORKSPACES.map((workspace) => workspace.id);

export const EXPERT_WORKSPACE_IDS = new Set(["governance-admin"]);
