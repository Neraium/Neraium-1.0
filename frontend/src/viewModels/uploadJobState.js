import { normalizeUploadStatus } from "./uploadContract";

export const AUTHORITATIVE_JOB_STATES = Object.freeze([
  "idle",
  "uploading",
  "queued",
  "claimed",
  "processing",
  "waiting",
  "stalled",
  "completed",
  "failed",
]);

const TERMINAL_FAILURES = new Set(["failed", "error", "validation_error", "timeout", "cancelled"]);
const ACTIVE_PROCESSING_STAGES = new Set([
  "validating_schema",
  "parsing",
  "parsing_telemetry",
  "detecting_schema_signals",
  "baseline_modeling",
  "baseline_validating",
  "baseline_quality_assessment",
  "baseline_mode_identification",
  "baseline_relationship_learning",
  "baseline_model_fitting",
  "baseline_candidate_persistence",
  "processing",
  "structural_scoring",
  "building_fingerprint",
  "cognition_ready",
  "saving_result",
  "saving_results",
  "writing_state",
]);

export function authoritativeJobState(payload = {}) {
  const explicit = String(payload?.execution_state ?? payload?.executionState ?? "").trim().toLowerCase();
  const jobState = String(payload?.job_state ?? payload?.jobState ?? "").trim().toLowerCase();
  const status = normalizeUploadStatus(payload?.status ?? payload?.processing_state ?? payload?.contract_stage);
  if (["completed", "completed_compatibility"].includes(jobState) || status === "complete") return "completed";
  if (["failed", "cancelled"].includes(jobState) || TERMINAL_FAILURES.has(status)) return "failed";

  const queueState = String(payload?.queue_state ?? payload?.queueState ?? "").trim().toLowerCase();
  if (queueState === "pending") return "queued";
  if (payload?.worker_heartbeat_stale === true || String(payload?.worker_state ?? "").toLowerCase() === "stalled") return "stalled";
  if (AUTHORITATIVE_JOB_STATES.includes(explicit)) return explicit;
  if (String(payload?.poll_connection_state ?? "").toLowerCase() === "interrupted") return "waiting";
  if (payload?.worker_claimed === true && ["queued", "accepted"].includes(status)) return "claimed";
  if (["queued", "accepted"].includes(status)) return "queued";
  if (payload?.worker_claimed === true || ACTIVE_PROCESSING_STAGES.has(status)) return "processing";
  return payload?.job_id || payload?.jobId ? "waiting" : "idle";
}

export function isTerminalJobState(value) {
  return ["completed", "failed"].includes(String(value || "").toLowerCase());
}

export function isPollableJobState(value) {
  return ["queued", "claimed", "processing", "waiting", "stalled"].includes(String(value || "").toLowerCase());
}

export function jobStateLabel(value) {
  return ({
    idle: "Idle",
    uploading: "Uploading",
    queued: "Queued",
    claimed: "Claimed by worker",
    processing: "Processing",
    waiting: "Waiting for status",
    stalled: "Stalled",
    completed: "Completed",
    failed: "Failed",
  })[String(value || "").toLowerCase()] ?? "Waiting for status";
}
