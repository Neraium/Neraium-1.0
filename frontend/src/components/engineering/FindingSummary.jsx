import React from "react";
import { normalizeFindingPresentation } from "../../viewModels/operatorFinding";
import FindingClassificationSummary from "../operational/FindingClassificationSummary";

function sentence(value, fallback) {
  const clean = String(value ?? "").replace(/\s+/g, " ").trim();
  if (!clean) return fallback;
  const first = clean.match(/^.*?[.!?](?:\s|$)/)?.[0]?.trim() ?? clean;
  return /[.!?]$/.test(first) ? first : `${first}.`;
}

function FindingSummary({ finding, onEvidence }) {
  const [acknowledged, setAcknowledged] = React.useState(false);
  if (!finding) return null;
  const statusClass = finding.status.toLowerCase().replace(/\s+/g, "-");
  const presentation = finding.classificationPresentation ?? normalizeFindingPresentation(finding);
  const evidence = sentence(finding.visibleSupporting?.[0] || finding.observedChange, "Recorded behavior changed from the learned baseline.");
  const nextCheck = sentence(
    presentation.investigationGuidance[0]?.check || finding.firstPlaceToLook || finding.recommendedFirstAction,
    "Review source data and relationship evidence.",
  );
  const visibleFinding = acknowledged ? { ...finding, status: "Acknowledged" } : finding;
  return (
    <article className={`finding-summary operational-finding operational-finding--${statusClass} operational-finding--classification-${presentation.tone}`} data-finding-id={finding.id} data-testid="compact-finding-card">
      <header className="operational-finding__identity">
        <span className="forensic-kicker">{finding.location?.asset || finding.system || finding.location?.label || "Unassigned system"}</span>
        <h2>{finding.title}</h2>
      </header>
      <FindingClassificationSummary finding={visibleFinding} compact />
      <p className="operational-finding__evidence-line">{evidence}</p>
      <div className="operational-finding__next"><span>Next check</span><p>{nextCheck}</p></div>
      <footer className="operational-finding__action" aria-label={`Actions for ${finding.title}`}>
        <button type="button" className="forensic-button" onClick={() => onEvidence?.(finding)}>Review</button>
        <button type="button" className="forensic-button forensic-button--secondary" aria-pressed={acknowledged} onClick={() => setAcknowledged(true)}>{acknowledged ? "Acknowledged" : "Acknowledge"}</button>
        <button type="button" className="forensic-link-button" onClick={() => onEvidence?.(finding)}>View evidence</button>
      </footer>
    </article>
  );
}

export default React.memo(FindingSummary);
