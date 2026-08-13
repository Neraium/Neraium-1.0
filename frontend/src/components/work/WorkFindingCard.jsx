import React from "react";
import { workStatusTone } from "../../viewModels/workQueue";

export default function WorkFindingCard({ finding, mode = "mine", actionLabel = "Open work", selected = false, onOpen }) {
  return (
    <article className={`work-card${selected ? " is-selected" : ""}`} data-testid="work-finding-card">
      <button type="button" className="work-card__open" onClick={() => onOpen?.(finding)} aria-label={`Open ${finding.equipment}: ${finding.change}`}>
        <header>
          <div><span className="work-eyebrow">{finding.system}</span><h2>{finding.equipment}</h2></div>
          <div className="work-card__signals">
            <span className={`work-status work-status--${workStatusTone(finding.status)}`}>{finding.statusLabel}</span>
            <span className={`work-priority work-priority--${finding.priority}`}>{finding.priority}</span>
          </div>
        </header>
        <p className="work-card__change">{finding.change}</p>
        <dl className="work-card__facts">
          <div><dt>{mode === "team" ? "Assigned to" : "Assigned by"}</dt><dd>{mode === "team" ? finding.assignment.label : finding.assignedBy}</dd></div>
          <div data-due-tone={finding.due.tone}><dt>Due</dt><dd>{finding.due.label}</dd></div>
          <div><dt>Change confidence</dt><dd>{finding.confidence}</dd></div>
        </dl>
        <span className="work-card__action">{actionLabel}<span aria-hidden="true"> →</span></span>
      </button>
    </article>
  );
}
