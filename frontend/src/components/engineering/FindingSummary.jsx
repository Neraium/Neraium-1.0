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
  const isCondition = finding.objectType === "condition";
  const evidence = (finding.visibleSupporting?.length ? finding.visibleSupporting : finding.supporting ?? [])
    .slice(0, isCondition ? 3 : 1)
    .map((item) => sentence(item, ""))
    .filter(Boolean);
  if (!evidence.length) evidence.push(sentence(finding.observedChange, "Supporting evidence is available."));
  const nextCheck = sentence(presentation.investigationGuidance[0]?.check ?? finding.firstPlaceToLook ?? finding.recommendedFirstAction, "Review the affected relationship.");
  const trajectory = finding.trajectory?.state
    ? `${finding.trajectory.state}${finding.trajectory.observed_for ? ` · ${finding.trajectory.observed_for}` : ""}`
    : "Not enough evidence to classify";
  const relationshipCount = Number(finding.corroboration?.relationship_count ?? finding.relationships?.length ?? 0);
  const displayStatus = escalated ? "Escalated review" : reviewStateLabel(reviewRecord);
  const visibleFinding = { ...finding, reviewStatus: displayStatus };
  return (
    <article className={`finding-summary operational-finding operational-finding--${statusClass} operational-finding--classification-${presentation.tone}${escalated ? " operational-finding--escalated" : ""}`} data-finding-id={finding.id} data-testid="compact-finding-card">
      <header className="operational-finding__identity"><div><span>{isCondition ? "Condition" : "System or asset"}</span><strong title={finding.location?.likelyInvestigationArea || finding.system}>{finding.location?.likelyInvestigationArea || finding.system || finding.location?.system || "Monitored area not narrowed"}</strong></div></header>
      <div className="operational-finding__what"><h3>{finding.title}</h3></div>
      <FindingClassificationSummary finding={visibleFinding} presentation={presentation} compact />
      {isCondition ? <section className="operational-finding__condition-evidence" aria-label="Condition evidence"><span>Evidence</span><ul>{evidence.map((item) => <li key={item}>{item}</li>)}</ul></section> : null}
      <div className="operational-finding__brief"><p><span>{isCondition ? "Trajectory" : "Evidence"}</span>{isCondition ? trajectory : evidence[0]}</p><p><span>Next check</span>{nextCheck}</p></div>
      {isCondition && relationshipCount ? <details className="operational-finding__relationship-detail"><summary>Details · {relationshipCount} supporting relationship{relationshipCount === 1 ? "" : "s"}</summary><ul>{finding.relationships.slice(0, 5).map((relationship) => <li key={relationship.id || relationship.label}>{relationship.label}</li>)}</ul></details> : null}
      {rankingExplanation ? <p className="operational-finding__ranking"><span>Why this is first</span>{rankingExplanation}</p> : null}
      <footer className="operational-finding__action" aria-label={`Actions for ${finding.title}`}>
        <button type="button" className="forensic-button" onClick={() => onReview?.(finding)}>{isCondition ? "Investigate" : "Review"}</button>
        <details className="operational-finding__more"><summary>{isCondition ? "Actions" : "More actions"}</summary><FindingReviewActions finding={finding} reviewRecord={reviewRecord} onAction={onReviewAction} compact /></details>
      </footer>
    </article>
  );
}

export default React.memo(FindingSummary);
