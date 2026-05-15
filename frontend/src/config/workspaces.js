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
  {
    id: "operator-workflow",
    label: "Operator Workflow",
    eyebrow: "Expert View",
    description: "Canonical full operator workflow from cognition state through replay and convergence review.",
  },
  {
    id: "cultivation-evidence",
    label: "Cultivation Evidence",
    eyebrow: "Expert View",
    description: "Evidence-first cultivation workspace for VPD relationships, compensation masking, and room synchronization drift.",
  },
  {
    id: "system-body",
    label: "Current Cognition State",
    eyebrow: "Expert View",
    description: "Facility cognition state, structural stability, and active pathways.",
  },
  {
    id: "drift-timeline",
    label: "Drift Timeline",
    eyebrow: "Expert View",
    description: "Trajectory of structural distance from stable baseline.",
  },
  {
    id: "fleet-view",
    label: "Multi-Site Cognition",
    eyebrow: "Expert View",
    description: "Cross-site structural cognition network and recurring archetype clusters.",
  },
  {
    id: "structural-ontology",
    label: "Structural Ontology",
    eyebrow: "Expert View",
    description: "Visualize archetype primitives, ontology relationships, and domain cognition mappings.",
  },
  {
    id: "ecosystem-workspace",
    label: "Ecosystem Layer",
    eyebrow: "Expert View",
    description: "Read-only integration posture, cognition state export, and structural graph ecosystem context.",
  },
  {
    id: "distributed-cognition",
    label: "Distributed Cognition",
    eyebrow: "Expert View",
    description: "Federated structural cognition, persistent graph memory, ontology evolution, and governance.",
  },
  {
    id: "operator-training",
    label: "Operator Training",
    eyebrow: "Cognition Training",
    description: "Replay-backed operator cognition training for structural evolution interpretation.",
  },
  {
    id: "behavior-science",
    label: "Behavior Science",
    eyebrow: "Research Layer",
    description: "Long-horizon structural behavior science, taxonomy, evolution theory, and explainability standards.",
  },
  {
    id: "operator-cognition-training",
    label: "Operator Curriculum",
    eyebrow: "Training System",
    description: "Replay-based operator cognition curriculum for structural interpretation exercises.",
  },
  {
    id: "structural-cognition-research",
    label: "Research Workspace",
    eyebrow: "Framework Layer",
    description: "Universal primitives, structural evolution mathematics, governance queue, archives, and reasoning traces.",
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

export const PRIMARY_WORKSPACE_ORDER = [
  "cultivation-mission-control",
  "historical-replay",
  "evidence-console",
  "propagation-map",
  "data-connections",
];

export const EXPERT_WORKSPACE_IDS = new Set(
  WORKSPACES.map((workspace) => workspace.id).filter((id) => !PRIMARY_WORKSPACE_ORDER.includes(id)),
);
