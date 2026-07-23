import React from "react";
import ConfidenceTierChip from "./ConfidenceTierChip";

function EvidenceList({ items }) {
  if (!items.length) return <p className="forensic-muted">No supporting observation was supplied.</p>;
  return <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul>;
}

export default function FindingSummary({ finding, onEvidence }) {
  if (!finding) return null;
  return (
    <article className={`finding-summary operational-finding operational-finding--${finding.status.toLowerCase().replace(/\s+/g, "-")}`} data-finding-id={finding.id}>
      <div className="operational-finding__answer">
        <div className="operational-field operational-field--status">
          <span>Status</span>
          <strong>{finding.status}</strong>
        </div>
        <div className="operational-field operational-field--what">
          <span>What</span>
          <h2>{finding.title}</h2>
        </div>
        <div className="operational-field operational-field--where">
          <span>Where</span>
          <p>{finding.location.label}</p>
        </div>
        <div className="operational-field operational-field--confidence">
          <span>Confidence</span>
          <ConfidenceTierChip tier={finding.tier} />
          {finding.confidenceReason ? <small>{finding.confidenceReason}</small> : null}
        </div>
        <div className="operational-finding__action">
          <button type="button" className="forensic-button" onClick={() => onEvidence?.(finding)}>Open Evidence</button>
        </div>
      </div>
      <section className="operational-finding__evidence" aria-label="Strongest supporting evidence">
        <h3>Evidence</h3>
        <EvidenceList items={finding.visibleSupporting} />
      </section>
      {finding.primaryLimitation ? <p className="operational-finding__limitation"><strong>Limitation:</strong> {finding.primaryLimitation}</p> : null}
    </article>
  );
}
