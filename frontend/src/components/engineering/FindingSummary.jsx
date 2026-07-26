import React from "react";
import { normalizeFindingPresentation } from "../../viewModels/operatorFinding";
import FindingClassificationSummary from "../operational/FindingClassificationSummary";

function sentence(value, fallback) {
  const clean = String(value ?? "").replace(/\s+/g, " ").trim();
  if (!clean) return fallback;
  const first = clean.match(/^.*?[.!?](?:\s|$)/)?.[0]?.trim() ?? clean;
  return /[.!?]$/.test(first) ? first : `${first}.`;
}

function FindingSummary({ finding, acknowledged = false, escalated = false, onReview, onAcknowledge, onEvidence }) {
  if (!finding) return null;
  const statusClass = String(finding.status ?? "change detected").toLowerCase().replace(/\s+/g, "-");
  const presentation = finding.classificationPresentation ?? normalizeFindingPresentation(finding);
  const evidence = sentence(finding.visibleSupporting?.[0] ?? finding.supporting?.[0] ?? finding.observedChange, "Supporting evidence is available.");
  const nextCheck = sentence(
    presentation.investigationGuidance[0]?.check ?? finding.firstPlaceToLook ?? finding.recommendedFirstAction,
    "Review relationship evidence.",
  );
  const displayStatus = escalated ? "Escalation" : acknowledged ? "Acknowledged" : "New";
  const visibleFinding = { ...finding, reviewStatus: displayStatus };
  return (
    <article className={`finding-summary operational-finding operational-finding--${statusClass} operational-finding--classification-${presentation.tone}${escalated ? " operational-finding--escalated" : ""}`} data-finding-id={finding.id} data-testid="compact-finding-card">
      <header className="operational-finding__identity">
        <div><span>System</span><strong>{finding.system || finding.location?.system || finding.location?.asset || "System not assigned"}</strong></div>
      </header>
      <div className="operational-finding__what"><h3>{finding.title}</h3></div>
      <FindingClassificationSummary finding={visibleFinding} compact />
      <div className="operational-finding__brief">
        <p><span>Evidence</span>{evidence}</p>
        <p><span>Next check</span>{nextCheck}</p>
      </div>
      <footer className="operational-finding__action" aria-label={`Actions for ${finding.title}`}>
        <button type="button" className="forensic-button" onClick={() => (onReview ?? onEvidence)?.(finding)}>Review</button>
        <button type="button" className="forensic-button forensic-button--secondary" aria-pressed={acknowledged} onClick={() => onAcknowledge?.(finding)}>{acknowledged ? "Acknowledged" : "Acknowledge"}</button>
        <button type="button" className="baseline-text-button forensic-link-button" onClick={() => onEvidence?.(finding)}>Evidence</button>
      </footer>
    </article>
  );
}

export default React.memo(FindingSummary);
