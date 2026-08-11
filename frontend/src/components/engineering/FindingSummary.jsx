import React from "react";
import FindingConfidenceStrip from "./FindingConfidenceStrip";
import FindingReviewActions from "./FindingReviewActions";
import { FindingWorkflowSummary } from "./FindingWorkflow";

function sentence(value, fallback) {
  const clean = String(value ?? "").replace(/\s+/g, " ").trim();
  if (!clean) return fallback;
  const first = clean.match(/^.*?[.!?](?:\s|$)/)?.[0]?.trim() ?? clean;
  return /[.!?]$/.test(first) ? first : `${first}.`;
}

function maintenanceAction(value) {
  const action = sentence(value, "Investigate this equipment change.");
  return /\b(?:coupling|corroboration|relationship|signal[_ -]?id|context review)\b/i.test(action)
    ? "Investigate this equipment change."
    : action;
}

function FindingSummary({ finding, reviewRecord = { state: "new" }, escalated = false, rankingExplanation = "", escalation = {}, onReview, onReviewAction }) {
  if (!finding) return null;
  const statusClass = String(finding.status ?? "change detected").toLowerCase().replace(/\s+/g, "-");
  const isCondition = finding.objectType === "condition";
  const equipment = finding.location?.asset || finding.location?.subsystem || finding.location?.system || finding.system || "Mapped equipment";
  const system = finding.location?.system && finding.location.system !== equipment ? finding.location.system : "";
  const requestedAction = maintenanceAction(finding.firstPlaceToLook || finding.recommendedFirstAction || finding.recommendedInvestigation?.[0]);
  const fallbackPriority = escalation?.serious || escalated ? "critical" : rankingExplanation ? "high" : "";
  const workflow = { ...reviewRecord, status: reviewRecord.status ?? reviewRecord.state, priority: reviewRecord.priority || fallbackPriority };
  const maintenanceTitle = `${equipment} changed`;
  return (
    <article className={`finding-summary operational-finding operational-finding--${statusClass}${escalated ? " operational-finding--escalated" : ""}`} data-finding-id={finding.id} data-testid="compact-finding-card">
      <header className="operational-finding__identity">
        <div><span>Equipment / system</span><strong>{equipment}</strong>{system ? <small>{system}</small> : null}</div>
        <span className="operational-finding__status">{workflow.status === "new" ? "New" : String(workflow.status ?? "Open").replace(/[_-]+/g, " ")}</span>
      </header>
      <section className="operational-finding__what"><span>What changed</span><h3>{maintenanceTitle}</h3></section>
      <section className="operational-finding__next"><span>Requested next action</span><p>{sentence(requestedAction, "Review this finding.")}</p></section>
      <FindingWorkflowSummary workflow={workflow} compact />
      <FindingConfidenceStrip finding={finding} />
      {rankingExplanation ? <details className="operational-finding__ranking"><summary>Why this needs attention</summary><p>{rankingExplanation}</p></details> : null}
      <footer className="operational-finding__action" aria-label={`Actions for ${maintenanceTitle}`}>
        <button type="button" className="forensic-button" onClick={() => onReview?.(finding)}>{isCondition ? "Investigate" : "Review"}</button>
        <details className="operational-finding__more"><summary>{isCondition ? "Actions" : "More actions"}</summary><FindingReviewActions finding={finding} reviewRecord={reviewRecord} onAction={onReviewAction} accessibleName={maintenanceTitle} compact /></details>
      </footer>
    </article>
  );
}

export default React.memo(FindingSummary);
