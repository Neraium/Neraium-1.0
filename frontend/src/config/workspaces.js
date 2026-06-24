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
    name: "Source / Intake",
    scope: "Incoming supply, source availability, inlet pressure, and upstream demand conditions.",
  },
  {
    name: "Treatment",
    scope: "Treatment performance, chemistry, quality indicators, and process response.",
  },
  {
    name: "Pumping",
    scope: "Pump load, runtime, flow response, pressure response, and equipment behavior.",
  },
  {
    name: "Distribution",
    scope: "Distribution pressure, flow balance, downstream demand, and system recovery behavior.",
  },
  {
    name: "Storage / Level",
    scope: "Tank, reservoir, basin, or vessel level behavior and refill/recovery patterns.",
  },
  {
    name: "Thermal / Process Loop",
    scope: "Chilled water, cooling, process-loop response, delta-T, and load behavior where applicable.",
  },
  {
    name: "Telemetry Integrity",
    scope: "Signal completeness, timestamp quality, source availability, and confidence impact.",
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
