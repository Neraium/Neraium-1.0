export const WORKSPACES = [
  {
    id: "system-body",
    label: "Structural State",
    eyebrow: "Operator View",
    description: "Primary infrastructure condition, escalation direction, and operational focus.",
  },
  {
    id: "data-connections",
    label: "Historian Setup",
    eyebrow: "Intake",
    description: "Configure read-only historian intake and upload pilot telemetry.",
  },
  {
    id: "historical-replay",
    label: "Infrastructure Diagnostics",
    eyebrow: "Technical",
    description: "Advanced replay internals, evidence lineage, topology, and diagnostic overlays.",
  },
  {
    id: "governance-admin",
    label: "Governance Admin",
    eyebrow: "Admin",
    description: "Internal Aletheia Gate custody records (PASS and NO_PASS EVP receipts).",
  },
  {
    id: "onboarding",
    label: "Set Up System",
    eyebrow: "Setup",
    description: "Guided onboarding from source selection to live monitoring.",
  },
];

export const FALLBACK_SYSTEMS = [
  {
    name: "HVAC",
    scope: "Room temperature control, equipment activity, and zone balancing.",
  },
  {
    name: "Humidity control",
    scope: "Dehumidification, humidification, and moisture stability.",
  },
  {
    name: "Airflow",
    scope: "Circulation, pressure movement, and room exchange behavior.",
  },
  {
    name: "Irrigation",
    scope: "Irrigation timing, cycle review, and environmental response context.",
  },
  {
    name: "Lighting",
    scope: "Photoperiod windows, fixture response, and environmental coupling.",
  },
  {
    name: "Sensor network",
    scope: "Room sensors, gateway exports, and telemetry continuity.",
  },
];

export const INTAKE_STAGES = [
  "Batch receipt",
  "Header and schema detection",
  "Timestamp and room context review",
  "SII engine processing",
  "Evidence and state write",
  "Complete",
];

export const REPORT_TEMPLATES = [
  "Room Climate Trend Summary",
  "System Coupling Review",
  "Grower Action Report",
];

export const DEFAULT_WORKSPACE_ID = "system-body";

export const PRIMARY_WORKSPACE_ORDER = WORKSPACES.map((workspace) => workspace.id);

export const EXPERT_WORKSPACE_IDS = new Set(["governance-admin"]);
