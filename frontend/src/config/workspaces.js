export const WORKSPACES = [
  {
    id: "system-body",
    label: "Portfolio",
    eyebrow: "Engineering Triage",
    description: "Sites, structural stability, evidence quality, and bounded operational findings.",
  },
  {
    id: "data-connections",
    label: "Data Connections",
    eyebrow: "Telemetry",
    description: "Import telemetry datasets and configure supported read-only connectors.",
  },
  {
    id: "observation-center",
    label: "Investigations",
    eyebrow: "Reasoning",
    description: "Operational findings, relationship evidence, limitations, and investigation outcomes.",
  },
  {
    id: "system-story",
    label: "Trace Mode",
    eyebrow: "Audit",
    description: "Review the read-only computational lineage behind a bounded conclusion.",
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
    name: "Central Plant and Airside Systems",
    scope: "Thermal production, airside delivery, equipment staging, and load response.",
  },
  {
    name: "Aquatic Amenities and Water Features",
    scope: "Circulation, heat load, treatment response, and guest-facing water systems.",
  },
  {
    name: "Process Water and Pumping",
    scope: "Flow, pressure, treatment performance, pump energy, and process response.",
  },
  {
    name: "Heat Rejection Systems",
    scope: "Thermal rejection behavior, approach temperature, staging, and load response.",
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
    name: "Utility Distribution",
    scope: "Water, gas, electrical, and thermal utility distribution behavior across the facility.",
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
