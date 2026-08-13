const TERMINAL_STATUSES = new Set(["resolved", "dismissed"]);

export const WORK_FILTERS = [
  { id: "active", label: "Active" },
  { id: "needs-assignment", label: "Needs assignment" },
  { id: "in-progress", label: "In progress" },
  { id: "overdue", label: "Overdue" },
  { id: "awaiting-review", label: "Awaiting review" },
  { id: "recently-resolved", label: "Recently resolved" },
];

function text(value) {
  return String(value ?? "").replace(/\s+/g, " ").trim();
}

function firstText(...values) {
  return values.map(text).find(Boolean) ?? "";
}

function title(value, fallback = "Not set") {
  const clean = text(value);
  return clean ? clean.replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase()) : fallback;
}

function listFirst(value) {
  return Array.isArray(value) ? text(value[0]) : "";
}

function recommendationFirst(value) {
  if (!Array.isArray(value) || !value.length) return "";
  return typeof value[0] === "object" ? text(value[0]?.check ?? value[0]?.action) : text(value[0]);
}

function plainChange(value) {
  const clean = text(value)
    .replace(/\brelationship weakening\b/gi, "behavior changed")
    .replace(/\bcoupling\b/gi, "response")
    .replace(/\bcorrelation\b/gi, "response pattern");
  return clean || "Neraium detected a persistent change that needs review.";
}

function findingSource(item) {
  const finding = item?.finding ?? item ?? {};
  const evidence = finding.evidence && typeof finding.evidence === "object" ? finding.evidence : {};
  return {
    rawCase: finding,
    source: finding.source ?? {},
    evidence,
    analytical: evidence.finding && typeof evidence.finding === "object" ? evidence.finding : {},
  };
}

export function workStatusLabel(value) {
  const status = text(value).toLowerCase().replace(/[ -]+/g, "_");
  return ({
    open: "Needs review",
    acknowledged: "Assigned",
    investigating: "In progress",
    waiting: "Waiting",
    escalated: "Escalated",
    awaiting_review: "Awaiting review",
    monitoring: "Monitoring",
    resolved: "Resolved",
    dismissed: "Dismissed",
  })[status] ?? title(status, "Needs review");
}

export function workDueState(value, now = new Date()) {
  const source = text(value);
  if (!source) return { label: "No due date", tone: "none", overdue: false };
  const due = new Date(source.length === 10 ? `${source}T23:59:59Z` : source);
  if (Number.isNaN(due.getTime())) return { label: "Due date unavailable", tone: "none", overdue: false };
  const today = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  const dueDay = new Date(Date.UTC(due.getUTCFullYear(), due.getUTCMonth(), due.getUTCDate()));
  const days = Math.round((dueDay.getTime() - today.getTime()) / 86_400_000);
  if (days < 0) return { label: `Overdue · ${due.toLocaleDateString()}`, tone: "overdue", overdue: true };
  if (days === 0) return { label: "Due today", tone: "today", overdue: false };
  if (days === 1) return { label: "Due tomorrow", tone: "soon", overdue: false };
  return { label: `Due ${due.toLocaleDateString()}`, tone: days <= 7 ? "soon" : "scheduled", overdue: false };
}

export function queryForWorkQueue({ mode = "mine", filter = "active", assignee = "", priority = "", status = "", system = "", limit = 30, offset = 0 } = {}) {
  return {
    assignedToMe: mode === "mine" && filter !== "needs-assignment",
    unassigned: filter === "needs-assignment",
    inProgress: filter === "in-progress",
    overdue: filter === "overdue",
    awaitingReview: filter === "awaiting-review",
    recentlyResolved: filter === "recently-resolved",
    active: filter === "active",
    assignee: mode === "team" ? text(assignee) : "",
    priority: text(priority),
    status: text(status),
    system: text(system),
    limit,
    offset,
  };
}

export function normalizeWorkFinding(item, now = new Date()) {
  const { rawCase, source, evidence, analytical } = findingSource(item);
  const workflow = item?.workflow ?? rawCase.workflow ?? {};
  const assignment = workflow.assignment ?? {};
  const system = firstText(
    analytical.system_name,
    analytical.system,
    listFirst(analytical.affected_systems),
    analytical.localization?.system,
    analytical.system_id,
    "System not identified",
  );
  const equipment = firstText(
    analytical.equipment_name,
    analytical.equipment,
    analytical.asset_name,
    analytical.localization?.monitored_boundary,
    analytical.subsystem_name,
    system,
  );
  const change = plainChange(firstText(
    analytical.headline,
    analytical.title,
    analytical.what_changed,
    analytical.summary,
    analytical.classification?.label,
  ));
  const firstCheck = plainChange(firstText(
    listFirst(analytical.next_checks),
    recommendationFirst(analytical.recommended_investigation),
    analytical.recommended_action,
    workflow.managerNote,
    "Confirm the equipment condition and compare it with the operating log.",
  ));
  const due = workDueState(workflow.dueDate ?? workflow.due_at, now);
  const confidence = firstText(
    analytical.confidence?.tier,
    analytical.confidence?.label,
    analytical.confidence,
    analytical.classification?.confidence,
    "Not stated",
  );
  const status = text(workflow.status) || "open";
  return {
    findingId: text(workflow.findingId ?? rawCase.finding_id ?? rawCase.id),
    sourceFindingKey: text(source.finding_key ?? evidence.source_finding_key),
    sourceRunId: text(source.run_id ?? evidence.source_run_id),
    system,
    equipment,
    change,
    firstCheck,
    whyItMatters: plainChange(firstText(analytical.why_it_matters, analytical.impact, analytical.significance)),
    priority: text(workflow.priority ?? workflow.effectivePriority ?? workflow.effective_priority ?? evidence.recommended_priority) || "medium",
    status,
    statusLabel: workStatusLabel(status),
    assignment: {
      kind: text(assignment.kind ?? assignment.target_type),
      label: text(assignment.label) || "Unassigned",
      externalReference: text(assignment.externalReference ?? assignment.external_ref),
      historical: Boolean(text(assignment.label) && !text(assignment.externalReference ?? assignment.external_ref)),
    },
    assignedBy: text(workflow.assignedBy ?? workflow.assigned_by) || "Not recorded",
    due,
    confidence: title(confidence, "Not stated"),
    version: Number(workflow.version ?? 0),
    managerNote: text(workflow.managerNote ?? workflow.manager_note),
    latestFieldReport: workflow.latestFieldReport ?? workflow.latest_field_report ?? null,
    fieldReports: workflow.fieldReports ?? workflow.field_reports ?? [],
    resolution: workflow.resolution ?? null,
    workflow,
    rawCase,
    terminal: TERMINAL_STATUSES.has(status),
  };
}

export function emptyStateForQueue({ mode = "mine", filter = "active" } = {}) {
  if (mode === "mine" && filter === "active") return { title: "Nothing assigned to you", body: "New assignments will appear here when a lead sends work your way." };
  return ({
    "needs-assignment": { title: "No unassigned findings", body: "Every finding in this view has an owner." },
    overdue: { title: "No overdue work", body: "Active work is currently within its due dates." },
    "recently-resolved": { title: "No recently resolved findings", body: "Reviewed outcomes will appear here after findings are closed." },
    active: { title: "No active findings", body: "There is no current maintenance attention in this view." },
    "awaiting-review": { title: "Nothing awaiting review", body: "Completed field investigations will appear here." },
    "in-progress": { title: "No work in progress", body: "Accepted and active investigations will appear here." },
  })[filter] ?? { title: "No findings", body: "Try another work filter." };
}

export function canLeadWorkflow(role) {
  return ["operator", "admin"].includes(text(role).toLowerCase());
}

export function isAssignedToCurrentUser(finding, currentUser) {
  return text(finding?.assignment?.externalReference).toLowerCase() === text(currentUser?.email).toLowerCase();
}
