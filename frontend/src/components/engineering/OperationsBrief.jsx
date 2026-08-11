import React, { useMemo } from "react";
import { buildOperationsBrief, deriveEscalationReadiness } from "../../viewModels/operationsBrief";
import { reviewRecordFor } from "../../viewModels/findingReviewState";
import FindingSummary from "./FindingSummary";

function briefDate(value) {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "Current conditions";
  return new Intl.DateTimeFormat(undefined, { weekday: "long", month: "short", day: "numeric" }).format(date);
}

function FindingList({ findings, brief, model, reviewRecords, onReview, onReviewAction }) {
  return (
    <div className="operations-finding-list">
      {findings.map((finding) => (
        <FindingSummary
          key={finding.id}
          finding={finding}
          reviewRecord={reviewRecordFor(finding, reviewRecords)}
          escalated={brief.escalations.includes(finding)}
          rankingExplanation={brief.priorityFinding?.id === finding.id ? brief.priorityExplanation : ""}
          onReview={onReview}
          onReviewAction={onReviewAction}
          escalation={deriveEscalationReadiness(finding, model.result)}
        />
      ))}
    </div>
  );
}

function BriefSection({ id, title, count, children }) {
  if (!count) return null;
  return (
    <section className="operations-section" aria-labelledby={id}>
      <header><h2 id={id}>{title}</h2><span aria-label={`${count} ${count === 1 ? "item" : "items"}`}>{count}</span></header>
      {children}
    </section>
  );
}

export default function OperationsBrief({ model, reviewRecords = {}, onReview, onReviewAction }) {
  const now = useMemo(() => new Date(), []);
  const brief = useMemo(() => buildOperationsBrief(model, reviewRecords, now), [model, now, reviewRecords]);
  const activeFindingCount = brief.newFindings.length + brief.needsAttention.length + brief.monitoringFindings.length;
  const monitoringCount = brief.monitoringFindings.length + brief.monitoringIssues.length;
  const allQuiet = activeFindingCount === 0 && brief.monitoringIssues.length === 0;
  const escalation = brief.escalations[0] ?? null;
  const escalationState = escalation ? deriveEscalationReadiness(escalation, model.result) : null;

  return (
    <div className="operations-brief operational-overview" data-testid="operations-brief">
      <header className="operations-brief__header">
        <div>
          <span className="forensic-kicker">Operations Brief · {briefDate(now)}</span>
          <h1>{model.site.name}</h1>
          <p>What deserves attention right now.</p>
        </div>
        <div className="operations-brief__state" data-quiet={allQuiet ? "true" : "false"}>
          <span>Current conditions</span>
          <strong>{allQuiet ? "Within learned behavior" : `${activeFindingCount} ${activeFindingCount === 1 ? "item" : "items"} in review`}</strong>
        </div>
      </header>

      {allQuiet ? (
        <section className="operations-quiet" aria-live="polite">
          <span className="operations-quiet__mark" aria-hidden="true" />
          <div><h2>All monitored systems are within learned behavior.</h2><p>No new findings require review.</p></div>
        </section>
      ) : (
        <section className="operations-answer" aria-live="polite">
          <strong>{brief.newFindings.length ? `${brief.newFindings.length} new ${brief.newFindings.length === 1 ? "finding" : "findings"} for review.` : "No new findings for review."}</strong>
          <span>{brief.needsAttention.length ? `${brief.needsAttention.length} unresolved ${brief.needsAttention.length === 1 ? "finding needs" : "findings need"} attention.` : monitoringCount ? `${monitoringCount} ${monitoringCount === 1 ? "item is" : "items are"} being monitored.` : ""}</span>
        </section>
      )}

      {escalation ? (
        <section className="operations-escalation" aria-label="Prompt engineering review">
          <div><span>Prompt engineering review</span><strong>{escalation.title}</strong></div>
          <p>{escalationState?.strengthening ? "Evidence support for the persistent relationship change is increasing across related signals." : "A persistent relationship change is supported across related signals."}</p>
          <ul><li>{escalation.classificationPresentation?.classificationConfidence ?? escalation.tier} confidence</li><li>Strong mode match</li><li>{escalation.classificationPresentation?.persistence?.label ?? "Persistent"}</li></ul>
          <button type="button" className="forensic-button" onClick={() => onReview?.(escalation)}>Review</button>
        </section>
      ) : null}

      {!allQuiet || brief.recentlyResolved.length ? (
        <div className="operations-sections">
          <BriefSection id="operations-new-heading" title="New" count={brief.newFindings.length}>
            <FindingList findings={brief.newFindings} brief={brief} model={model} reviewRecords={reviewRecords} onReview={onReview} onReviewAction={onReviewAction} />
          </BriefSection>
          <BriefSection id="operations-attention-heading" title="Needs attention" count={brief.needsAttention.length}>
            <FindingList findings={brief.needsAttention} brief={brief} model={model} reviewRecords={reviewRecords} onReview={onReview} onReviewAction={onReviewAction} />
          </BriefSection>
          <BriefSection id="operations-monitoring-heading" title="Monitoring" count={monitoringCount}>
            {brief.monitoringFindings.length ? <FindingList findings={brief.monitoringFindings} brief={brief} model={model} reviewRecords={reviewRecords} onReview={onReview} onReviewAction={onReviewAction} /> : null}
            {brief.monitoringIssues.length ? <ul className="operations-monitoring-list">{brief.monitoringIssues.map((issue, index) => <li key={issue.id ?? index}><strong>{issue.source ?? "Instrumentation"}</strong><span>{issue.signals?.[0] ?? "Signal coverage needs review"}</span></li>)}</ul> : null}
          </BriefSection>
          <BriefSection id="operations-resolved-heading" title="Recently resolved" count={brief.recentlyResolved.length}>
            <ul className="operations-resolved-list">{brief.recentlyResolved.map((item) => <li key={item.id}><div><strong>{item.title}</strong>{item.system ? <span>{item.system}</span> : null}</div><small>{item.status}</small></li>)}</ul>
          </BriefSection>
        </div>
      ) : null}
    </div>
  );
}
