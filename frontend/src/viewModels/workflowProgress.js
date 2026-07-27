export const BASELINE_PROGRESS_STATE_MACHINE = "baseline_construction.v1";
export const MONITORING_PROGRESS_STATE_MACHINE = "sii_monitoring.v1";

export const BASELINE_PROGRESS_STAGES = Object.freeze([
  { id: "import", label: "Import", description: "Bringing the historical dataset into the baseline workspace." },
  { id: "validate", label: "Validate", description: "Checking historical coverage and dataset structure." },
  { id: "map", label: "Map", description: "Mapping historical signals to systems, assets, and sensors." },
  { id: "learn", label: "Learn", description: "Learning the expected operating patterns in the historical dataset." },
  { id: "review", label: "Review", description: "Preparing the Baseline Suitability Report and candidate Behavioral Digital Model." },
  { id: "ready", label: "Ready", description: "The Baseline Suitability Report and candidate Behavioral Digital Model are ready." },
]);

export const BASELINE_LEARN_STEPS = Object.freeze([
  { id: "validating_historical_coverage", label: "Validating historical coverage" },
  { id: "assessing_data_quality", label: "Assessing data quality" },
  { id: "checking_sensor_suitability", label: "Checking sensor suitability" },
  { id: "identifying_operating_modes", label: "Identifying operating modes" },
  { id: "learning_signal_behavior", label: "Learning signal behavior" },
  { id: "learning_relationships", label: "Learning relationships" },
  { id: "building_behavioral_graph", label: "Building behavioral graph" },
  { id: "estimating_empirical_thresholds", label: "Estimating empirical thresholds" },
  { id: "fitting_expected_behavior_models", label: "Fitting expected-behavior models" },
  { id: "creating_candidate_baseline", label: "Creating candidate baseline" },
]);

export const MONITORING_PROGRESS_STAGES = Object.freeze([
  { id: "import", label: "Import", description: "Loading the selected operational dataset." },
  { id: "validate", label: "Validate", description: "Checking the dataset format and required signals." },
  { id: "load", label: "Load Baseline", description: "Loading the active Behavioral Digital Model." },
  { id: "compare", label: "Compare", description: "Comparing operational behavior with the active baseline." },
  { id: "reason", label: "Reason", description: "Evaluating physics and propagation context." },
  { id: "evidence", label: "Evidence", description: "Fusing supporting evidence and confidence context." },
  { id: "observations", label: "Observations", description: "Saving observations for operator review." },
]);

const BASELINE_WORKFLOWS = new Set(["create_baseline", "extend_baseline"]);
const BASELINE_STAGE_IDS = new Set(BASELINE_PROGRESS_STAGES.map((stage) => stage.id));
const MONITORING_STAGE_IDS = new Set(MONITORING_PROGRESS_STAGES.map((stage) => stage.id));
const PROHIBITED_BASELINE_COPY = /\b(?:compar(?:e[ds]?|ing|isons?)|anomal(?:y|ies)|evidence|findings?|current\s+behavior)\b|drift\s+against\s+(?:the\s+)?baseline/i;

export function isBaselineWorkflow(value) {
  return BASELINE_WORKFLOWS.has(String(value || "").trim().toLowerCase());
}

export function isSafeBaselineCopy(value) {
  return !PROHIBITED_BASELINE_COPY.test(String(value || ""));
}

function stageStates(stages, activeId) {
  const activeIndex = Math.max(0, stages.findIndex((stage) => stage.id === activeId));
  return stages.map((stage, index) => ({
    ...stage,
    state: index < activeIndex ? "complete" : index === activeIndex ? "active" : "pending",
  }));
}

function inferredBaselineStage(payload, clientState) {
  const explicit = String(payload?.baseline_stage || "").trim().toLowerCase();
  if (BASELINE_STAGE_IDS.has(explicit)) return explicit;
  const state = String(clientState || payload?.processing_state || payload?.status || "").trim().toLowerCase();
  if (["baseline_ready", "baseline_active", "complete", "save_complete"].includes(state)) return "ready";
  if (["baseline_review", "baseline_reviewing"].includes(state)) return "review";
  if (state.includes("baseline_mapping")) return "map";
  if (state.includes("baseline_validat")) return "validate";
  if (state.includes("baseline_") || state === "baseline_processing") return "learn";
  return "import";
}

function baselineStep(payload, stageId) {
  const suppliedId = String(payload?.baseline_step || "").trim();
  const suppliedLabel = String(payload?.baseline_step_label || "").trim();
  if (suppliedLabel && isSafeBaselineCopy(suppliedLabel)) {
    return { id: suppliedId || stageId, label: suppliedLabel };
  }
  if (stageId === "learn") return BASELINE_LEARN_STEPS[0];
  const stage = BASELINE_PROGRESS_STAGES.find((item) => item.id === stageId) ?? BASELINE_PROGRESS_STAGES[0];
  return { id: stage.id, label: stage.description };
}

export function resolveBaselineProgress(payload = {}, clientState = "") {
  const stageId = inferredBaselineStage(payload, clientState);
  const complete = stageId === "ready";
  const stages = stageStates(BASELINE_PROGRESS_STAGES, stageId);
  const currentIndex = stages.findIndex((stage) => stage.id === stageId);
  const current = stages[currentIndex] ?? stages[0];
  const step = baselineStep(payload, stageId);
  const suppliedLearnIndex = Number(payload?.baseline_learn_step_index);
  const learnIndex = Number.isInteger(suppliedLearnIndex) && suppliedLearnIndex >= 0
    ? Math.min(BASELINE_LEARN_STEPS.length - 1, suppliedLearnIndex)
    : Math.max(0, BASELINE_LEARN_STEPS.findIndex((item) => item.id === step.id));
  return {
    kind: "baseline",
    stateMachine: BASELINE_PROGRESS_STATE_MACHINE,
    stages,
    current: { ...current, detail: step.label },
    currentIndex,
    learnSteps: BASELINE_LEARN_STEPS.map((item, index) => ({
      ...item,
      state: stageId === "ready" || stageId === "review" || index < learnIndex
        ? "complete"
        : stageId === "learn" && index === learnIndex
          ? "active"
          : "pending",
    })),
    complete,
  };
}

function inferredMonitoringStage(payload, clientState) {
  const explicit = String(payload?.monitoring_stage || "").trim().toLowerCase();
  if (MONITORING_STAGE_IDS.has(explicit)) return explicit;
  const state = String(payload?.contract_stage || payload?.processing_state || clientState || payload?.status || "").trim().toLowerCase();
  if (["complete", "completed", "save_complete", "navigation_pending", "saving_results"].includes(state)) return "observations";
  if (["writing_state", "generating_findings_evidence", "cognition_ready"].includes(state)) return "evidence";
  if (["building_propagation_model", "generating_system_interpretation"].includes(state)) return "reason";
  if (["running_sii", "structural_scoring", "building_fingerprint", "scoring_drift_relationships"].includes(state)) return "compare";
  if (["baseline_modeling", "building_baseline", "processing"].includes(state)) return "load";
  if (["validating_schema", "parsing", "detecting_schema_signals"].includes(state)) return "validate";
  return "import";
}

export function resolveMonitoringProgress(payload = {}, clientState = "") {
  const stageId = inferredMonitoringStage(payload, clientState);
  const complete = ["complete", "completed", "save_complete"].includes(
    String(payload?.processing_state || payload?.status || clientState || "").trim().toLowerCase(),
  );
  const stages = stageStates(MONITORING_PROGRESS_STAGES, stageId);
  const currentIndex = stages.findIndex((stage) => stage.id === stageId);
  const current = stages[currentIndex] ?? stages[0];
  return {
    kind: "monitoring",
    stateMachine: MONITORING_PROGRESS_STATE_MACHINE,
    stages,
    current: { ...current, detail: current.description },
    currentIndex,
    learnSteps: [],
    complete,
  };
}

export function resolveWorkflowProgress({ workflow, payload = {}, clientState = "" } = {}) {
  return isBaselineWorkflow(workflow ?? payload?.workflow)
    ? resolveBaselineProgress(payload, clientState)
    : resolveMonitoringProgress(payload, clientState);
}
