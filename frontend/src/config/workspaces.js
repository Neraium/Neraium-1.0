export const WORKSPACES = [
  {
    id: "system-body",
    label: "System Status",
    eyebrow: "Operator View",
    description: "What changed, why it matters, and what to review next.",
  },
  {
    id: "data-connections",
    label: "Upload Data",
    eyebrow: "Intake",
    description: "Upload telemetry and track processing.",
  },
  {
    id: "historical-replay",
    label: "Evidence Replay",
    eyebrow: "Evidence",
    description: "Review what changed, why it matters, and the supporting evidence.",
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
    name: "Commercial pools",
    scope: "Pool and spa chemistry, turnover, thermal stability, and load response.",
  },
  {
    name: "Resort water systems",
    scope: "Makeup water, level recovery, distribution pressure, and multi-asset demand behavior.",
  },
  {
    name: "Water treatment",
    scope: "ORP, pH, chlorine, turbidity, conductivity, and feed response.",
  },
  {
    name: "Chilled water loops",
    scope: "Supply/return temperature, delta-T, flow, differential pressure, and chiller load.",
  },
  {
    name: "Pumps and filtration",
    scope: "Pump load, runtime, filter pressure, hydraulic resistance, and low-flow signatures.",
  },
  {
    name: "Cooling towers",
    scope: "Future tower coverage for fan response, basin temperature, blowdown, and heat rejection drift.",
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
