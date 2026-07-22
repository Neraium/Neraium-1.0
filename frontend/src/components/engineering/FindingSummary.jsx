import React from "react";
import ConfidenceTierChip from "./ConfidenceTierChip";

function EvidenceList({ items, empty }) {
  return items.length ? <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="forensic-muted">{empty}</p>;
}

export default function FindingSummary({ finding, primary = false, onInvestigate, onEvidence }) {
  if (!finding) return (
    <section className="finding-summary finding-summary--empty">
      <span className="forensic-kicker">Operational finding</span>
      <h2>No supported operational finding</h2>
      <p>Available evidence does not identify behavior that requires an investigation.</p>
    </section>
  );
  const withheld = finding.tier === "Withheld";
  return (
    <article className={`finding-summary${primary ? " finding-summary--primary" : ""}${withheld ? " finding-summary--withheld" : ""}`} data-finding-id={finding.id}>
      <header>
        <div><span className="forensic-kicker">{primary ? "Highest-priority operational finding" : "Operational finding"}</span><h2>{finding.title}</h2><p>{finding.system}</p></div>
        <ConfidenceTierChip tier={finding.tier} />
      </header>
      <div className="finding-summary__grid">
        <section><h3>Observed change</h3><p>{finding.observedChange}</p></section>
        <section><h3>Why it matters</h3><p>{finding.whyItMatters}</p></section>
        <section><h3>Supporting evidence</h3><EvidenceList items={finding.supporting} empty="No supporting observation was supplied." /></section>
        <section><h3>Contradicting or limiting evidence</h3><EvidenceList items={[...finding.contradictions, ...finding.limitations]} empty="No contradictory evidence was supplied with this result." /></section>
        <section className="finding-summary__inspection"><h3>{withheld ? "Evidence required to continue" : "First place to look"}</h3><p>{withheld ? (finding.limitations[0] || "Mapped, complete relationship evidence is required before a specific inspection can be recommended.") : (finding.firstPlaceToLook || "Begin with the selected relationship and its contributing signals.")}</p></section>
        <section><h3>Confirmation criteria</h3><p>{finding.confirmationCriteria}</p></section>
      </div>
      <footer>
        <dl><div><dt>Baseline</dt><dd>{finding.comparison.baseline}</dd></div><div><dt>Current period</dt><dd>{finding.comparison.current}</dd></div></dl>
        <div className="finding-summary__actions">
          {onEvidence ? <button type="button" className="forensic-button forensic-button--secondary" onClick={() => onEvidence(finding)}>Inspect evidence</button> : null}
          {onInvestigate ? <button type="button" className="forensic-button" onClick={() => onInvestigate(finding)}>{withheld ? "Review evidence gap" : "Open investigation"}</button> : null}
        </div>
      </footer>
    </article>
  );
}
