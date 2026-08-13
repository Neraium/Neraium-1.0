const UNAVAILABLE_STATUSES = new Set([404, 405, 501]);

function cleanText(value) {
  return String(value ?? "").trim();
}

function optionalText(value) {
  const text = cleanText(value);
  return text || null;
}

function integer(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= 0 ? parsed : fallback;
}

async function readPayload(response) {
  try {
    return typeof response?.json === "function" ? await response.json() : null;
  } catch {
    return null;
  }
}

export class FindingApiError extends Error {
  constructor(message, { status = 0, code = "finding_api_error", payload = null } = {}) {
    super(message);
    this.name = "FindingApiError";
    this.status = status;
    this.code = code;
    this.payload = payload;
    this.unavailable = UNAVAILABLE_STATUSES.has(status) || code === "finding_api_unavailable";
    this.conflict = status === 409 || status === 412 || code === "version_conflict";
  }
}

function errorDetail(payload, fallback) {
  const detail = payload?.detail;
  return cleanText(
    (detail && typeof detail === "object" ? detail.message ?? detail.error : detail)
      ?? payload?.message
      ?? payload?.error,
  ) || fallback;
}

async function checkedPayload(response, fallbackMessage) {
  const payload = await readPayload(response);
  if (response?.ok) return payload;
  const status = Number(response?.status ?? 0);
  const code = cleanText(payload?.code ?? payload?.detail?.code ?? payload?.detail?.error)
    || (status === 409 || status === 412 ? "version_conflict" : UNAVAILABLE_STATUSES.has(status) ? "finding_api_unavailable" : "finding_api_error");
  throw new FindingApiError(errorDetail(payload, fallbackMessage), { status, code, payload });
}

export function findingWorkflowIdentity(finding) {
  return cleanText(
    finding?.workflowFindingId
      ?? finding?.workflow_finding_id
      ?? finding?.canonicalFindingId
      ?? finding?.canonical_finding_id
      ?? finding?.finding_id
      ?? finding?.id,
  );
}

export function normalizeFindingWorkflow(payload, fallback = {}) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return null;
  const finding = payload.finding && typeof payload.finding === "object" ? payload.finding : payload;
  const raw = finding.workflow && typeof finding.workflow === "object"
    ? finding.workflow
    : payload.workflow && typeof payload.workflow === "object"
      ? payload.workflow
      : finding;
  const hasWorkflowShape = [
    raw.version, raw.workflow_version, raw.status, raw.workflow_status, raw.lifecycle_state,
    raw.user_priority, raw.recommended_priority, raw.effective_priority, raw.assignment, raw.assignee, raw.due_at,
    raw.manager_note, raw.resolution, raw.validation_outcome,
  ].some((value) => value !== undefined && value !== null);
  if (!hasWorkflowShape) return null;
  const assignment = raw.assignment && typeof raw.assignment === "object"
    ? raw.assignment
    : raw.assignee && typeof raw.assignee === "object"
      ? raw.assignee
      : {};
  const resolution = raw.resolution && typeof raw.resolution === "object" ? raw.resolution : {};
  const source = finding.source && typeof finding.source === "object" ? finding.source : payload.source ?? fallback.source ?? {};
  const status = cleanText(raw.status ?? raw.workflow_status ?? raw.lifecycle_state ?? raw.state ?? fallback.status) || "new";
  return {
    findingId: cleanText(finding.finding_id ?? finding.id ?? payload.finding_id ?? fallback.findingId),
    source,
    version: integer(raw.version ?? raw.workflow_version ?? finding.workflow_version ?? payload.workflow_version),
    status,
    recommendedPriority: cleanText(raw.recommended_priority ?? fallback.recommendedPriority),
    userPriority: cleanText(raw.user_priority ?? fallback.userPriority),
    priority: cleanText(raw.effective_priority ?? raw.user_priority ?? raw.recommended_priority ?? fallback.priority),
    dueDate: cleanText(raw.due_at ?? fallback.dueDate),
    managerNote: cleanText(raw.manager_note ?? raw.managerNote ?? fallback.managerNote),
    assignment: {
      kind: cleanText(assignment.target_type ?? assignment.kind ?? assignment.type ?? raw.assignment_kind ?? raw.assignee_type ?? fallback.assignment?.kind),
      label: cleanText(assignment.label ?? assignment.name ?? raw.assignment_label ?? raw.assignee_label ?? raw.owner ?? fallback.assignment?.label),
      externalReference: cleanText(assignment.external_ref ?? assignment.external_reference ?? assignment.externalReference ?? fallback.assignment?.externalReference),
    },
    assignedBy: cleanText(raw.assigned_by ?? raw.assignedBy ?? fallback.assignedBy),
    assignmentHistory: Array.isArray(raw.assignment_history ?? raw.assignmentHistory)
      ? (raw.assignment_history ?? raw.assignmentHistory)
      : [],
    workOrderReference: cleanText(raw.work_order_reference ?? fallback.workOrderReference),
    externalReference: cleanText(raw.external_reference ?? fallback.externalReference),
    validationOutcome: cleanText(raw.validation_outcome ?? fallback.validationOutcome),
    validationNote: cleanText(raw.validation_note ?? fallback.validationNote),
    latestFeedback: raw.latest_feedback && typeof raw.latest_feedback === "object" ? raw.latest_feedback : null,
    latestFieldReport: raw.latest_field_report && typeof raw.latest_field_report === "object" ? raw.latest_field_report : null,
    fieldReports: Array.isArray(raw.field_reports) ? raw.field_reports : [],
    resolution: {
      outcome: cleanText(resolution.outcome ?? raw.resolution_outcome ?? fallback.resolution?.outcome),
      note: cleanText(resolution.note ?? raw.resolution_note ?? fallback.resolution?.note),
      resolvedAt: cleanText(resolution.resolved_at ?? raw.resolved_at ?? fallback.resolution?.resolvedAt),
    },
    updatedAt: cleanText(raw.updated_at ?? finding.updated_at ?? payload.updated_at),
    updatedBy: cleanText(raw.updated_by ?? finding.updated_by ?? payload.updated_by),
    persisted: true,
  };
}

export function isFindingApiUnavailable(error) {
  return error?.unavailable === true || UNAVAILABLE_STATUSES.has(Number(error?.status));
}

function requireClient(apiFetch) {
  if (typeof apiFetch !== "function") throw new TypeError("apiFetch is required for finding workflow requests.");
}

function requireIdentity(findingId) {
  const id = cleanText(findingId);
  if (!id) throw new TypeError("findingId is required for finding workflow requests.");
  return id;
}

function requireVersion(expectedVersion) {
  const version = Number(expectedVersion);
  if (!Number.isInteger(version) || version < 0) throw new TypeError("expectedVersion must be a non-negative integer.");
  return version;
}

function idempotencyKey(value, findingId, version, action) {
  const supplied = cleanText(value);
  if (supplied) return supplied;
  const random = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `finding-${action}-${findingId}-${version}-${random}`;
}

export async function fetchFinding({ apiFetch, findingId, signal } = {}) {
  requireClient(apiFetch);
  const id = requireIdentity(findingId);
  const response = await apiFetch(`/api/findings/${encodeURIComponent(id)}`, { cache: "no-store", signal });
  const payload = await checkedPayload(response, "Finding workflow could not be loaded.");
  const workflow = normalizeFindingWorkflow(payload, { findingId: id });
  if (!workflow) throw new FindingApiError("Finding workflow response was not recognized.", { status: Number(response?.status ?? 0), code: "finding_api_unavailable", payload });
  return { payload, workflow };
}

export async function fetchFindings({
  apiFetch,
  sourceKind,
  sourceRunId,
  status,
  priority,
  system,
  assignee,
  assignedToMe = false,
  unassigned = false,
  overdue = false,
  inProgress = false,
  awaitingReview = false,
  recentlyResolved = false,
  active = false,
  limit = 100,
  offset = 0,
  signal,
} = {}) {
  requireClient(apiFetch);
  const params = new URLSearchParams();
  if (cleanText(sourceKind)) params.set("source_kind", cleanText(sourceKind));
  if (cleanText(sourceRunId)) params.set("source_run_id", cleanText(sourceRunId));
  if (cleanText(status)) params.set("status", cleanText(status));
  if (cleanText(priority)) params.set("priority", cleanText(priority));
  if (cleanText(system)) params.set("system", cleanText(system));
  if (cleanText(assignee)) params.set("assignee", cleanText(assignee));
  if (assignedToMe) params.set("assigned_to_me", "true");
  if (unassigned) params.set("unassigned", "true");
  if (overdue) params.set("overdue", "true");
  if (inProgress) params.set("in_progress", "true");
  if (awaitingReview) params.set("awaiting_review", "true");
  if (recentlyResolved) params.set("recently_resolved", "true");
  if (active) params.set("active", "true");
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  const response = await apiFetch(`/api/findings?${params.toString()}`, { cache: "no-store", signal });
  const payload = await checkedPayload(response, "Findings could not be loaded.");
  if (!Array.isArray(payload?.findings)) throw new FindingApiError("Findings response was not recognized.", { status: Number(response?.status ?? 0), code: "finding_api_unavailable", payload });
  return {
    ...payload,
    findings: payload.findings.map((finding) => ({ finding, workflow: normalizeFindingWorkflow(finding) })).filter((item) => item.workflow),
  };
}

export async function fetchFindingActivity({ apiFetch, findingId, signal } = {}) {
  requireClient(apiFetch);
  const id = requireIdentity(findingId);
  const response = await apiFetch(`/api/findings/${encodeURIComponent(id)}/activity`, { cache: "no-store", signal });
  const payload = await checkedPayload(response, "Finding activity could not be loaded.");
  return Array.isArray(payload) ? payload : Array.isArray(payload?.activity) ? payload.activity : Array.isArray(payload?.events) ? payload.events : [];
}

export async function fetchFindingMembers({ apiFetch, signal } = {}) {
  requireClient(apiFetch);
  const response = await apiFetch("/api/findings/members", { cache: "no-store", signal });
  const payload = await checkedPayload(response, "Team members could not be loaded.");
  if (!Array.isArray(payload?.members)) throw new FindingApiError("Team member response was not recognized.", { status: Number(response?.status ?? 0), payload });
  return payload.members.map((member) => ({
    memberId: cleanText(member.member_id ?? member.memberId),
    displayName: cleanText(member.display_name ?? member.displayName ?? member.member_id),
    role: cleanText(member.role),
    active: member.is_active !== false,
  })).filter((member) => member.memberId && member.active);
}

function assignmentBody(assignment) {
  if (assignment === null) return null;
  if (!assignment || typeof assignment !== "object") return undefined;
  const label = optionalText(assignment.label);
  const kind = optionalText(assignment.kind);
  const externalReference = optionalText(assignment.externalReference ?? assignment.external_reference);
  if (!label && !kind && !externalReference) return null;
  return { target_type: kind, label, external_ref: externalReference };
}

function workflowMutationBody(changes, expectedVersion, key) {
  const body = { expected_version: requireVersion(expectedVersion), idempotency_key: key };
  if (Object.hasOwn(changes, "status")) body.status = optionalText(changes.status);
  if (Object.hasOwn(changes, "priority") || Object.hasOwn(changes, "userPriority") || Object.hasOwn(changes, "user_priority")) body.user_priority = optionalText(changes.userPriority ?? changes.user_priority ?? changes.priority);
  if (Object.hasOwn(changes, "dueDate") || Object.hasOwn(changes, "due_at")) body.due_at = optionalText(changes.dueDate ?? changes.due_at);
  if (Object.hasOwn(changes, "managerNote") || Object.hasOwn(changes, "manager_note")) body.manager_note = optionalText(changes.managerNote ?? changes.manager_note);
  if (Object.hasOwn(changes, "assignment")) body.assignment = assignmentBody(changes.assignment);
  if (Object.hasOwn(changes, "workOrderReference") || Object.hasOwn(changes, "work_order_reference")) body.work_order_reference = optionalText(changes.workOrderReference ?? changes.work_order_reference);
  if (Object.hasOwn(changes, "externalReference") || Object.hasOwn(changes, "external_reference")) body.external_reference = optionalText(changes.externalReference ?? changes.external_reference);
  if (Object.hasOwn(changes, "validationOutcome") || Object.hasOwn(changes, "validation_outcome")) body.validation_outcome = optionalText(changes.validationOutcome ?? changes.validation_outcome);
  if (Object.hasOwn(changes, "validationNote") || Object.hasOwn(changes, "validation_note")) body.validation_note = optionalText(changes.validationNote ?? changes.validation_note);
  return body;
}

export async function patchFindingWorkflow({ apiFetch, findingId, expectedVersion, changes = {}, idempotencyKey: suppliedKey = "", signal } = {}) {
  requireClient(apiFetch);
  const id = requireIdentity(findingId);
  const version = requireVersion(expectedVersion);
  const response = await apiFetch(`/api/findings/${encodeURIComponent(id)}/workflow`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", "If-Match": String(version) },
    body: JSON.stringify(workflowMutationBody(changes, version, idempotencyKey(suppliedKey, id, version, "workflow"))),
    signal,
  });
  const payload = await checkedPayload(response, "Finding workflow could not be saved.");
  const workflow = normalizeFindingWorkflow(payload, { findingId: id });
  if (!workflow) throw new FindingApiError("Finding workflow response was not recognized.", { status: Number(response?.status ?? 0), code: "finding_api_unavailable", payload });
  return { payload, workflow };
}

export async function resolveFinding({ apiFetch, findingId, expectedVersion, outcome, note = "", idempotencyKey: suppliedKey = "", signal } = {}) {
  requireClient(apiFetch);
  const id = requireIdentity(findingId);
  const version = requireVersion(expectedVersion);
  const normalizedOutcome = optionalText(outcome);
  if (!normalizedOutcome) throw new TypeError("outcome is required to resolve a finding.");
  const response = await apiFetch(`/api/findings/${encodeURIComponent(id)}/resolution`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "If-Match": String(version) },
    body: JSON.stringify({ expected_version: version, idempotency_key: idempotencyKey(suppliedKey, id, version, "resolution"), outcome: normalizedOutcome, note: optionalText(note) }),
    signal,
  });
  const payload = await checkedPayload(response, "Finding resolution could not be saved.");
  const workflow = normalizeFindingWorkflow(payload, { findingId: id, status: "resolved", resolution: { outcome: normalizedOutcome, note } });
  if (!workflow) throw new FindingApiError("Finding resolution response was not recognized.", { status: Number(response?.status ?? 0), code: "finding_api_unavailable", payload });
  return { payload, workflow };
}

export async function postFindingFeedback({ apiFetch, findingId, expectedVersion, category, note = "", outcome = "", actionTaken = "", interventionAt = "", followupAt = "", idempotencyKey: suppliedKey = "", signal } = {}) {
  requireClient(apiFetch);
  const id = requireIdentity(findingId);
  const version = requireVersion(expectedVersion);
  const normalizedCategory = optionalText(category);
  if (!normalizedCategory) throw new TypeError("category is required to record finding feedback.");
  const response = await apiFetch(`/api/findings/${encodeURIComponent(id)}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "If-Match": String(version) },
    body: JSON.stringify({
      expected_version: version,
      idempotency_key: idempotencyKey(suppliedKey, id, version, "feedback"),
      category: normalizedCategory,
      note: optionalText(note),
      outcome: optionalText(outcome),
      action_taken: optionalText(actionTaken),
      intervention_at: optionalText(interventionAt),
      followup_at: optionalText(followupAt),
    }),
    signal,
  });
  const payload = await checkedPayload(response, "Finding feedback could not be saved.");
  const workflow = normalizeFindingWorkflow(payload, { findingId: id });
  if (!workflow) throw new FindingApiError("Finding feedback response was not recognized.", { status: Number(response?.status ?? 0), code: "finding_api_unavailable", payload });
  return { payload, workflow };
}

export async function postFindingFieldReport({
  apiFetch,
  findingId,
  expectedVersion,
  note = "",
  inspected = "",
  found = "",
  actionTaken = "",
  problemFound = "uncertain",
  needsEscalation = false,
  investigationComplete = false,
  idempotencyKey: suppliedKey = "",
  signal,
} = {}) {
  requireClient(apiFetch);
  const id = requireIdentity(findingId);
  const version = requireVersion(expectedVersion);
  const normalizedProblem = cleanText(problemFound).toLowerCase();
  if (!["yes", "no", "uncertain"].includes(normalizedProblem)) throw new TypeError("problemFound must be yes, no, or uncertain.");
  const response = await apiFetch(`/api/findings/${encodeURIComponent(id)}/field-reports`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "If-Match": String(version) },
    body: JSON.stringify({
      expected_version: version,
      idempotency_key: idempotencyKey(suppliedKey, id, version, "field-report"),
      note: optionalText(note),
      inspected: optionalText(inspected),
      found: optionalText(found),
      action_taken: optionalText(actionTaken),
      problem_found: normalizedProblem,
      needs_escalation: Boolean(needsEscalation),
      investigation_complete: Boolean(investigationComplete),
    }),
    signal,
  });
  const payload = await checkedPayload(response, "Field report could not be saved.");
  const workflow = normalizeFindingWorkflow(payload, { findingId: id });
  if (!workflow) throw new FindingApiError("Field report response was not recognized.", { status: Number(response?.status ?? 0), code: "finding_api_unavailable", payload });
  return { payload, workflow };
}
