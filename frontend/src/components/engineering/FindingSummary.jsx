import React from "react";
import { normalizeFindingPresentation } from "../../viewModels/operatorFinding";
import { reviewStateLabel } from "../../viewModels/findingReviewState";
import FindingClassificationSummary from "../operational/FindingClassificationSummary";
import FindingReviewActions from "./FindingReviewActions";

function sentence(value, fallback) {
  const clean = String(value ?? "").replace(/\s+/g, " ").trim();
  if (!clean) return fallback;
  const first = clean.match(/^.*?[.!?](?:\s|$)/)?.[0]?.trim() ?? clean;
  return /[.!?]$/.test(first) ? first : `${first}.`;
}

function FindingSummary({ finding, reviewRecord = { state: "new" }, escalated = false, rankingExplanation = "", onReview, onReviewAction }) {
  if (!finding) return null;
  const statusClass = String(finding.status ?? "change detected").toLowerCase().replace(/\s+/g, "-");
  const presentation = finding.classificationPresentation ?? normalizeFindingPresentation(finding);
  const evidence = sentence(finding.visibleSupporting?.[0] ?? finding.supporting?.[0] ?? finding.observedChange, "Supporting evidence is available.");
  const nextCheck = sentence(presentation.investigationGuidance[0]?.check ?? finding.firstPlaceToLook ?? finding.recommendedFirstAction, "Review the affected relationship.");
  const displayStatus = escalated ? "Escalated review" : reviewStateLabel(reviewRecord);
  const visibleFinding = { ...finding, reviewStatus: displayStatus };
  return (
    <article className={`finding-summary operational-finding operational-finding--${statusClass} operational-finding--classification-${presentation.tone}${escalated ? " operational-finding--escalated" : ""}`} data-finding-id={finding.id} data-testid="compact-finding-card">
      <header className="operational-finding__identity"><div><span>System or asset</span><strong title={finding.system || finding.location?.system || finding.location?.asset}>{finding.system || finding.location?.system || finding.location?.asset || "System not assigned"}</strong></div></header>
      <div className="operational-finding__what"><h3>{finding.title}</h3></div>
      <FindingClassificationSummary finding={visibleFinding} presentation={presentation} compact />
      <div className="operational-finding__brief"><p><span>Evidence</span>{evidence}</p><p><span>Next check</span>{nextCheck}</p></div>
      {rankingExplanation ? <p className="operational-finding__ranking"><span>Why this is first</span>{rankingExplanation}</p> : null}
      <footer className="operational-finding__action" aria-label={`Actions for ${finding.title}`}>
        <button type="button" className="forensic-button" onClick={() => onReview?.(finding)}>Review</button>
        <details className="operational-finding__more"><summary>More actions</summary><FindingReviewActions finding={finding} reviewRecord={reviewRecord} onAction={onReviewAction} compact /></details>
      </footer>
    </article>
  );
}

export default React.memo(FindingSummary);
