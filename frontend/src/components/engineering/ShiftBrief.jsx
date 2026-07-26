import React, { useMemo } from "react";
import { buildShiftBrief } from "../../viewModels/shiftBrief";
import FindingSummary from "./FindingSummary";

function briefDate(value) {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "Current shift";
  return new Intl.DateTimeFormat(undefined, { weekday: "long", month: "short", day: "numeric" }).format(date);
}

function CountCell({ label, value, tone = "quiet" }) {
  return (
    <div className={`shift-count shift-count--${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function FindingList({ findings, brief, acknowledgedIds, onReview, onEvidence, onAcknowledge }) {
  return (
    <div className="shift-finding-list">
      {findings.map((finding) => (
        <FindingSummary
          key={finding.id}
          finding={finding}
          acknowledged={acknowledgedIds.includes(String(finding.id))}
          escalated={brief.escalations.includes(finding)}
          onReview={onReview}
          onEvidence={onEvidence}
          onAcknowledge={onAcknowledge}
        />
      ))}
    </div>
  );
}

export default function ShiftBrief({ model, acknowledgedIds = [], onReview, onEvidence, onAcknowledge, onSystem }) {
  const now = useMemo(() => new Date(), []);
  const brief = useMemo(() => buildShiftBrief(model, acknowledgedIds, now), [acknowledgedIds, model, now]);
  const allQuiet = brief.newFindings.length === 0 && brief.needsAttention.length === 0;
  const issueCount = brief.monitoringIssues.length;
  const attentionCount = brief.newFindings.length + brief.needsAttention.length;
  const issueSentence = `${issueCount} instrumentation issue${issueCount === 1 ? "" : "s"} remain${issueCount === 1 ? "s" : ""} under review.`;
  return (
    <div className="shift-brief operational-overview" data-testid="shift-brief">
      <header className="shift-brief__header">
        <div>
          <span className="forensic-kicker">Shift Brief · {briefDate(now)}</span>
          <h1>{model.site.name}</h1>
          <p>What deserves attention today.</p>
        </div>
        <div className="shift-brief__state" data-quiet={allQuiet ? "true" : "false"}>
          <span>Status</span>
          <strong>{allQuiet ? "Quiet" : `${attentionCount} to review`}</strong>
        </div>
      </header>

      <section className="shift-counts" aria-label="Morning summary">
        <CountCell label="New findings" value={brief.counts.newFindings} tone={brief.counts.newFindings ? "attention" : "quiet"} />
        <CountCell label="Escalations" value={brief.counts.escalations} tone={brief.counts.escalations ? "critical" : "quiet"} />
        <CountCell label="Resolved" value={brief.counts.resolved} />
        <CountCell label="Monitoring" value={brief.counts.monitoring} tone={brief.counts.monitoring ? "watch" : "quiet"} />
      </section>

      <section className="shift-answer" aria-live="polite">
        <strong>{allQuiet ? "No new unexplained system changes." : `${attentionCount} unexplained system change${attentionCount === 1 ? "" : "s"} ${attentionCount === 1 ? "needs" : "need"} review.`}</strong>
        {issueCount ? <span>{issueSentence}</span> : <span>Instrumentation is reporting normally.</span>}
      </section>

      {brief.escalations.length ? (
        <section className="shift-escalation" aria-label="Escalations">
          <span>Escalation</span>
          <strong>{brief.escalations[0].title}</strong>
          <small>Persistent change on a critical asset with multiple supporting relationships and no known operational explanation.</small>
        </section>
      ) : null}

      <div className="shift-sections">
        <section className="shift-section" aria-labelledby="new-today-heading">
          <header><h2 id="new-today-heading">New today</h2><span>{brief.newFindings.length}</span></header>
          {brief.newFindings.length ? (
            <FindingList findings={brief.newFindings} brief={brief} acknowledgedIds={acknowledgedIds} onReview={onReview} onEvidence={onEvidence} onAcknowledge={onAcknowledge} />
          ) : <p className="shift-section__empty">No new findings.</p>}
        </section>

        <section className="shift-section" aria-labelledby="needs-attention-heading">
          <header><h2 id="needs-attention-heading">Needs attention</h2><span>{brief.needsAttention.length}</span></header>
          {brief.needsAttention.length ? (
            <FindingList findings={brief.needsAttention} brief={brief} acknowledgedIds={acknowledgedIds} onReview={onReview} onEvidence={onEvidence} onAcknowledge={onAcknowledge} />
          ) : <p className="shift-section__empty">No carried findings need review.</p>}
        </section>

        <section className="shift-section" aria-labelledby="monitoring-heading">
          <header><h2 id="monitoring-heading">Monitoring</h2><span>{issueCount}</span></header>
          {issueCount ? (
            <ul className="shift-monitoring-list">
              {brief.monitoringIssues.map((issue, index) => <li key={issue.id ?? index}><strong>{issue.source ?? "Instrumentation"}</strong><span>{issue.signals?.[0] ?? "Signal coverage"}</span></li>)}
            </ul>
          ) : <p className="shift-section__empty">Instrumentation is reporting normally.</p>}
        </section>

        <section className="shift-section" aria-labelledby="quiet-systems-heading">
          <header><h2 id="quiet-systems-heading">Quiet systems</h2><span>{brief.quietSystems.length}</span></header>
          {brief.quietSystems.length ? (
            <div className="quiet-system-list">{brief.quietSystems.map((system) => <button type="button" key={system.id ?? system.name} onClick={() => onSystem?.(system.name)}><span aria-hidden="true" />{system.name}</button>)}</div>
          ) : <p className="shift-section__empty">No quiet systems reported.</p>}
        </section>
      </div>
    </div>
  );
}
