import React from "react";
import FindingReviewActions from "./FindingReviewActions";

function sentence(value, fallback) {
  const clean = String(value ?? "").replace(/\s+/g, " ").trim();
  if (!clean) return fallback;
  const first = clean.match(/^.*?[.!?](?:\s|$)/)?.[0]?.trim() ?? clean;
  return /[.!?]$/.test(first) ? first : `${first}.`;
}

function FindingSummary({ finding, reviewRecord = { state: "new" }, escalated = false, onReview, onReviewAction }) {
  if (!finding) return null;
  const statusClass = String(finding.status ?? "change detected").toLowerCase().replace(/\s+/g, "-");
  const isCondition = finding.objectType === "condition";
  const evidence = [...new Set([
    ...(finding.supporting ?? []),
    ...(finding.relationships ?? []).map((relationship) => relationship?.label),
  ])]
    .map((item) => sentence(item, ""))
    .filter(Boolean);
  const system = finding.location?.system || finding.system || finding.location?.label || "System not assigned";
  const confidence = finding.tier || finding.confidence || "Withheld";
  return (
    <article className={`finding-summary operational-finding operational-finding--${statusClass}${escalated ? " operational-finding--escalated" : ""}`} data-finding-id={finding.id} data-testid="compact-finding-card">
      <header className="operational-finding__alert">
        <div><span>What happened</span><h3>{finding.title}</h3></div>
        <dl>
          <div><dt>System</dt><dd>{system}</dd></div>
          <div><dt>Confidence</dt><dd>{confidence}</dd></div>
        </dl>
      </header>
      <details className="operational-finding__evidence">
        <summary>Evidence ({evidence.length})</summary>
        {evidence.length ? <ul>{evidence.map((item) => <li key={item}>{item}</li>)}</ul> : <p>No supporting observation was supplied.</p>}
      </details>
      <footer className="operational-finding__action" aria-label={`Actions for ${finding.title}`}>
        <button type="button" className="forensic-button" onClick={() => onReview?.(finding)}>{isCondition ? "Investigate" : "Review"}</button>
        <details className="operational-finding__more"><summary>{isCondition ? "Actions" : "More actions"}</summary><FindingReviewActions finding={finding} reviewRecord={reviewRecord} onAction={onReviewAction} compact /></details>
      </footer>
    </article>
  );
}

export default React.memo(FindingSummary);
