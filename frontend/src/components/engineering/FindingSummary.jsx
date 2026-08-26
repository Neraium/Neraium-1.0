import React from "react";

function FindingSummary({ card, onReview }) {
  if (!card) return null;
  const context = [card.systemContext, card.assetContext].filter(Boolean);
  const accessibleName = String(card.title || "finding").replace(/[.]$/, "");

  return (
    <article className="finding-summary operational-finding operational-finding--compact" data-finding-key={card.findingKey} data-testid="compact-finding-card">
      <header className="operational-finding__identity">
        <div>
          <span>System / asset</span>
          <strong>{context[0]}</strong>
          {context[1] ? <small>{context[1]}</small> : null}
        </div>
        <span className="operational-finding__priority">{card.priority}</span>
      </header>
      <section className="operational-finding__what">
        <span>Finding</span>
        <h3>{card.title}</h3>
        <p>{card.behavior}</p>
      </section>
      <dl className="operational-finding__summary-meta">
        <div><dt>Change confidence</dt><dd>{card.changeConfidence}</dd></div>
        <div><dt>Review state</dt><dd>{card.reviewState}</dd></div>
        <div><dt>Assignment</dt><dd>{card.assignment}</dd></div>
      </dl>
      {card.materialLimitation ? <p className="operational-finding__compact-limit"><span>Important limitation</span>{card.materialLimitation}</p> : null}
      <footer className="operational-finding__action" aria-label={`Actions for ${accessibleName}`}>
        <button type="button" className="forensic-button" onClick={() => onReview?.(card.findingKey)}>{card.primaryAction.label}</button>
      </footer>
    </article>
  );
}

export default React.memo(FindingSummary);
