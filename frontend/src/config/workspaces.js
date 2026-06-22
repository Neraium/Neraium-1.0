export const WORKSPACES = [
  {
    id: "system-body",
    label: "Health",
    eyebrow: "System Health",
    description: "What changed, why it matters, and what to review next.",
  },
  {
    id: "data-connections",
    label: "Upload Data",
    eyebrow: "Telemetry",
    description: "Analyze a telemetry file and build the system story.",
  },
  {
    id: "system-story",
    label: "System Story",
    eyebrow: "Story",
    description: "Explain what happened, why we believe it, what likely caused it, and what to inspect next.",
  },
  {
    id: "observation-center",
    label: "Issues",
    eyebrow: "Review",
    description: "Review operational concerns, confidence, impact, and recommended checks.",
  },
  {
    id: "help-changelog",
    label: "Technical",
    eyebrow: "Support",
    description: "Review support notes and operator-facing review rules.",
  },
  {
    id: "governance-admin",
    label: "Technical Admin",
    eyebrow: "Admin",
    description: "Internal custody records and backend review details.",
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
  "Telemetry received",
  "Variable and timestamp detection",
  "Historical comparison",
  "System behavior review",
  "System story write",
  "Complete",
];

export const REPORT_TEMPLATES = [
  "System Change Summary",
  "System Behavior Review",
  "Observation Feedback Record",
];

export const DEFAULT_WORKSPACE_ID = "system-body";

export const PRIMARY_WORKSPACE_ORDER = WORKSPACES.map((workspace) => workspace.id);

export const EXPERT_WORKSPACE_IDS = new Set(["governance-admin"]);
