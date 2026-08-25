import React from "react";
import FindingConfidenceStrip from "./FindingConfidenceStrip";
import FindingReviewActions from "./FindingReviewActions";
import { FindingWorkflowSummary } from "./FindingWorkflow";

function sentence(value) {
  const clean = String(value ?? "").replace(/\s+/g, " ").trim();
  if (!clean) return "";
  const first = clean.match(/^.*?[.!?](?:\s|$)/)?.[0]?.trim() ?? clean;
  return /[.!?]$/.test(first) ? first : `${first}.`;
}

function label(value) {
  return String(value ?? "").trim().replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function contextFields(finding) {
  const context = finding?.operatingMode && typeof finding.operatingMode === "object" ? finding.operatingMode : {};
  const baseline = context.baseline_mode_label ?? context.baselineModeLabel ?? context.baseline_mode ?? context.baselineMode;
  const recent = context.recent_mode_label ?? context.recentModeLabel ?? context.recent_mode ?? context.recentMode;
  const match = context.match ?? context.status;
  const fields = [
    ["Baseline", baseline],
    ["Current", recent],
    ["Comparator", match],
  ].filter(([, value]) => value !== null && value !== undefined && String(value).trim());
  if (fields.length) return fields;
  const comparison = finding?.comparison ?? {};
  return [
    ["Baseline", comparison.baseline],
    ["Current", comparison.current],
  ].filter(([, value]) => value && !/^(learned baseline|current comparison)$/i.test(String(value).trim()));
}

function FindingSummary({ finding, reviewRecord = { state: "new" }, escalated = false, rankingExplanation = "", escalation = {}, primaryActionLabel = "", onReview, onReviewAction }) {
  if (!finding) return null;
  const statusClass = String(finding.status ?? "change detected").toLowerCase().replace(/\s+/g, "-");
  const insufficient = finding.status === "Evidence insufficient" || ["Deferred", "Withheld"].includes(finding.tier);
  const equipment = finding.location?.asset || finding.location?.subsystem || finding.location?.system || finding.system || "Mapped equipment";
  const system = finding.location?.system && finding.location.system !== equipment ? finding.location.system : "";
  const fallbackPriority = escalation?.serious || escalated ? "critical" : rankingExplanation ? "high" : "";
  const workflow = { ...reviewRecord, status: reviewRecord.status ?? reviewRecord.state, priority: reviewRecord.priority || fallbackPriority };
  const title = insufficient ? "Evidence insufficient for reliable interpretation" : sentence(finding.title || finding.observedChange);
  const context = contextFields(finding);
  const evidence = (finding.visibleSupporting?.length ? finding.visibleSupporting : finding.supporting ?? []).filter(Boolean).slice(0, 3);
  const limitation = sentence(finding.primaryLimitation || finding.certaintyLimit || finding.confidenceReason);
  const next = finding.recommendationAllowed ? sentence(finding.firstPlaceToLook || finding.recommendedFirstAction) : "";
  const why = insufficient
    ? limitation || "The available evidence does not support a reliable change conclusion."
    : sentence(finding.whyItMatters || rankingExplanation || evidence[0] || limitation);
  const accessibleName = title.replace(/[.]$/, "");
  const actionLabel = primaryActionLabel || (finding.objectType === "condition" ? "Investigate" : "Review");

  return (
    <article className={`finding-summary operational-finding operational-finding--${statusClass}${escalated ? " operational-finding--escalated" : ""}`} data-finding-id={finding.id} data-testid="compact-finding-card">
      <header className="operational-finding__identity">
        <div><span>Equipment / system</span><strong>{equipment}</strong>{system ? <small>{system}</small> : null}</div>
        <span className="operational-finding__status">{finding.status || "Evidence insufficient"}</span>
      </header>
      <section className="operational-finding__what"><span>Finding</span><h3>{title}</h3></section>
      {next ? <section className="operational-finding__next"><span>Requested next action</span><p>{next}</p></section> : null}
      <section className="operational-finding__attention"><span>Why this needs attention</span><p>{why || "Review the evidence boundary before deciding the next action."}</p></section>
      <FindingWorkflowSummary workflow={workflow} compact />
      <FindingConfidenceStrip finding={finding} />
      <details className="operational-finding__evidence">
        <summary>Evidence and limitations</summary>
        <div className="operational-finding__evidence-body">
          {context.length ? <dl>{context.map(([term, value]) => <div key={term}><dt>{term}</dt><dd>{label(value)}</dd></div>)}</dl> : null}
          {evidence.length ? <ul>{evidence.map((item) => <li key={item}>{sentence(item)}</li>)}</ul> : <p className="case-unavailable">No supporting evidence item was supplied.</p>}
          {limitation ? <p className="operational-finding__evidence-limit"><strong>Limit:</strong> {limitation}</p> : null}
        </div>
      </details>
      <footer className="operational-finding__action" aria-label={`Actions for ${accessibleName}`}>
        <button type="button" className="forensic-button" onClick={() => onReview?.(finding)}>{actionLabel}</button>
        <details className="operational-finding__more"><summary>Actions</summary><FindingReviewActions finding={finding} reviewRecord={reviewRecord} onAction={onReviewAction} accessibleName={accessibleName} compact /></details>
      </footer>
    </article>
  );
}

export default React.memo(FindingSummary);
