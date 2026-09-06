import React, { useEffect, useState } from "react";
import { reviewStateLabel } from "../../viewModels/findingReviewState";

const STATUS_OPTIONS = ["open", "acknowledged", "investigating", "monitoring", "dismissed"];
const PRIORITY_OPTIONS = ["low", "medium", "high", "critical"];
const RESOLUTION_OPTIONS = [
  ["issue_found", "Issue found"],
  ["no_issue_found", "No issue found"],
  ["operational_change", "Operational change"],
  ["sensor_issue", "Sensor issue"],
  ["maintenance_performed", "Maintenance performed"],
];
const FEEDBACK_OPTIONS = [
  ["confirmed_issue", "Confirmed issue"],
  ["useful_warning", "Useful warning"],
  ["known_operational_change", "Known operational change"],
  ["maintenance_event", "Maintenance event"],
  ["sensor_or_data_problem", "Sensor or data problem"],
  ["environmental_cause", "Environmental observation"],
  ["expected_behavior", "Expected behavior"],
  ["false_positive", "False positive"],
  ["nothing_meaningful", "Nothing meaningful"],
];

function clean(value) {
  return String(value ?? "").trim();
}

function title(value, fallback = "Not set") {
  const text = clean(value);
  return text ? text.replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase()) : fallback;
}

function workflowStatusLabel(value) {
  const normalized = clean(value).toLowerCase().replace(/[ -]+/g, "_");
  const workflowLabels = {
    open: "Open",
    acknowledged: "Acknowledged",
    investigating: "Investigating",
    monitoring: "Monitoring",
    resolved: "Resolved",
    dismissed: "Dismissed",
  };
  if (workflowLabels[normalized]) return workflowLabels[normalized];
  if (["new", "closed", "not_useful"].includes(normalized)) return reviewStateLabel(normalized);
  return title(value, "Open");
}

function dateInput(value) {
  return clean(value).slice(0, 10);
}

export function dueState(value, now = new Date()) {
  const source = clean(value);
  if (!source) return { label: "No due date", tone: "none" };
  const due = new Date(source.length === 10 ? `${source}T23:59:59Z` : source);
  if (Number.isNaN(due.getTime())) return { label: "Due date unavailable", tone: "none" };
  const today = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  const dueDay = new Date(Date.UTC(due.getUTCFullYear(), due.getUTCMonth(), due.getUTCDate()));
  const days = Math.round((dueDay.getTime() - today.getTime()) / 86_400_000);
  if (days < 0) return { label: `Overdue · ${due.toLocaleDateString()}`, tone: "overdue" };
  if (days === 0) return { label: "Due today", tone: "today" };
  if (days === 1) return { label: "Due tomorrow", tone: "soon" };
  return { label: `Due ${due.toLocaleDateString()}`, tone: days <= 7 ? "soon" : "scheduled" };
}

export function FindingWorkflowSummary({ workflow = {}, compact = false }) {
  const assignment = workflow.assignment ?? {};
  const due = dueState(workflow.dueDate ?? workflow.due_at);
  const status = workflow.status ?? workflow.state ?? "open";
  return (
    <dl className={`finding-workflow-summary${compact ? " finding-workflow-summary--compact" : ""}`}>
      <div><dt>Priority</dt><dd>{title(workflow.priority ?? workflow.effectivePriority ?? workflow.effective_priority, "Needs review")}</dd></div>
      <div><dt>Assignment</dt><dd>{clean(assignment.label) || "Unassigned"}{assignment.kind || assignment.targetType || assignment.target_type ? <small>{title(assignment.kind ?? assignment.targetType ?? assignment.target_type)}</small> : null}</dd></div>
      {!compact ? <div data-due-tone={due.tone}><dt>Due</dt><dd>{due.label}</dd></div> : null}
      {!compact ? <div><dt>Workflow</dt><dd>{workflowStatusLabel(status)}</dd></div> : null}
      {!compact && workflow.validationOutcome ? <div><dt>Validation</dt><dd>{title(workflow.validationOutcome)}</dd></div> : null}
      {!compact && workflow.workOrderReference ? <div><dt>Work order</dt><dd>{workflow.workOrderReference}</dd></div> : null}
    </dl>
  );
}

function workflowDraft(workflow) {
  const assignment = workflow?.assignment ?? {};
  return {
    status: clean(workflow?.status) || "open",
    priority: clean(workflow?.userPriority ?? workflow?.user_priority),
    assignmentKind: clean(assignment.kind ?? assignment.targetType ?? assignment.target_type),
    assignmentLabel: clean(assignment.label),
    assignmentExternalReference: clean(assignment.externalReference ?? assignment.external_ref),
    dueDate: dateInput(workflow?.dueDate ?? workflow?.due_at),
    managerNote: clean(workflow?.managerNote ?? workflow?.manager_note),
    workOrderReference: clean(workflow?.workOrderReference ?? workflow?.work_order_reference),
    externalReference: clean(workflow?.externalReference ?? workflow?.external_reference),
    validationOutcome: clean(workflow?.validationOutcome ?? workflow?.validation_outcome),
    validationNote: clean(workflow?.validationNote ?? workflow?.validation_note),
  };
}

function conflictMessage(error) {
  if (error?.conflict || [409, 412].includes(Number(error?.status))) return "This finding changed after you opened it. Reload the workflow before saving again.";
  return error?.message || "The workflow change could not be saved.";
}

export default function FindingWorkflowPanel({ finding, workflow = {}, onSave, onFeedback, onResolve, onReload }) {
  const [draft, setDraft] = useState(() => workflowDraft(workflow));
  const [resolution, setResolution] = useState({ outcome: RESOLUTION_OPTIONS[0][0], note: "" });
  const [feedback, setFeedback] = useState({ category: FEEDBACK_OPTIONS[0][0], note: "", actionTaken: "" });
  const [state, setState] = useState({ pending: "", message: "", error: false });
  const identity = workflow.findingId ?? workflow.workflowFindingId ?? finding?.workflowFindingId ?? finding?.id;
  const version = Number(workflow.version ?? 0);
  useEffect(() => setDraft(workflowDraft(workflow)), [workflow]);
  const assignmentDisabled = !draft.assignmentKind;
  const persisted = workflow.persisted === true || clean(workflow.findingId);
  const canMutate = persisted && typeof onSave === "function";
  const dirtyAssignment = draft.assignmentKind && draft.assignmentLabel
    ? { kind: draft.assignmentKind, label: draft.assignmentLabel, externalReference: draft.assignmentExternalReference }
    : null;
  const savePayload = {
    status: draft.status,
    priority: draft.priority || null,
    assignment: dirtyAssignment,
    dueDate: draft.dueDate ? `${draft.dueDate}T23:59:59Z` : null,
    managerNote: draft.managerNote || null,
    workOrderReference: draft.workOrderReference || null,
    externalReference: draft.externalReference || null,
    validationOutcome: draft.validationOutcome || null,
    validationNote: draft.validationNote || null,
  };

  async function save(event) {
    event.preventDefault();
    setState({ pending: "save", message: "", error: false });
    try {
      await onSave?.({ findingId: identity, expectedVersion: version, changes: savePayload });
      setState({ pending: "", message: "Workflow saved.", error: false });
    } catch (error) {
      setState({ pending: "", message: conflictMessage(error), error: true });
    }
  }

  async function resolve(event) {
    event.preventDefault();
    setState({ pending: "resolve", message: "", error: false });
    try {
      await onResolve?.({ findingId: identity, expectedVersion: version, outcome: resolution.outcome, note: resolution.note });
      setState({ pending: "", message: "Resolution recorded.", error: false });
    } catch (error) {
      setState({ pending: "", message: conflictMessage(error), error: true });
    }
  }

  async function submitFeedback(event) {
    event.preventDefault();
    setState({ pending: "feedback", message: "", error: false });
    try {
      await onFeedback?.({ findingId: identity, expectedVersion: version, ...feedback });
      setState({ pending: "", message: "Feedback recorded.", error: false });
      setFeedback((current) => ({ ...current, note: "", actionTaken: "" }));
    } catch (error) {
      setState({ pending: "", message: conflictMessage(error), error: true });
    }
  }

  return (
    <section className="finding-workflow" aria-labelledby={`finding-workflow-${finding?.id ?? identity}`}>
      <header><div><span className="forensic-kicker">Finding workflow</span><h2 id={`finding-workflow-${finding?.id ?? identity}`}>Ownership and next action</h2></div><span>Version {version}</span></header>
      <FindingWorkflowSummary workflow={workflow} />
      <details className="finding-workflow__editor">
        <summary>Edit workflow</summary>
        <form onSubmit={save}>
          <label>Status<select value={draft.status} onChange={(event) => setDraft((current) => ({ ...current, status: event.target.value }))}>{draft.status === "resolved" ? <option value="resolved" disabled>Resolved</option> : null}{STATUS_OPTIONS.map((option) => <option key={option} value={option}>{title(option)}</option>)}</select></label>
          <label>User priority<select value={draft.priority} onChange={(event) => setDraft((current) => ({ ...current, priority: event.target.value }))}><option value="">Use recommended priority</option>{PRIORITY_OPTIONS.map((option) => <option key={option} value={option}>{title(option)}</option>)}</select></label>
          <label>Assign to<select value={draft.assignmentKind} onChange={(event) => setDraft((current) => ({ ...current, assignmentKind: event.target.value, assignmentLabel: event.target.value ? current.assignmentLabel : "" }))}><option value="">Unassigned</option><option value="person">Person</option><option value="team">Team</option></select></label>
          <label>Person or team label<input value={draft.assignmentLabel} required={!assignmentDisabled} disabled={assignmentDisabled} onChange={(event) => setDraft((current) => ({ ...current, assignmentLabel: event.target.value }))} /></label>
          <label>Assignment external reference<input value={draft.assignmentExternalReference} disabled={assignmentDisabled} onChange={(event) => setDraft((current) => ({ ...current, assignmentExternalReference: event.target.value }))} /></label>
          <label>Due date<input type="date" value={draft.dueDate} onChange={(event) => setDraft((current) => ({ ...current, dueDate: event.target.value }))} /></label>
          <label className="finding-workflow__wide">Manager note<textarea value={draft.managerNote} onChange={(event) => setDraft((current) => ({ ...current, managerNote: event.target.value }))} /></label>
          <label>Work order reference<input value={draft.workOrderReference} onChange={(event) => setDraft((current) => ({ ...current, workOrderReference: event.target.value }))} /></label>
          <label>External reference<input value={draft.externalReference} onChange={(event) => setDraft((current) => ({ ...current, externalReference: event.target.value }))} /></label>
          <label>Validation outcome<input value={draft.validationOutcome} onChange={(event) => setDraft((current) => ({ ...current, validationOutcome: event.target.value }))} /></label>
          <label>Validation note<input value={draft.validationNote} onChange={(event) => setDraft((current) => ({ ...current, validationNote: event.target.value }))} /></label>
          <div className="finding-workflow__buttons"><button type="submit" className="forensic-button" disabled={!canMutate || state.pending === "save"}>{state.pending === "save" ? "Saving…" : "Save workflow"}</button>{state.error && onReload ? <button type="button" className="forensic-button forensic-button--secondary" onClick={onReload}>Reload workflow</button> : null}</div>
        </form>
      </details>
      <details className="finding-workflow__feedback">
        <summary>Record feedback</summary>
        <form onSubmit={submitFeedback}>
          <label>Feedback category<select value={feedback.category} onChange={(event) => setFeedback((current) => ({ ...current, category: event.target.value }))}>{FEEDBACK_OPTIONS.map(([value, optionLabel]) => <option key={value} value={value}>{optionLabel}</option>)}</select></label>
          <label>Feedback note<textarea value={feedback.note} onChange={(event) => setFeedback((current) => ({ ...current, note: event.target.value }))} /></label>
          <label>Action taken<input value={feedback.actionTaken} onChange={(event) => setFeedback((current) => ({ ...current, actionTaken: event.target.value }))} /></label>
          <button type="submit" className="forensic-button" disabled={!persisted || typeof onFeedback !== "function" || state.pending === "feedback"}>{state.pending === "feedback" ? "Recording…" : "Save feedback"}</button>
        </form>
      </details>
      <details className="finding-workflow__resolution">
        <summary>Record resolution</summary>
        <form onSubmit={resolve}>
          <label>Resolution outcome<select required value={resolution.outcome} onChange={(event) => setResolution((current) => ({ ...current, outcome: event.target.value }))}>{RESOLUTION_OPTIONS.map(([value, optionLabel]) => <option key={value} value={value}>{optionLabel}</option>)}</select></label>
          <label>Resolution note<textarea value={resolution.note} onChange={(event) => setResolution((current) => ({ ...current, note: event.target.value }))} /></label>
          <button type="submit" className="forensic-button" disabled={!persisted || typeof onResolve !== "function" || state.pending === "resolve"}>{state.pending === "resolve" ? "Recording…" : "Resolve finding"}</button>
        </form>
      </details>
      {!persisted ? <p className="finding-workflow__notice">Historical record · Finding-level workflow is unavailable. Existing review actions remain available.</p> : null}
      <p className={`finding-workflow__status${state.error ? " is-error" : ""}`} role="status" aria-live="polite">{state.message}</p>
    </section>
  );
}
