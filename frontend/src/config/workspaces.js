export const WORKSPACES = [
  {
    id: "system-body",
    label: "Command Center",
    eyebrow: "Operational State",
    description: "Facility state, behavior baseline, discovered systems, and highest-priority insight.",
  },
  {
    id: "data-connections",
    label: "Datasets & Connectors",
    eyebrow: "Telemetry",
    description: "Import telemetry datasets and configure supported read-only connectors.",
  },
  {
    id: "observation-center",
    label: "Insights",
    eyebrow: "Review",
    description: "Prioritized operational insights, evidence, and recommended investigations.",
  },
  {
    id: "system-story",
    label: "Analysis Details",
    eyebrow: "Analysis",
    description: "Review analysis history, evidence metadata, source details, and support diagnostics.",
  },
  {
    id: "help-changelog",
    label: "Help & Status",
    eyebrow: "Support",
    description: "Review product terminology, status meanings, service diagnostics, and product updates.",
  },
  {
    id: "governance-admin",
    label: "Administration",
    eyebrow: "Admin",
    description: "Manage user access, sessions, SII governance records, and analysis service status.",
  },
];

export const FALLBACK_SYSTEMS = [
  {
    name: "Operational Systems",
    scope: "Equipment groups, control subsystems, operating processes, and load response.",
  },
  {
    name: "Guest Infrastructure",
    scope: "Guest-facing systems, service availability, comfort, safety, and operating response.",
  },
  {
    name: "Utility Systems",
    scope: "Water, gas, electrical, thermal, fuel, and other utility distribution behavior.",
  },
  {
    name: "Mechanical Systems",
    scope: "Mechanical equipment groups, runtime behavior, staging, and service response.",
  },
  {
    name: "Building Control Systems",
    scope: "Control states, schedules, setpoints, occupancy signals, and facility response.",
  },
  {
    name: "Energy Infrastructure",
    scope: "Electrical load behavior, demand response, meter relationships, and generation assets.",
  },
  {
    name: "Environmental Systems",
    scope: "Water, air, waste, treatment, compliance, and environmental operating behavior.",
  },
];

export const INTAKE_STAGES = [
  "Telemetry received",
  "Variable and timestamp detection",
  "Historical comparison",
  "System behavior review",
  "Result write",
  "Complete",
];

export const REPORT_TEMPLATES = [
  "System Change Summary",
  "System Behavior Review",
  "Observation Feedback Record",
];

export const DEFAULT_WORKSPACE_ID = "system-body";

export const PRIMARY_WORKSPACE_ORDER = WORKSPACES.map((workspace) => workspace.id);

export const EXPERT_WORKSPACE_IDS = new Set(["governance-admin", "system-story"]);
