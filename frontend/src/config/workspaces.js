export const WORKSPACES = [
  {
    id: "system-body",
    label: "Structural State",
    eyebrow: "Operator View",
    description: "Primary infrastructure condition, detected data type, escalation direction, and operational focus.",
  },
  {
    id: "data-connections",
    label: "Telemetry Setup",
    eyebrow: "Intake",
    description: "Configure read-only telemetry intake and upload facility telemetry.",
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
];

export const FALLBACK_SYSTEMS = [
  {
    name: "Circulation",
    scope: "Hydraulic flow continuity, pump behavior, and pressure response.",
  },
  {
    name: "Filtration",
    scope: "Filter pressure, flow resistance, and cycle stability.",
  },
  {
    name: "Thermal control",
    scope: "Pool/spa thermal stability and heater response windows.",
  },
  {
    name: "Water chemistry",
    scope: "ORP/pH/feed coupling and chemistry behavior over time.",
  },
  {
    name: "Hydraulic routing",
    scope: "Valve path changes and distribution consistency.",
  },
  {
    name: "Operational context",
    scope: "Occupancy, ambient heat, and overnight stabilization context.",
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
