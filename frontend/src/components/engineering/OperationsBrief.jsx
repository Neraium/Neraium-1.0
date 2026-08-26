import React from "react";

import FindingSummary from "./FindingSummary";

function countLabel(value, singular, plural) {
  return `${value} ${value === 1 ? singular : plural}`;
}

export default function OperationsBrief({ projection, onReview, onOpenEvidence }) {
  if (!projection || projection.variant === "unavailable") {
    return (
      <section className="operations-brief operational-overview operations-result-state" data-testid="operations-brief">
        <span className="forensic-kicker">Operations Brief</span>
        <h1>Result unavailable</h1>
        <p>The result cannot be presented from the available analysis record.</p>
      </section>
    );
  }
  if (projection.variant === "processing") {
    return (
      <section className="operations-brief operational-overview operations-result-state" data-testid="operations-brief" aria-live="polite">
        <span className="forensic-kicker">Operations Brief</span>
        <h1>{projection.headline}</h1>
        <p>{projection.explanation}</p>
      </section>
    );
  }
  const stable = projection.variant === "ready" && projection.outcome === "stable";
  const insufficient = projection.variant === "insufficient";
  const noReviewable = projection.variant === "ready" && projection.outcome === "analysis_complete" && projection.cards.length === 0;
  if (stable || insufficient || noReviewable) {
    return (
      <section className={`operations-brief operational-overview operations-result-state${insufficient ? " operations-result-state--insufficient" : ""}`} data-testid="operations-brief" aria-live="polite">
        <span className="forensic-kicker">{projection.eyebrow}</span>
        <h1>{projection.headline}</h1>
        <p>{projection.explanation}</p>
        {noReviewable ? <dl className="operations-brief__counts" aria-label="Analysis result counts"><div><dt>Findings for review</dt><dd>0</dd></div><div><dt>Systems represented</dt><dd>0</dd></div></dl> : null}
        {insufficient && projection.improvement ? <small>{projection.improvement}</small> : null}
        {insufficient && projection.auditAction ? (
          <div className="operations-result-state__action">
            <button type="button" className="forensic-button forensic-button--secondary" onClick={() => onOpenEvidence?.(projection.auditAction.findingKey)}>{projection.auditAction.label}</button>
          </div>
        ) : null}
      </section>
    );
  }
  return (
    <div className="operations-brief operational-overview" data-testid="operations-brief">
      <header className="operations-brief__header operations-brief__header--summary">
        <div>
          <span className="forensic-kicker">{projection.eyebrow}</span>
          <h1>{projection.headline}</h1>
          <p>{projection.explanation}</p>
        </div>
        <dl className="operations-brief__counts" aria-label="Analysis result counts">
          <div><dt>Findings for review</dt><dd>{projection.counts.findingsForReview}</dd></div>
          <div><dt>Systems represented</dt><dd>{projection.counts.systemsRepresented}</dd></div>
        </dl>
      </header>

      <section className="operations-results" aria-labelledby="operations-results-heading">
        <header><h2 id="operations-results-heading">What to review</h2><span>{countLabel(projection.cards.length, "finding", "findings")}</span></header>
        <div className="operations-finding-list">
          {projection.cards.map((card) => <FindingSummary key={card.findingKey} card={card} onReview={onReview} />)}
        </div>
      </section>
    </div>
  );
}
