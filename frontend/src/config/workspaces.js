export const WORKSPACES = [
  {
    id: "system-body",
    label: "System Status",
    eyebrow: "Operator View",
    description: "Current system behavior, evidence confidence, and the next operator review step.",
  },
  {
    id: "data-connections",
    label: "Upload Data",
    eyebrow: "Intake",
    description: "Connect or upload multivariate telemetry with no domain-specific configuration.",
  },
  {
    id: "historical-replay",
    label: "Why It Changed",
    eyebrow: "Evidence",
    description: "Replay the before, change, and after moments behind a finding.",
  },
  {
    id: "observation-center",
    label: "Findings",
    eyebrow: "Evidence",
    description: "Review what changed, confidence, possible impact, and supporting evidence.",
  },
  {
    id: "help-changelog",
    label: "Help",
    eyebrow: "Trust",
    description: "Read the instrument boundary, version notes, and operator-facing review rules.",
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
    scope: "How the system returns to its usual behavior after a disturbance.",
  },
  {
    name: "Relationship Pattern Shift",
    scope: "Where variable relationships now behave differently than usual.",
  },
  {
    name: "Change Direction",
    scope: "Direction and strength of the observed behavior change.",
  },
  {
    name: "Persistence Window",
    scope: "How long the current structural change has remained active.",
  },
];

export const INTAKE_STAGES = [
  "Batch receipt",
  "Variable and timestamp detection",
  "Reference behavior learning",
  "System behavior review",
  "Observation and state write",
  "Complete",
];

export const REPORT_TEMPLATES = [
  "System Change Summary",
  "Relationship Shift Review",
  "Observation Feedback Record",
];

export const DEFAULT_WORKSPACE_ID = "system-body";

export const PRIMARY_WORKSPACE_ORDER = WORKSPACES.map((workspace) => workspace.id);

export const EXPERT_WORKSPACE_IDS = new Set(["governance-admin"]);
