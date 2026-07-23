import React from "react";
import ConfidenceTierChip from "./ConfidenceTierChip";

function EvidenceList({ items }) {
  if (!items.length) return <p className="forensic-muted">No supporting observation was supplied.</p>;
  return <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul>;
}

export default function FindingSummary({ finding, onEvidence }) {
  if (!finding) return null;
  const statusClass = finding.status.toLowerCase().replace(/\s+/g, "-");
  return (
    <article className={`finding-summary operational-finding operational-finding--${statusClass}`} data-finding-id={finding.id}>
      <header className="operational-finding__meta">
        <span className={`operational-status-chip operational-status-chip--${statusClass}`}>{finding.status}</span>
        <ConfidenceTierChip tier={finding.tier} />
      </header>
      <div className="operational-finding__what">
        <h2>{finding.title}</h2>
      </div>
      <section className="operational-finding__where">
        <h3>Where</h3>
        <p>{finding.location.label}</p>
      </section>
      {finding.relatedAreas?.length ? (
        <section className="operational-finding__areas">
          <h3>Affected areas</h3>
          <p>{finding.relatedAreas.join(" · ")}</p>
        </section>
      ) : null}
      <section className="operational-finding__evidence" aria-label="Strongest supporting evidence">
        <h3>Evidence</h3>
        <EvidenceList items={finding.visibleSupporting} />
      </section>
      {finding.confidenceReason ? <p className="operational-finding__limitation">{finding.confidenceReason}</p> : null}
      <footer className="operational-finding__action">
        <button type="button" className="forensic-button" onClick={() => onEvidence?.(finding)}>Open Evidence</button>
      </footer>
    </article>
  );
}
