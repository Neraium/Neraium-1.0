export const WORKSPACES = [
  {
    id: "system-body",
    label: "Command Center",
    eyebrow: "Operational State",
    description: "Operational state overview, fingerprint status, system summary, and top insight.",
  },
  {
    id: "data-connections",
    label: "Data Sources",
    eyebrow: "Telemetry",
    description: "Connect telemetry sources and analyze historical operating data.",
  },
  {
    id: "observation-center",
    label: "Insights",
    eyebrow: "Review",
    description: "Prioritized operational insights, evidence, and recommended investigations.",
  },
  {
    id: "system-story",
    label: "Advanced",
    eyebrow: "Technical",
    description: "Raw identifiers, evidence objects, metadata, and diagnostics.",
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
    name: "HVAC and Central Plant",
    scope: "Chilled water, boiler, air handling, equipment staging, and load response.",
  },
  {
    name: "Pools, Spas, and Water Features",
    scope: "Feature circulation, heat load, chemistry response, and guest-facing water systems.",
  },
  {
    name: "Water Treatment and Pumping",
    scope: "Pump power, flow, pressure, treatment performance, and process response.",
  },
  {
    name: "Cooling Towers and Heat Rejection",
    scope: "Condenser water behavior, approach temperature, tower staging, and heat rejection.",
  },
  {
    name: "Building Automation",
    scope: "BMS points, control states, schedules, setpoints, and occupancy-driven response.",
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
