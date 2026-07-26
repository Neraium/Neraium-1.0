import React from "react";
import ConfidenceTierChip from "./ConfidenceTierChip";

function sentence(value, fallback) {
  const text = String(value ?? "").trim();
  if (!text) return fallback;
  return /[.!?]$/.test(text) ? text : `${text}.`;
}

export default function FindingSummary({ finding, acknowledged = false, escalated = false, onReview, onAcknowledge, onEvidence }) {
  if (!finding) return null;
  const statusClass = String(finding.status ?? "change detected").toLowerCase().replace(/\s+/g, "-");
  const classification = finding.status === "Change detected" ? "Behavior change" : "Evidence limited";
  const evidence = sentence(finding.visibleSupporting?.[0] ?? finding.supporting?.[0], "Supporting evidence is available.");
  const nextCheck = sentence(finding.firstPlaceToLook, "Review relationship timeline.");
  const displayStatus = escalated ? "Escalation" : acknowledged ? "Acknowledged" : "New";
  return (
    <article className={`finding-summary operational-finding operational-finding--${statusClass}${escalated ? " operational-finding--escalated" : ""}`} data-finding-id={finding.id}>
      <header className="operational-finding__identity">
        <div><span>System</span><strong>{finding.system || finding.location?.system || "System not assigned"}</strong></div>
        <div className="operational-finding__chips">
          <span className={`operational-status-chip operational-status-chip--${statusClass}`}>{classification}</span>
          <ConfidenceTierChip tier={finding.tier} />
          <span className={`operational-review-status${escalated ? " is-escalated" : ""}`}>{displayStatus}</span>
        </div>
      </header>
      <div className="operational-finding__what"><h3>{finding.title}</h3></div>
      <div className="operational-finding__brief">
        <p><span>Evidence</span>{evidence}</p>
        <p><span>Next check</span>{nextCheck}</p>
      </div>
      <footer className="operational-finding__action">
        <button type="button" className="forensic-button" onClick={() => onReview?.(finding)}>Review</button>
        <button type="button" className="forensic-button forensic-button--secondary" aria-pressed={acknowledged} onClick={() => onAcknowledge?.(finding)}>{acknowledged ? "Acknowledged" : "Acknowledge"}</button>
        <button type="button" className="baseline-text-button" onClick={() => onEvidence?.(finding)}>Evidence</button>
      </footer>
    </article>
  );
}
