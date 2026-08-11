const EXPLAINED_CATEGORIES = new Set([
  "known_operational_change",
  "sensor_or_data_problem",
  "environmental_cause",
  "expected_behavior",
  "maintenance_event",
]);

const NOT_USEFUL_CATEGORIES = new Set([
  "nothing_meaningful",
  "false_positive",
  "ignore",
]);

const MONITORING_CATEGORIES = new Set([
  "confirmed_issue",
  "useful_warning",
]);

export const REVIEW_STATE_LABELS = Object.freeze({
  new: "New",
  acknowledged: "Acknowledged",
  investigating: "Investigating",
  explained: "Explained",
  monitoring: "Monitoring",
  closed: "Closed",
  not_useful: "Not useful",
});

export const KNOWN_CONDITIONS = Object.freeze([
  { value: "scheduled_staging_change", label: "Scheduled staging change", category: "expected_behavior" },
  { value: "maintenance_activity", label: "Maintenance activity", category: "maintenance_event" },
  { value: "setpoint_change", label: "Setpoint change", category: "known_operational_change" },
  { value: "known_sensor_issue", label: "Known sensor issue", category: "sensor_or_data_problem" },
  { value: "expected_operating_mode", label: "Expected operating mode", category: "expected_behavior" },
  { value: "other", label: "Other", category: "known_operational_change" },
]);

function cleanText(value) {
  return String(value ?? "").trim();
}

function normalizedState(value) {
  const raw = cleanText(value).toLowerCase().replace(/[ -]+/g, "_");
  const state = ({ open: "new", resolved: "closed", dismissed: "not_useful" })[raw] ?? raw;
  return Object.hasOwn(REVIEW_STATE_LABELS, state) ? state : "";
}

function normalizedAssignment(value = {}) {
  if (!value || typeof value !== "object") return { kind: "", label: "", externalReference: "" };
  return {
    kind: cleanText(value.kind ?? value.targetType ?? value.target_type ?? value.type),
    label: cleanText(value.label ?? value.name),
    externalReference: cleanText(value.externalReference ?? value.external_ref ?? value.external_reference),
  };
}

function normalizedResolution(value = {}) {
  if (!value || typeof value !== "object") return { outcome: "", note: "", resolvedAt: "" };
  return {
    outcome: cleanText(value.outcome),
    note: cleanText(value.note),
    resolvedAt: cleanText(value.resolvedAt ?? value.resolved_at),
  };
}

function workflowFields(record = {}) {
  return {
    status: cleanText(record.status ?? record.workflowStatus ?? record.workflow_status),
    version: Number.isInteger(Number(record.version)) ? Number(record.version) : 0,
    priority: cleanText(record.priority ?? record.effectivePriority ?? record.effective_priority),
    recommendedPriority: cleanText(record.recommendedPriority ?? record.recommended_priority),
    userPriority: cleanText(record.userPriority ?? record.user_priority),
    dueDate: cleanText(record.dueDate ?? record.due_at),
    managerNote: cleanText(record.managerNote ?? record.manager_note),
    assignment: normalizedAssignment(record.assignment),
    workOrderReference: cleanText(record.workOrderReference ?? record.work_order_reference),
    externalReference: cleanText(record.externalReference ?? record.external_reference),
    validationOutcome: cleanText(record.validationOutcome ?? record.validation_outcome),
    validationNote: cleanText(record.validationNote ?? record.validation_note),
    resolution: normalizedResolution(record.resolution),
    workflowFindingId: cleanText(record.workflowFindingId ?? record.findingId ?? record.finding_id),
    source: record.source && typeof record.source === "object" ? record.source : {},
  };
}

export function normalizeReviewRecords(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return Object.fromEntries(Object.entries(value).flatMap(([id, record]) => {
    if (!record || typeof record !== "object") return [];
    const state = normalizedState(record.status ?? record.state);
    if (!state) return [];
    return [[String(id), {
      state,
      reason: cleanText(record.reason),
      note: cleanText(record.note),
      reviewedAt: cleanText(record.reviewedAt ?? record.reviewed_at),
      owner: cleanText(record.owner ?? record.actor),
      persisted: record.persisted === true,
      ...workflowFields(record),
    }]];
  }));
}

export function reviewStateFromFeedback(feedback = {}) {
  const explicit = normalizedState(feedback.review_state ?? feedback.reviewState ?? feedback.status);
  if (explicit) return explicit;
  const category = cleanText(feedback.category ?? feedback.feedback_category);
  if (EXPLAINED_CATEGORIES.has(category)) return "explained";
  if (NOT_USEFUL_CATEGORIES.has(category)) return "not_useful";
  if (MONITORING_CATEGORIES.has(category)) return "monitoring";
  return "";
}

export function reviewRecordFromFinding(finding = {}) {
  const statusEvent = Array.isArray(finding.caseHistory) ? finding.caseHistory[0] : null;
  const caseState = statusEvent?.state ?? finding.caseState;
  const explicitCaseState = normalizedState(
    caseState === "open" ? "new"
      : caseState === "resolved" ? "closed"
        : caseState === "dismissed" ? "not_useful"
          : caseState,
  );
  if (explicitCaseState) {
    return {
      state: explicitCaseState,
      reason: cleanText(statusEvent?.note),
      note: cleanText(statusEvent?.note),
      reviewedAt: cleanText(statusEvent?.recorded_at),
      owner: cleanText(statusEvent?.owner ?? statusEvent?.actor),
      persisted: true,
    };
  }
  const feedback = finding.outcome && typeof finding.outcome === "object" ? finding.outcome : {};
  const state = reviewStateFromFeedback(feedback);
  if (!state) return null;
  return {
    state,
    reason: cleanText(feedback.outcome ?? feedback.note),
    note: cleanText(feedback.note),
    reviewedAt: cleanText(feedback.recorded_at ?? feedback.recordedAt),
    owner: cleanText(feedback.actor),
    persisted: true,
  };
}

export function reviewRecordFromWorkflow(workflow = {}) {
  if (!workflow || typeof workflow !== "object") return null;
  const state = normalizedState(workflow.status ?? workflow.state);
  if (!state) return null;
  return {
    state,
    reason: cleanText(workflow.resolution?.outcome),
    note: cleanText(workflow.managerNote ?? workflow.manager_note ?? workflow.resolution?.note),
    reviewedAt: cleanText(workflow.updatedAt ?? workflow.updated_at ?? workflow.resolution?.resolvedAt ?? workflow.resolution?.resolved_at),
    owner: cleanText(workflow.updatedBy ?? workflow.updated_by),
    persisted: true,
    ...workflowFields(workflow),
  };
}

export function reviewRecordFor(finding, records = {}) {
  const id = String(finding?.id ?? "");
  return records[id] ?? reviewRecordFromWorkflow(finding?.workflow) ?? reviewRecordFromFinding(finding) ?? { state: "new", reason: "", note: "", reviewedAt: "", owner: "", persisted: false, ...workflowFields() };
}

export function reviewStateLabel(recordOrState) {
  const state = normalizedState(typeof recordOrState === "string" ? recordOrState : recordOrState?.state) || "new";
  return REVIEW_STATE_LABELS[state];
}

export function isResolvedReviewState(recordOrState) {
  const state = normalizedState(typeof recordOrState === "string" ? recordOrState : recordOrState?.state);
  return state === "explained" || state === "closed";
}

export function isSuppressedReviewState(recordOrState) {
  const state = normalizedState(typeof recordOrState === "string" ? recordOrState : recordOrState?.state);
  return state === "not_useful";
}

export function feedbackForReviewAction(action = {}) {
  if (action.state === "not_useful") {
    return { category: "nothing_meaningful", outcome: "Not useful", note: action.note || null };
  }
  if (action.state !== "explained") return null;
  const condition = KNOWN_CONDITIONS.find((item) => item.value === action.reason) ?? KNOWN_CONDITIONS[KNOWN_CONDITIONS.length - 1];
  const note = cleanText(action.note);
  return {
    category: condition.category,
    outcome: condition.label,
    note: note || condition.label,
  };
}
