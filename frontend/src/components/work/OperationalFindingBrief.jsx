import React, { useEffect, useState } from "react";
import { canLeadWorkflow, isAssignedToCurrentUser } from "../../viewModels/workQueue";
import FieldReportForm from "./FieldReportForm";
import FindingActivityTimeline from "./FindingActivityTimeline";

const PRIORITIES = ["low", "medium", "high", "critical"];

function dateValue(value) {
  return String(value ?? "").slice(0, 10);
}

function reportDate(value) {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "Date not recorded" : parsed.toLocaleString();
}

function LatestFieldReport({ report }) {
  return (
    <section className="work-field-result" aria-labelledby="work-field-result-title">
      <header><span className="work-eyebrow">Technician result</span><h2 id="work-field-result-title">Latest field report</h2></header>
      {!report ? <p className="work-empty-note">No technician notes yet.</p> : (
        <div>
          <dl>
            <div><dt>Inspected</dt><dd>{report.inspected || "Not recorded"}</dd></div>
            <div><dt>Found</dt><dd>{report.found || "Not recorded"}</dd></div>
            <div><dt>Physical problem</dt><dd>{String(report.problem_found || "uncertain").replace(/_/g, " ")}</dd></div>
            <div><dt>Action taken</dt><dd>{report.action_taken || "None recorded"}</dd></div>
          </dl>
          {report.note ? <p>{report.note}</p> : null}
          <small>{report.actor || "Technician"} · {reportDate(report.recorded_at)}</small>
        </div>
      )}
    </section>
  );
}

function LeadControls({ finding, members, membersLoading, membersError, onWorkflow, onResolve, pending }) {
  const assignedMember = members.find((member) => member.memberId === finding.assignment.externalReference);
  const unavailableAssignment = Boolean(finding.assignment.label && finding.assignment.label !== "Unassigned" && !assignedMember);
  const historicalAssignment = unavailableAssignment && !membersLoading && !membersError;
  const currentMemberId = unavailableAssignment ? "__historical" : finding.assignment.externalReference;
  const [draft, setDraft] = useState({ memberId: currentMemberId, priority: finding.priority, dueDate: dateValue(finding.workflow.dueDate ?? finding.workflow.due_at), managerNote: finding.managerNote });
  useEffect(() => setDraft({ memberId: currentMemberId, priority: finding.priority, dueDate: dateValue(finding.workflow.dueDate ?? finding.workflow.due_at), managerNote: finding.managerNote }), [currentMemberId, finding]);
  const selected = members.find((member) => member.memberId === draft.memberId);

  function save(event) {
    event.preventDefault();
    const changes = {
      priority: draft.priority,
      dueDate: draft.dueDate ? `${draft.dueDate}T23:59:59Z` : null,
      managerNote: draft.managerNote || null,
    };
    if (draft.memberId !== "__historical") {
      changes.assignment = selected ? { kind: "person", label: selected.displayName, externalReference: selected.memberId } : null;
    }
    onWorkflow?.(changes);
  }

  return (
    <section className="lead-controls" aria-labelledby="lead-controls-title">
      <header><span className="work-eyebrow">Lead review</span><h2 id="lead-controls-title">Ownership and next step</h2></header>
      <form onSubmit={save}>
        <label>Assign to<select aria-label="Assign to" value={draft.memberId} disabled={membersLoading || Boolean(membersError)} onChange={(event) => setDraft((current) => ({ ...current, memberId: event.target.value }))}><option value="">Unassigned</option>{unavailableAssignment ? <option value="__historical" disabled>{historicalAssignment ? "Former member" : "Current assignment"} · {finding.assignment.label}</option> : null}{members.map((member) => <option key={member.memberId} value={member.memberId}>{member.displayName}</option>)}</select>{membersError ? <small className="work-error">Assignment is unavailable until active members load.</small> : null}</label>
        <label>Priority<select value={draft.priority} onChange={(event) => setDraft((current) => ({ ...current, priority: event.target.value }))}>{PRIORITIES.map((priority) => <option key={priority} value={priority}>{priority[0].toUpperCase() + priority.slice(1)}</option>)}</select></label>
        <label>Due date<input type="date" value={draft.dueDate} onChange={(event) => setDraft((current) => ({ ...current, dueDate: event.target.value }))} /></label>
        <label className="lead-controls__guidance">Guidance for the technician<textarea value={draft.managerNote} onChange={(event) => setDraft((current) => ({ ...current, managerNote: event.target.value }))} /></label>
        <button type="submit" className="work-primary-action" disabled={pending}>Save assignment</button>
      </form>
      <div className="lead-controls__outcomes" aria-label="Lead workflow outcomes">
        <button type="button" onClick={() => onWorkflow?.({ status: "investigating" })} disabled={pending}>Return for investigation</button>
        <button type="button" onClick={() => onWorkflow?.({ status: "monitoring" })} disabled={pending}>Monitor</button>
        <button type="button" onClick={() => onWorkflow?.({ status: "escalated" })} disabled={pending}>Escalate</button>
        <button type="button" onClick={() => onWorkflow?.({ status: "dismissed" })} disabled={pending}>Dismiss</button>
        <button type="button" onClick={() => onResolve?.("maintenance_performed", "Lead reviewed the completed field investigation.")} disabled={pending}>Resolve</button>
        <button type="button" onClick={() => onResolve?.("no_issue_found", "No maintenance issue was found after review.")} disabled={pending}>No action needed</button>
      </div>
    </section>
  );
}

export default function OperationalFindingBrief({ finding, currentUser, members = [], membersLoading = false, membersError = "", activity = [], activityLoading = false, activityError = "", pending = false, mutationMessage = "", mutationError = false, onBack, onWorkflow, onFieldReport, onResolve, technicalFinding, onInvestigation, onEvidence }) {
  const lead = canLeadWorkflow(currentUser?.role);
  const assignedToMe = isAssignedToCurrentUser(finding, currentUser);
  const technicianCanUpdate = lead || assignedToMe;
  return (
    <article className="work-brief">
      <button type="button" className="work-back" onClick={onBack}>Back to work list</button>
      <header className="work-brief__header">
        <div><span className="work-eyebrow">{finding.system}</span><h1>{finding.equipment}</h1><p>{finding.change}</p></div>
        <div className="work-brief__urgency"><span className={`work-priority work-priority--${finding.priority}`}>{finding.priority}</span><strong>{finding.statusLabel}</strong></div>
      </header>
      <dl className="work-brief__facts">
        <div><dt>Assigned to</dt><dd>{finding.assignment.label}{finding.assignment.historical ? <small>Historical assignment</small> : null}</dd></div>
        <div><dt>Assigned by</dt><dd>{finding.assignedBy}</dd></div>
        <div data-due-tone={finding.due.tone}><dt>Due</dt><dd>{finding.due.label}</dd></div>
        <div><dt>Change confidence</dt><dd>{finding.confidence}</dd></div>
      </dl>
      <section className="work-first-check"><span className="work-eyebrow">Check first</span><h2>{finding.firstCheck}</h2>{finding.managerNote ? <p>{finding.managerNote}</p> : null}</section>

      {technicianCanUpdate && !finding.terminal ? (
        <section className="work-quick-actions" aria-label="Technician work actions">
          {finding.status === "open" ? <button type="button" className="work-primary-action" onClick={() => onWorkflow?.({ status: "acknowledged" })} disabled={pending}>Accept work</button> : null}
          {finding.status === "acknowledged" ? <button type="button" className="work-primary-action" onClick={() => onWorkflow?.({ status: "investigating" })} disabled={pending}>Start investigation</button> : null}
          {["investigating", "waiting", "escalated"].includes(finding.status) ? <button type="button" onClick={() => onWorkflow?.({ status: "waiting" })} disabled={pending}>Mark waiting</button> : null}
        </section>
      ) : !lead && !assignedToMe ? <p className="work-permission-note">This work is not assigned to you. You can review it, but only its assignee or a lead can update it.</p> : null}
      <p className={`work-form-status${mutationError ? " is-error" : ""}`} role="status" aria-live="polite">{mutationMessage}</p>

      {lead ? <LeadControls finding={finding} members={members} membersLoading={membersLoading} membersError={membersError} onWorkflow={onWorkflow} onResolve={onResolve} pending={pending} /> : null}
      {technicianCanUpdate && !finding.terminal ? <FieldReportForm disabled={pending} onSubmit={onFieldReport} /> : null}
      <LatestFieldReport report={finding.latestFieldReport} />
      <FindingActivityTimeline activity={activity} loading={activityLoading} error={activityError} />

      <section className="work-drilldown" aria-labelledby="work-drilldown-title">
        <header><span className="work-eyebrow">Deeper context</span><h2 id="work-drilldown-title">Investigation and evidence</h2></header>
        {technicalFinding ? <div><button type="button" onClick={() => onInvestigation?.(technicalFinding)}>Open investigation</button><button type="button" onClick={() => onEvidence?.(technicalFinding)}>Open technical evidence</button></div> : <p>Technical evidence is not available in this workspace context. The operational finding and team history remain available here.</p>}
      </section>
    </article>
  );
}
