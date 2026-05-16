export const WORKSPACES = [
  {
    id: "cultivation-mission-control",
    label: "Cultivation Mission Control",
    eyebrow: "Cultivation Primary",
    description: "Canonical cultivation structural cognition interface for facility state, replay, pathways, and convergence.",
  },
  {
    id: "historical-replay",
    label: "Structural Replay",
    eyebrow: "Replay First",
    description: "Timeline scrub, propagation pathways, evidence by frame, and continuation windows.",
  },
  {
    id: "evidence-console",
    label: "Evidence Lineage",
    eyebrow: "Evidence First",
    description: "Inspect why structural cognition outputs are supported by subsystem and topology evidence.",
  },
  {
    id: "propagation-map",
    label: "Propagation Map",
    eyebrow: "Spread View",
    description: "Environmental topology spread view for room-to-room structural pathway propagation.",
  },
  {
    id: "data-connections",
    label: "Data Connections",
    eyebrow: "Signal Intake",
    description: "Upload telemetry files and manage the live intake endpoint.",
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

export const DEFAULT_WORKSPACE_ID = "cultivation-mission-control";

export const PRIMARY_WORKSPACE_ORDER = WORKSPACES.map((workspace) => workspace.id);

export const EXPERT_WORKSPACE_IDS = new Set([
  "historical-replay",
  "evidence-console",
]);
