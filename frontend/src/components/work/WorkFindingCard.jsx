import React from "react";

export default function WorkFindingCard({ finding, selected = false, onOpen }) {
  return (
    <article className={`work-card${selected ? " is-selected" : ""}`} data-testid="work-finding-card">
      <button type="button" className="work-card__open" onClick={() => onOpen?.(finding)} aria-label={`Open ${finding.equipment}: ${finding.change}`}>
        <header>
          <div><span className="work-eyebrow">{finding.system}</span><h2>{finding.equipment}</h2></div>
          <span className={`work-priority work-priority--${finding.priority}`}>{finding.priority}</span>
        </header>
        <p className="work-card__change">{finding.change}</p>
        <dl className="work-card__facts">
          <div><dt>Status</dt><dd>{finding.statusLabel}</dd></div>
          <div><dt>Assigned to</dt><dd>{finding.assignment.label}</dd></div>
          <div data-due-tone={finding.due.tone}><dt>Due</dt><dd>{finding.due.label}</dd></div>
          <div><dt>Change confidence</dt><dd>{finding.confidence}</dd></div>
        </dl>
        <span className="work-card__action">Review work</span>
      </button>
    </article>
  );
}
