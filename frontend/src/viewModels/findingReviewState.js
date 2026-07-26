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
  const state = cleanText(value).toLowerCase().replace(/[ -]+/g, "_");
  return Object.hasOwn(REVIEW_STATE_LABELS, state) ? state : "";
}

export function normalizeReviewRecords(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return Object.fromEntries(Object.entries(value).flatMap(([id, record]) => {
    if (!record || typeof record !== "object") return [];
    const state = normalizedState(record.state);
    if (!state) return [];
    return [[String(id), {
      state,
      reason: cleanText(record.reason),
      note: cleanText(record.note),
      reviewedAt: cleanText(record.reviewedAt ?? record.reviewed_at),
      owner: cleanText(record.owner ?? record.actor),
      persisted: record.persisted === true,
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

export function reviewRecordFor(finding, records = {}) {
  const id = String(finding?.id ?? "");
  return records[id] ?? reviewRecordFromFinding(finding) ?? { state: "new", reason: "", note: "", reviewedAt: "", owner: "", persisted: false };
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
